# 생성 — 기획 문서(4종) 및 코드 파일 병렬 생성, 잘림 시 이어쓰기, 파일 수정

import json, os, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents import AGENTS
from signals import BriefSignal, DocsSignal, CodeSignal
from utils import sse, agent_call, doc_call
from workspace_utils import write_workspace, extract_code, is_truncated

# 병렬 API 콜 사이 딜레이 (rate limit 방지)
_CALL_STAGGER = 2.0   # 각 콜 제출 간격 (초)
_MAX_WORKERS  = 3     # 동시 최대 API 콜 수


def _pick_code_agent(fpath: str) -> str:
    """파일 경로를 보고 가장 적합한 담당자를 반환."""
    fname = os.path.basename(fpath).lower()
    # 프론트엔드 → 민아
    if fpath.endswith(".html") or "static/" in fpath or "frontend/" in fpath:
        return "mina"
    # 테스트 → 지민 (품질파)
    if any(x in fname for x in ("test_", "_test.", "spec_", "_spec.", "conftest")):
        return "jimin"
    # 유틸·보안·인증·미들웨어 → 유진 (실용파·보안)
    if any(x in fname for x in ("util", "helper", "security", "auth", "middleware",
                                 "validator", "guard", "permission")):
        return "yujin"
    # DB·모델·스키마 → 수영 (아키텍처파)
    if any(x in fname for x in ("model", "schema", "db", "database",
                                 "migration", "repository", "store")):
        return "suyoung"
    # API·라우터·서비스 → 수영
    if any(x in fname for x in ("api", "route", "router", "endpoint",
                                 "service", "controller", "handler")):
        return "suyoung"
    # requirements, config → 유진
    if any(x in fname for x in ("requirements", "config", "settings", "env")):
        return "yujin"
    # README, 문서 → 민아 (사용자 친화적 글쓰기)
    if fname.endswith(".md"):
        return "mina"
    return "suyoung"


