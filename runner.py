# 러너 — run_autonomous_task(태스크 분류→킥오프→워크플로우), run_followup_task(피드백 후속 처리)

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import db
import rag
from agents import AGENTS, WORKFLOWS
from utils import sse, agent_call, doc_call, set_attachment, make_sse_stream
from workspace_utils import create_workspace, write_workspace, extract_code
from deliberation import classify_task, bilateral_chat
from workflows import _run_build, _run_feedback, _run_review, _run_discuss, _run_plan


def run_autonomous_task(task: str, attachment: dict | None = None):
    return make_sse_stream(_autonomous_task_gen(task, attachment))


def _autonomous_task_gen(task: str, attachment: dict | None = None):
    set_attachment(attachment)
    rag_context = rag.search(task)
    session_id = None

    def save(agent_id, content, msg_type, participants=None):
        if not session_id:
            return
        try:
            a = AGENTS.get(agent_id, {})
            db.save_message(session_id, agent_id, a.get("name", agent_id),
                            a.get("role", ""), content, msg_type, participants)
        except Exception as e:
            print(f"[DB] 저장 실패: {e}")

    workflow_type = classify_task(task)
    yield sse({"type": "workflow", "workflow_type": workflow_type,
               "phases": WORKFLOWS.get(workflow_type, [])})

    # workflow_type 확정 후 세션 생성
    try:
        session_id = db.create_session(task, workflow_type)
    except Exception as e:
        session_id = None
        print(f"[DB] 세션 생성 실패: {e}")

    yield sse({"type": "phase", "phase": 1, "label": "킥오프"})

    for aid in AGENTS:
        yield sse({"type": "thinking", "agent": aid})

    intentions = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(agent_call, aid, task,
                f"태스크: '{task}'\n\n첫 반응을 당신의 성향에서 한 마디로."): aid
            for aid in AGENTS
        }
        for future in as_completed(futures):
            aid = futures[future]
            try:
                text, intention = future.result()
            except Exception:
                text, intention = "...", None
            if intention and intention.get("action") == "want":
                intentions[aid] = intention
            save(aid, text, "kickoff")
            yield sse({"type": "response", "agent": aid, "content": text,
                       "ctx": "kickoff", "intention": intention})

    # 1:1 대화 요청 처리 (중복 방지)
    seen_pairs = set()
    for aid, intention in intentions.items():
        target = intention.get("target", "")
        if target in AGENTS and target != aid:
            pair = tuple(sorted([aid, target]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                yield sse({"type": "intention", "agent": aid, "target": target,
                           "reason": intention.get("reason", "")})
                yield from bilateral_chat(aid, target, intention.get("reason", task), task)

    workspace = create_workspace(task, workflow_type)
    yield sse({"type": "workspace_created", "path": workspace})

    if workflow_type == "build":
        yield from _run_build(task, workspace, save, rag_context)
    elif workflow_type == "feedback":
        yield from _run_feedback(task, workspace, save, rag_context)
    elif workflow_type == "review":
        yield from _run_review(task, workspace, save, rag_context)
    elif workflow_type == "discuss":
        yield from _run_discuss(task, workspace, save, rag_context)
    else:
        yield from _run_plan(task, workspace, save, rag_context)

    rag.index_workspace(workspace, task, workflow_type)

    if session_id:
        try:
            db.complete_session(session_id, task)
        except Exception as e:
            print(f"[DB] 세션 완료 실패: {e}")

    set_attachment(None)  # 다음 태스크를 위해 초기화


def run_followup_task(task: str, workspace: str, feedback: str):
    return make_sse_stream(_followup_task_gen(task, workspace, feedback))


def _followup_task_gen(task: str, workspace: str, feedback: str):
    yield sse({"type": "phase", "phase": 1, "label": "피드백 킥오프"})

    yield sse({"type": "thinking", "agent": "lead"})
    notice, _ = agent_call("lead", task,
        f"사용자 피드백이 들어왔습니다: '{feedback}'\n\n"
        f"팀에게 이 피드백을 전달하고 무엇을 수정/추가할지 한 마디로 지시하세요.")
    yield sse({"type": "kickoff", "agent": "lead", "content": notice})

    yield sse({"type": "phase", "phase": 2, "label": "수정 작업"})
    react_agents = ["jimin", "junhyuk", "yujin", "suyoung", "mina"]
    with ThreadPoolExecutor(max_workers=5) as ex:
        react_futures = {
            ex.submit(agent_call, aid, task,
                f"사용자 피드백: '{feedback}'\n\n"
                f"승우 지시: {notice}\n\n이 피드백에 대해 본인 역할 관점에서 한 마디."
            ): aid for aid in react_agents
        }
        for fut in as_completed(react_futures):
            aid = react_futures[fut]
            try:
                msg, _ = fut.result()
                yield sse({"type": "message", "agent": aid, "content": msg})
            except Exception:
                pass

    generated = {}
    if workspace and os.path.isdir(workspace):
        for root, _, files in os.walk(workspace):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, workspace)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        generated[rel] = f.read()
                except Exception:
                    pass

    if generated:
        relevant_files = list(generated.keys())[:6]
        yield sse({"type": "phase", "phase": 3, "label": "파일 수정"})

        def fix_with_feedback(fpath, content):
            is_frontend = fpath.endswith(".html") or "static/" in fpath
            agent_id = "mina" if is_frontend else "suyoung"
            return fpath, agent_id, doc_call(agent_id, task,
                f"사용자 피드백: '{feedback}'\n\n"
                f"기존 파일 `{fpath}`:\n```\n{content[:1200]}\n```\n\n"
                f"피드백을 반영해서 이 파일을 수정하세요. "
                f"수정이 필요 없으면 원본 그대로 코드 블록으로 반환하세요.",
                max_tokens=8192
            )

        with ThreadPoolExecutor(max_workers=4) as ex:
            fix_futures = {
                ex.submit(fix_with_feedback, fp, generated[fp]): fp
                for fp in relevant_files if fp in generated
            }
            for fut in as_completed(fix_futures):
                fp = fix_futures[fut]
                try:
                    fpath, agent_id, raw = fut.result()
                    code = extract_code(raw)
                    write_workspace(workspace, fpath, code)
                    generated[fpath] = code
                    yield sse({"type": "doc_saved", "agent": agent_id,
                               "file": fpath, "path": f"{workspace}/{fpath}"})
                except Exception as e:
                    yield sse({"type": "error", "msg": f"{fp} 수정 실패: {e}"})

    yield sse({"type": "phase", "phase": 4, "label": "최종 결론"})
    yield sse({"type": "thinking", "agent": "lead"})
    final, _ = agent_call("lead", task,
        f"피드백 '{feedback}'을 반영해서 수정 작업이 완료되었습니다.\n\n"
        f"수정 결과를 한 줄로 정리하세요.")
    write_workspace(workspace, "00_팀장결론.md", final)
    yield sse({"type": "synthesis", "content": final, "agent": "lead",
               "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})
