# 토론 — deliberate(라운드 토론+합의), team_gate(전원 PASS/BLOCK 투표), classify_task(태스크 라우팅)

import json, re, random, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

_CALL_STAGGER = 2.0  # API 콜 사이 딜레이 (초) — generation.py와 통일

from agents import AGENTS, WORKFLOWS
from signals import ConsensusSignal, GateSignal
from utils import sse, agent_call, doc_call, tool_agent_call, strip_next, client, MODEL_FAST, MODEL_SMART  # noqa: E501


def quick_react(task: str, situation: str, candidates: list[str],
                max_agents: int = 2, skip_chance: float = 0.2) -> list[tuple[str, str]]:
    if random.random() < skip_chance:
        return []
    n = random.randint(1, min(max_agents, len(candidates)))
    selected = random.sample(candidates, n)
    results = []
    with ThreadPoolExecutor(max_workers=len(selected)) as ex:
        futures = {
            ex.submit(agent_call, aid, task,
                      f"{situation}\n\n자연스럽게 한 마디만. 50자 이내."): aid
            for aid in selected
        }
        for fut in as_completed(futures):
            aid = futures[fut]
            try:
                text, _ = fut.result()
                results.append((aid, strip_next(text)))
            except Exception:
                pass
    return results


def deliberate(task: str, topic: str, agents: list[str], rounds: int = 2,
               workspace: str = ""):
    history: deque[tuple[str, str]] = deque(maxlen=20)

    for round_num in range(rounds):
        for aid in agents:
            context = "\n".join(f"{AGENTS[a]['name']}: {t}" for a, t in history)
            is_first = not context

            if is_first:
                # 첫 발언 — 조사하고 나서 말하기 (Sonnet + 도구 사용)
                file_hint = (
                    "search_memory로 과거 유사 사례를 찾거나, "
                    "read_file / list_files로 관련 파일을 직접 확인하세요.\n"
                ) if workspace else "search_memory로 과거 유사 사례를 찾아보세요.\n"
                prompt = (
                    f"토론 주제: {topic}\n\n"
                    f"발언 전에 {file_hint}"
                    f"조사한 내용을 근거로 당신 성향의 핵심 입장을 말하세요. 200자 이내."
                )
                call_model = MODEL_SMART
            else:
                # 이후 발언 — 앞 사람 발언 보고 반응 (Haiku, 도구 불필요)
                prompt = (
                    f"토론 주제: {topic}\n\n"
                    f"지금까지 논의:\n{context}\n\n"
                    f"앞 발언에 구체적으로 반응하거나 반박하세요. 상대방 이름 언급. 200자 이내."
                )
                call_model = MODEL_FAST

            yield sse({"type": "thinking", "agent": aid})
            try:
                text = tool_agent_call(aid, task, prompt,
                                       workspace=workspace, max_tokens=1024,
                                       model=call_model)
                text = strip_next(text)
                history.append((aid, text))
                yield sse({"type": "response", "agent": aid, "content": text, "ctx": "debate"})
            except Exception as e:
                print(f"[deliberate] {aid} 발언 실패: {e}")
            time.sleep(_CALL_STAGGER)

    # ── 각 에이전트 핵심 요구사항 표명 ────────────────────────────
    full_convo = "\n".join(f"{AGENTS[a]['name']}: {t}" for a, t in history)
    requirements: dict[str, str] = {}

    for aid in agents:
        yield sse({"type": "thinking", "agent": aid})
        try:
            req = tool_agent_call(aid, task,
                f"토론 결과:\n{full_convo}\n\n"
                f"당신 성향에서 이 결과물에 반드시 반영되어야 할 핵심 요구사항 1가지를 한 문장으로.",
                workspace=workspace,
                max_tokens=1024,
                model=MODEL_FAST,  # 짧은 요구사항 표명 — Haiku로 충분
            )
            req = strip_next(req)
            requirements[aid] = req
            yield sse({"type": "response", "agent": aid, "content": f"✔ {req}", "ctx": "requirement"})
        except Exception as e:
            print(f"[deliberate] {aid} 요구사항 실패: {e}")
        time.sleep(_CALL_STAGGER)

    # ── 체크리스트 형태로 합의문 구성 ────────────────────────────
    req_lines = "\n".join(
        f"- {AGENTS[a]['name']}: {requirements[a]}"
        for a in agents if a in requirements
    )
    checklist = f"【팀 합의 체크리스트】\n{req_lines}"
    yield sse({"type": "consensus", "agent": "lead", "content": checklist})
    yield ConsensusSignal(consensus=checklist)


def classify_task(task: str) -> str:
    try:
        resp = client.messages.create(
            model=MODEL_FAST, max_tokens=20,
            system=(
                "Classify the task into one type:\n"
                "- build: create, make, build, develop a project/app/service/tool\n"
                "- feedback: review, evaluate, improve, give feedback on existing content\n"
                "- review: code review, technical audit\n"
                "- discuss: question, recommendation, compare options, brainstorm\n"
                "- plan: planning only, roadmap, spec, design doc (no implementation)\n"
                "Reply with ONLY the type word, nothing else."
            ),
            messages=[{"role": "user", "content": task}],
        )
        t = resp.content[0].text.strip().lower()
        return t if t in WORKFLOWS else "build"
    except Exception:
        return "build"