def plan_code_structure(task: str, doc_summary: str, arch_consensus: str = "") -> list[dict]:
    consensus_note = f"\n\n【팀 아키텍처 합의 — 반드시 반영】\n{arch_consensus}" if arch_consensus else ""
    resp = doc_call("suyoung", task,
        f"프로젝트 문서 요약:\n{doc_summary[:800]}{consensus_note}\n\n"
        f"이 프로젝트의 전체 파일 구조를 결정하세요.\n"
        f"의존성 순서대로 (낮은 레벨 → 높은 레벨) JSON 배열로만 반환하세요.\n"
        f"각 파일에 대해 path, description, exports(다른 파일이 import할 클래스/함수 목록)를 명시하세요:\n"
        f'[{{"path": "code/models.py", "description": "데이터 모델", "exports": "class User, class Session"}}, ...]\n'
        f"반드시 포함해야 하는 항목:\n"
        f"- code/ 하위 백엔드 파일들 (models, services, routers 등)\n"
        f"- code/requirements.txt\n"
        f"- static/index.html (프론트엔드 UI — 반드시 포함)\n"
        f"- README.md\n"
        f"반드시 JSON만 반환.",
        max_tokens=500
    )
    match = re.search(r'\[.*?\]', resp, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return [
        {"path": "code/main.py", "description": "메인 진입점", "exports": "app"},
        {"path": "code/requirements.txt", "description": "의존성", "exports": ""},
        {"path": "static/index.html", "description": "프론트엔드 UI", "exports": ""},
        {"path": "README.md", "description": "실행 방법", "exports": ""},
    ]


def _collect_team_brief(task: str, context: str = ""):
    """팀 전원 의견을 순차 수집하는 제너레이터.
    각 에이전트는 앞 사람의 발언을 보고 겹치지 않는 관점을 추가.
    마지막에 {"__brief__": (brief_str, results_dict)} 를 yield."""
    ctx_note = f"\n\n참고:\n{context}" if context else ""
    results = {}

    for aid in AGENTS:
        prev = "\n".join(
            f"{AGENTS[a]['name']}: {results[a]}" for a in AGENTS if a in results
        )
        prev_note = f"\n\n이미 나온 의견:\n{prev}" if prev else ""

        yield sse({"type": "thinking", "agent": aid})
        try:
            text, _ = agent_call(aid, task,
                f"프로젝트: {task}{ctx_note}{prev_note}\n\n"
                f"당신만의 관점에서 핵심 포인트 1가지만. 80자 이내.", 80)
            results[aid] = text
            yield sse({"type": "response", "agent": aid, "content": text, "ctx": "plan"})
        except Exception:
            pass

    brief = "\n".join(
        f"{AGENTS[a]['name']} ({AGENTS[a]['role']}): {results[a]}"
        for a in AGENTS if a in results
    )
    yield BriefSignal(brief=brief, results=results)


def write_project_docs(task: str, workspace: str, feedback: str = "", consensus: str = "", rag_context: str = ""):
    revision_note = f"\n\n수정 피드백 반영: {feedback}" if feedback else ""
    consensus_note = f"\n\n【팀 합의 방향 — 반드시 반영】\n{consensus}" if consensus else ""
    rag_note = f"\n\n【과거 유사 프로젝트 참고】\n{rag_context}" if rag_context else ""

    # ── Step 1: 팀 전원 의견 순차 수집 ───────────────────────────
    team_brief = ""
    for item in _collect_team_brief(task, (rag_context + "\n\n" + consensus).strip() if rag_context else consensus):
        if isinstance(item, BriefSignal):
            team_brief = item.brief
        else:
            yield item

    team_brief_block = f"\n\n【팀 전원 의견 — 모두 반영할 것】\n{team_brief}" if team_brief else ""

    # ── Step 2: 문서 작성 (각자 전문 영역 담당, 팀 의견 전부 포함) ──
    doc_assignments = [
        ("jimin", "docs/01_요구사항정의서.md",
         f"태스크: {task}{rag_note}{consensus_note}{team_brief_block}{revision_note}\n\n"
         f"위 팀 전원의 의견을 빠짐없이 반영하여 요구사항정의서를 마크다운으로 작성하세요.\n"
         f"포함: 프로젝트 개요, 기능 요구사항, 비기능 요구사항, 제약사항, 우선순위"),
        ("suyoung", "docs/02_기술설계서.md",
         f"태스크: {task}{rag_note}{consensus_note}{team_brief_block}{revision_note}\n\n"
         f"위 팀 전원의 의견을 빠짐없이 반영하여 기술 설계서를 마크다운으로 작성하세요.\n"
         f"포함: 시스템 아키텍처, 기술 스택, API 설계, DB 구조, AI 파이프라인"),
        ("junhyuk", "docs/03_시장조사보고서.md",
         f"태스크: {task}{rag_note}{consensus_note}{team_brief_block}{revision_note}\n\n"
         f"위 팀 전원의 의견을 빠짐없이 반영하여 시장조사보고서를 마크다운으로 작성하세요.\n"
         f"포함: 시장 규모(TAM/SAM/SOM), 경쟁사 분석, 타겟 고객, 수익 모델, 리스크"),
        ("yujin", "docs/04_진행계획서.md",
         f"태스크: {task}{rag_note}{consensus_note}{team_brief_block}{revision_note}\n\n"
         f"위 팀 전원의 의견을 빠짐없이 반영하여 진행 계획서를 마크다운으로 작성하세요.\n"
         f"포함: 마일스톤, MVP 범위, v2 범위, 자동화 항목, 예상 일정"),
    ]

    for agent_id, filename, _ in doc_assignments:
        doc_label = f"{filename} (수정)" if feedback else filename
        yield sse({"type": "writing_doc", "agent": agent_id, "doc": doc_label})

    docs_content = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_map = {}
        for agent_id, filename, prompt in doc_assignments:
            future_map[executor.submit(doc_call, agent_id, task, prompt, 1500)] = (agent_id, filename)
            time.sleep(_CALL_STAGGER)
        for future in as_completed(future_map):
            agent_id, filename = future_map[future]
            try:
                content = future.result()
            except Exception as e:
                content = f"# 생성 실패\n\n{e}"
                yield sse({"type": "error", "msg": f"{filename} 생성 실패: {e}"})
            write_workspace(workspace, filename, content)
            docs_content[filename] = {"agent": agent_id, "content": content}
            yield sse({"type": "doc_saved", "agent": agent_id,
                       "file": filename, "path": f"{workspace}/{filename}"})

    yield DocsSignal(docs=docs_content)


def write_code_files(task: str, workspace: str, doc_summary: str,
                     review_feedback: str = "", prev_generated: dict = None,
                     prev_file_plan: list = None, arch_consensus: str = ""):
    if prev_generated is None:
        # ── 파일 구조 설계 ─────────────────────────────────────────
        yield sse({"type": "thinking", "agent": "suyoung"})
        yield sse({"type": "writing_doc", "agent": "suyoung", "doc": "코드 구조 설계 중..."})
        file_plan = plan_code_structure(task, doc_summary, arch_consensus)
        yield sse({"type": "code_structure", "files": [f["path"] for f in file_plan]})

        # ── 팀 전원 코드 요구사항 순차 수집 ──────────────────────
        ctx_str = (
            f"파일 구조:\n" + "\n".join(f["path"] for f in file_plan) +
            (f"\n\n아키텍처 합의:\n{arch_consensus}" if arch_consensus else "")
        )
        code_brief = ""
        for item in _collect_team_brief(task, ctx_str):
            if isinstance(item, BriefSignal):
                code_brief = item.brief
            else:
                yield item

        generated: dict[str, str] = {}
    else:
        file_plan = prev_file_plan or [{"path": p, "description": "수정"}
                                       for p in prev_generated.keys()]
        generated = dict(prev_generated)
        code_brief = ""

    feedback_note = f"\n\n코드리뷰 피드백 반영: {review_feedback}" if review_feedback else ""
    code_brief_block = f"\n\n【팀 전원 코드 요구사항 — 반드시 반영】\n{code_brief}" if code_brief else ""

    interface_map = "\n".join(
        f"- {fi['path']}: {fi.get('exports') or fi['description']}"
        for fi in file_plan
    )

    for file_info in file_plan:
        doc_label = f"{file_info['path']} (수정)" if review_feedback else file_info['path']
        agent_id = _pick_code_agent(file_info['path'])
        yield sse({"type": "writing_doc", "agent": agent_id, "doc": doc_label})

    def make_code_prompt(fpath: str, fdesc: str) -> tuple[str, str]:
        agent_id = _pick_code_agent(fpath)
        is_frontend = agent_id == "mina"

        interface_ctx = (
            f"【프로젝트 파일 인터페이스 — import 시 반드시 이 구조를 따르세요】\n"
            f"{interface_map}\n\n"
        )
        if is_frontend:
            prompt = (
                f"당신은 민아입니다. AX팀 프론트엔드 개발자.\n"
                f"{interface_ctx}"
                f"{code_brief_block}\n\n"
                f"파일: `{fpath}` — {fdesc}\n"
                f"- 깔끔하고 사용하기 편한 UI\n"
                f"- 순수 HTML/CSS/JS (프레임워크 없이)\n"
                f"- fetch로 백엔드 API 연동\n"
                f"- 설명 없이 코드만. 첫 줄부터 바로 <!DOCTYPE html> 시작\n"
                f"- 반드시 코드 블록(```)으로 감싸세요"
                f"{feedback_note}"
            )
        else:
            prompt = (
                f"{interface_ctx}"
                f"{code_brief_block}\n\n"
                f"파일: `{fpath}` — {fdesc}\n"
                f"- 완전하고 실행 가능하게 작성\n"
                f"- 설명 텍스트 금지. 코드만 출력\n"
                f"- 반드시 코드 블록(```)으로 감싸세요"
                f"{feedback_note}"
            )
        return prompt, agent_id

    def generate_file(fi: dict) -> tuple[str, str, str]:
        fpath = fi["path"]
        prompt, agent_id = make_code_prompt(fpath, fi["description"])
        full_prompt = f"프로젝트 문서:\n{doc_summary[:600]}\n\n{prompt}"

        raw, truncated = doc_call(agent_id, task, full_prompt, max_tokens=8192, return_meta=True)
        code = extract_code(raw)

        # 잘림 감지 시 최대 3회 이어쓰기 (긴 파일도 대응)
        # API stop_reason=="max_tokens" 우선, 휴리스틱은 보조
        for _ in range(3):
            if not truncated and not is_truncated(code):
                break
            continuation_raw, truncated = doc_call(agent_id, task,
                f"다음 코드가 중간에 잘렸습니다. 잘린 부분 바로 다음부터 이어서 완성하세요.\n"
                f"```\n{code[-600:]}\n```\n"
                f"이어지는 코드만 코드 블록으로 출력하세요.",
                max_tokens=8192,
                return_meta=True,
            )
            continuation = extract_code(continuation_raw)
            if not continuation:
                break
            code = code + "\n" + continuation

        return fpath, agent_id, code

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_map = {}
        for fi in file_plan:
            future_map[executor.submit(generate_file, fi)] = fi
            time.sleep(_CALL_STAGGER)
        for future in as_completed(future_map):
            fi = future_map[future]
            fpath = fi["path"]
            try:
                fpath, agent_id, code = future.result()
            except Exception as e:
                agent_id = _pick_code_agent(fpath)
                code = f"# 생성 실패: {e}"
                yield sse({"type": "error", "msg": f"{fpath} 생성 실패: {e}"})
            write_workspace(workspace, fpath, code)
            generated[fpath] = code
            yield sse({"type": "doc_saved", "agent": agent_id,
                       "file": fpath, "path": f"{workspace}/{fpath}"})

    yield CodeSignal(file_plan=file_plan, generated=generated)


def fix_file(task: str, fpath: str, current_code: str,
             issues: list, all_generated: dict) -> str:
    issue_notes = "\n".join(
        f"- {iss['problem']}"
        for iss in issues if iss.get("file") == fpath
    )
    other_files = "\n\n".join(
        f"### {p}\n```\n{c[:400]}\n```"
        for p, c in all_generated.items() if p != fpath
    )
    agent_id = _pick_code_agent(fpath)
    return doc_call(agent_id, task,
        f"코드리뷰 지적사항:\n{issue_notes}\n\n"
        f"다른 파일들 (참고용):\n{other_files}\n\n"
        f"수정할 파일: `{fpath}`\n현재 코드:\n```\n{current_code}\n```\n\n"
        f"지적사항을 반영해서 이 파일만 수정하세요. 반드시 코드 블록으로 감싸세요.",
        max_tokens=8192
    )