def _extract_requirement(consensus: str, agent_name: str) -> str:
    """합의 체크리스트에서 특정 에이전트의 요구사항 추출."""
    m = re.search(rf"- {re.escape(agent_name)}: (.+)", consensus)
    return m.group(1).strip() if m else ""


def team_gate(task: str, artifact_summary: str, round_label: str,
              consensus: str = "", workspace: str = ""):
    """순차적으로 투표하는 generator. 각 에이전트가 도구로 파일을 직접 읽어 검증.
    마지막에 {"__gate__": (can_proceed, block_reasons, summary)} yield."""
    votes = {}

    for aid in AGENTS:
        yield sse({"type": "thinking", "agent": aid})
        my_req = _extract_requirement(consensus, AGENTS[aid]["name"])
        req_check = (
            f"\n\n【당신의 핵심 요구사항】: {my_req}\n"
            f"이 요구사항이 결과물에 반영됐는지 반드시 확인하세요."
        ) if my_req else ""

        tool_hint = (
            "\n\nlist_files로 생성된 파일 목록을 확인하고, "
            "read_file로 핵심 파일을 직접 읽어서 요구사항 반영 여부를 검증하세요."
            if workspace else ""
        )

        try:
            resp = tool_agent_call(aid, task,
                f"라운드: {round_label}\n\n결과물 요약:\n{artifact_summary[:300]}"
                f"{req_check}{tool_hint}\n\n"
                f"당신의 요구사항이 반영됐는가? 다음 단계로 넘어가도 되는가?\n"
                f"확인 후 반드시 JSON만 출력: "
                f"{{\"vote\": \"PASS\" or \"BLOCK\", \"reason\": \"한 줄 이유\", "
                f"\"missing\": \"반영 안 된 항목 (BLOCK시만, 없으면 빈 문자열)\"}}",
                workspace=workspace,
                max_tokens=1024,
            )
            m = re.search(r'\{.*?\}', resp, re.DOTALL)
            if m:
                try:
                    d = json.loads(m.group())
                    v = d.get("vote", "PASS").upper()
                    r = d.get("reason", "")
                    missing = d.get("missing", "")
                    r = f"{r} — 미반영: {missing}" if v == "BLOCK" and missing else r
                except json.JSONDecodeError:
                    print(f"[team_gate] JSON 파싱 실패 ({aid}): {m.group()!r}")
                    v, r = "BLOCK", "JSON 파싱 실패 — 검증 불가"
            else:
                print(f"[team_gate] JSON 없음 ({aid}): {resp!r}")
                v, r = "BLOCK", "응답 파싱 불가 — 검증 불가"
        except Exception as e:
            print(f"[team_gate] 예외 ({aid}): {e}")
            v, r = "PASS", ""

        votes[aid] = (v, r)
        yield sse({"type": "response", "agent": aid,
                   "content": f"{'✅ PASS' if v == 'PASS' else '⛔ BLOCK'} — {r}",
                   "ctx": "gate"})
        time.sleep(_CALL_STAGGER)

    blockers = [(aid, r) for aid, (v, r) in votes.items() if v == "BLOCK"]
    can_proceed = len(blockers) == 0  # 1명이라도 BLOCK이면 재시도
    block_reasons = [f"{AGENTS[aid]['name']}: {r}" for aid, r in blockers]
    summary = f"{len(AGENTS) - len(blockers)}/{len(AGENTS)} PASS"
    yield GateSignal(can_proceed=can_proceed, block_reasons=block_reasons, summary=summary)


def bilateral_chat(aid1: str, aid2: str, topic: str, task: str, turns: int = 2):
    """두 에이전트 간 1:1 대화 generator."""
    yield sse({"type": "bilateral_start", "participants": [aid1, aid2], "topic": topic})
    history = []
    for _ in range(turns):
        for aid in [aid1, aid2]:
            other = aid2 if aid == aid1 else aid1
            ctx = "\n".join(f"{AGENTS[a]['name']}: {t}" for a, t in history)
            prompt = (
                f"[1:1 대화] {AGENTS[other]['name']}와 대화 중. 주제: {topic}\n\n"
                + (f"대화 내용:\n{ctx}\n\n" if ctx else "")
                + "자연스럽게 한 마디. 1문장 이내."
            )
            yield sse({"type": "thinking", "agent": aid})
            try:
                text, _ = agent_call(aid, task, prompt, 100)
                text = strip_next(text)
                history.append((aid, text))
                yield sse({"type": "response", "agent": aid, "content": text, "ctx": "bilateral"})
            except Exception:
                pass
    yield sse({"type": "bilateral_end", "participants": [aid1, aid2]})
