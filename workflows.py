# 워크플로우 — 태스크 타입별 실행 흐름 (build: 3라운드, feedback/review, discuss, plan)

import os, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents import AGENTS, WORKFLOW_AGENTS
from signals import ConsensusSignal, GateSignal, GateResultSignal, DocsSignal, CodeSignal
from utils import sse, agent_call, doc_call
from workspace_utils import write_workspace, extract_code, check_syntax
from generation import write_project_docs, write_code_files, fix_file
from deliberation import deliberate, quick_react, team_gate


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────

def _extract_consensus(gen):
    """deliberate() generator 소비 헬퍼 — SSE는 yield하고 ConsensusSignal은 buf[0]에 저장."""
    buf = [None]

    def _inner():
        for item in gen:
            if isinstance(item, ConsensusSignal):
                buf[0] = item.consensus
            else:
                yield item

    return _inner(), buf


def _run_team_gate(task, artifact_summary, round_label, round_num,
                   attempt=None, consensus="", workspace=""):
    """team_gate generator를 소비하고 gate SSE를 yield한 뒤 GateResultSignal을 yield하는 헬퍼."""
    can_proceed, block_reasons, summary = True, [], ""
    for item in team_gate(task, artifact_summary, round_label, consensus, workspace):
        if isinstance(item, GateSignal):
            can_proceed, block_reasons, summary = item.can_proceed, item.block_reasons, item.summary
        else:
            yield item
    extra = {"attempt": attempt} if attempt is not None else {}
    yield sse({"type": "gate", "round": round_num, "passed": can_proceed,
               "summary": summary, "block_reasons": block_reasons, **extra})
    yield GateResultSignal(can_proceed=can_proceed, block_reasons=block_reasons)


def _collect_individual_analysis(task: str, make_prompt, max_tokens: int = 200,
                                  ctx_key: str = "analyze"):
    """에이전트별 개인 분석/발언을 순차 수집하는 공통 헬퍼.

    make_prompt: callable(agent_id: str, prev_results: dict) -> str
        앞 에이전트의 결과를 참고해 각 에이전트의 프롬프트를 동적으로 생성한다.

    Yields SSE events. results dict를 generator return value로 반환
    (호출자에서 `results = yield from _collect_individual_analysis(...)` 형태로 사용).
    """
    results: dict[str, str] = {}

    for aid in AGENTS:
        yield sse({"type": "thinking", "agent": aid})
        prompt = make_prompt(aid, results)
        try:
            text = doc_call(aid, task, prompt, max_tokens=max_tokens)
            results[aid] = text
            yield sse({"type": "response", "agent": aid, "content": text, "ctx": ctx_key})
        except Exception:
            pass
        time.sleep(2.0)

    return results  # 호출자에서 yield from 표현식 값으로 수신


def _consume_docs(gen):
    """write_project_docs() generator 소비 헬퍼 — SSE는 yield하고 docs dict를 buf[0]에 저장."""
    buf = [{}]

    def _inner():
        for item in gen:
            if isinstance(item, DocsSignal):
                buf[0] = item.docs
            else:
                yield item

    return _inner(), buf


def _consume_code(gen):
    """write_code_files() generator 소비 헬퍼 — SSE는 yield하고 (file_plan, generated)를 buf[0]에 저장."""
    buf = [(None, {})]

    def _inner():
        for item in gen:
            if isinstance(item, CodeSignal):
                buf[0] = (item.file_plan, item.generated)
            else:
                yield item

    return _inner(), buf


def _identify_files_to_fix(task: str, block_reasons: str, generated: dict) -> list[str]:
    file_list = "\n".join(generated.keys())
    resp = doc_call("suyoung", task,
        f"다음 문제가 지적됐다:\n{block_reasons}\n\n"
        f"파일 목록:\n{file_list}\n\n"
        f"수정이 필요한 파일 경로만 줄바꿈으로 반환. 다른 텍스트 없이.",
        max_tokens=100
    )
    return [line.strip() for line in resp.strip().split('\n')
            if line.strip() in generated][:3]


# ── 워크플로우 구현 ────────────────────────────────────────────────────────

def _run_build(task: str, workspace: str, save_fn, rag_context: str = ""):
    docs_content = {}
    generated = {}
    file_plan = None

    # ── Round 1: 기획 ─────────────────────────────────────────
    yield sse({"type": "round", "round": 1, "label": "기획", "total": 3})

    direction_topic = f"'{task}' 프로젝트의 핵심 방향, 접근 방식, 주요 리스크를 논의하세요."
    if rag_context:
        direction_topic = f"{rag_context}\n\n{direction_topic}"

    stream, buf = _extract_consensus(deliberate(
        task,
        direction_topic,
        WORKFLOW_AGENTS["build"]["direction"], rounds=2, workspace=workspace,
    ))
    yield from stream
    direction_consensus = buf[0] or ""

    for attempt in range(1, 4):
        docs_stream, docs_buf = _consume_docs(
            write_project_docs(task, workspace, consensus=direction_consensus, rag_context=rag_context)
        )
        yield from docs_stream
        docs_content = docs_buf[0]

        doc_summary_short = "\n".join(
            f"{k}: {v['content'][:200]}" for k, v in docs_content.items()
        )
        can_proceed, block_reasons = True, []
        for item in _run_team_gate(task, doc_summary_short, "Round 1 기획", 1, attempt, direction_consensus, workspace):
            if isinstance(item, GateResultSignal):
                can_proceed, block_reasons = item.can_proceed, item.block_reasons
            else:
                yield item

        if can_proceed:
            break

        block_text = "\n".join(block_reasons)
        stream, buf = _extract_consensus(deliberate(
            task, f"다음 문제 개선 방법 논의:\n{block_text}",
            WORKFLOW_AGENTS["build"]["retry"], rounds=1, workspace=workspace,
        ))
        yield from stream
        direction_consensus = buf[0] or ""

    if not can_proceed:
        yield sse({"type": "error", "msg": f"기획 검증 3회 실패 — 작업 중단: {block_text}"})
        yield sse({"type": "done", "workspace": workspace, "failed": True})
        return

    # ── Round 2: 개발 ─────────────────────────────────────────
    yield sse({"type": "round", "round": 2, "label": "개발", "total": 3})

    doc_summary = "\n\n".join(
        f"### {k}\n{v['content'][:400]}" for k, v in docs_content.items()
    )

    stream, buf = _extract_consensus(deliberate(
        task,
        f"문서 요약:\n{doc_summary[:500]}\n\n코드 구조와 핵심 기술 결정을 논의하세요.",
        WORKFLOW_AGENTS["build"]["arch"], rounds=1, workspace=workspace,
    ))
    yield from stream
    arch_consensus = buf[0] or ""

    for attempt in range(1, 4):
        code_stream, code_buf = _consume_code(write_code_files(
            task, workspace, doc_summary,
            arch_consensus=arch_consensus if attempt == 1 else "",
            prev_generated=generated if attempt > 1 else None,
            prev_file_plan=file_plan if attempt > 1 else None,
        ))
        yield from code_stream
        new_plan, generated = code_buf[0]
        if new_plan:
            file_plan = new_plan

        code_summary = "\n".join(
            f"{k}: {v[:150]}" for k, v in list(generated.items())[:5]
        )
        can_proceed, block_reasons = True, []
        for item in _run_team_gate(task, code_summary, "Round 2 개발", 2, attempt, arch_consensus, workspace):
            if isinstance(item, GateResultSignal):
                can_proceed, block_reasons = item.can_proceed, item.block_reasons
            else:
                yield item

        if can_proceed:
            break

        block_text = "\n".join(block_reasons)
        for aid, text in quick_react(task, f"코드 반려됨: {block_text}",
                                     ["suyoung", "yujin"], max_agents=2, skip_chance=0.1):
            yield sse({"type": "response", "agent": aid, "content": text})

        files_to_fix = _identify_files_to_fix(task, block_text, generated)
        if files_to_fix:
            issues = [{"file": fp, "problem": block_text} for fp in files_to_fix]
            for fp in files_to_fix:
                yield sse({"type": "writing_doc", "agent": "suyoung", "doc": f"{fp} (수정)"})
            with ThreadPoolExecutor(max_workers=3) as executor:
                fix_futures = {}
                for fp in files_to_fix:
                    if fp in generated:
                        fix_futures[executor.submit(fix_file, task, fp,
                                                    generated.get(fp, ""), issues, generated)] = fp
                        time.sleep(2.0)  # rate limit 방지
                for future in as_completed(fix_futures):
                    fp = fix_futures[future]
                    try:
                        fixed = extract_code(future.result())
                        write_workspace(workspace, fp, fixed)
                        generated[fp] = fixed
                        yield sse({"type": "doc_saved", "agent": "suyoung",
                                   "file": fp, "path": f"{workspace}/{fp}"})
                    except Exception as e:
                        yield sse({"type": "error", "msg": f"{fp} 수정 실패: {e}"})

    if not can_proceed:
        yield sse({"type": "error", "msg": f"코드 검증 3회 실패 — 작업 중단: {block_text}"})
        yield sse({"type": "done", "workspace": workspace, "failed": True})
        return

    # ── Round 3: 검증 ─────────────────────────────────────────
    yield sse({"type": "round", "round": 3, "label": "검증", "total": 3})

    file_list = "\n".join(f"- {p}" for p in generated.keys()) if generated else "파일 없음"
    yield sse({"type": "writing_doc", "agent": "mina", "doc": "결과보고서.md"})
    try:
        report = doc_call("mina", task,
            f"태스크: {task}\n\n생성된 파일:\n{file_list}\n\n"
            f"프로젝트 결과보고서 작성. 포함: 요약, 주요 결정사항, 결과물 목록, 실행 방법, 다음 단계")
    except Exception as e:
        report = f"# 결과보고서\n\n생성 실패: {e}"
    write_workspace(workspace, "docs/결과보고서.md", report)
    yield sse({"type": "doc_saved", "agent": "mina",
               "file": "docs/결과보고서.md", "path": f"{workspace}/docs/결과보고서.md"})

    final_summary = f"파일 목록:\n{file_list}\n\n결과보고서:\n{report[:400]}"
    combined_consensus = f"{direction_consensus}\n\n{arch_consensus}".strip()
    for item in _run_team_gate(task, final_summary, "Round 3 검증", 3, consensus=combined_consensus, workspace=workspace):
        if isinstance(item, GateResultSignal):
            pass
        else:
            yield item

    final, _ = agent_call("lead", task,
        f"프로젝트가 완료됐습니다. 결과물:\n{file_list}\n\n최종 결론 한 줄.")
    save_fn("lead", final, "synthesis")
    write_workspace(workspace, "00_결론.md", final)
    yield sse({"type": "synthesis", "content": final, "agent": "lead",
               "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})


def _run_feedback(task: str, workspace: str, save_fn, rag_context: str = ""):
    # ── Round 1: 심층 개인 분석 ───────────────────────────────────
    yield sse({"type": "round", "round": 1, "label": "심층 분석", "total": 3})

    def make_analysis_prompt(aid, prev_results):
        prev = "\n".join(
            f"{AGENTS[a]['name']}: {prev_results[a]}" for a in AGENTS if a in prev_results
        )
        prev_note = f"\n\n이미 나온 분석:\n{prev}" if prev else ""
        return (
            f"분석 대상:\n{task}\n\n"
            f"당신의 성향으로 핵심 강점 1가지, 가장 심각한 문제 1가지, 구체적 개선안 1가지. 150자 이내."
            f"{prev_note}"
        )

    analyses = yield from _collect_individual_analysis(
        task, make_analysis_prompt, max_tokens=200, ctx_key="analyze"
    )

    # ── Round 2: 교차 토론 ────────────────────────────────────────
    yield sse({"type": "round", "round": 2, "label": "교차 토론", "total": 3})

    analysis_summary = "\n".join(
        f"{AGENTS[a]['name']}: {t[:180]}" for a, t in analyses.items() if t
    )
    cross_topic = f"각자의 분석 결과:\n{analysis_summary}\n\n가장 중요한 개선사항 3개와 그 우선순위를 합의하세요."
    if rag_context:
        cross_topic = f"{rag_context}\n\n{cross_topic}"
    stream, buf = _extract_consensus(deliberate(
        task, cross_topic, list(AGENTS.keys()), rounds=2, workspace=workspace,
    ))
    yield from stream
    consensus = buf[0] or ""

    # ── Round 3: 보고서 작성 ──────────────────────────────────────
    yield sse({"type": "round", "round": 3, "label": "보고서 작성", "total": 3})

    yield sse({"type": "writing_doc", "agent": "jimin", "doc": "docs/피드백_분석보고서.md"})
    report = doc_call("jimin", task,
        f"분석 대상:\n{task}\n\n팀 분석:\n{analysis_summary}\n\n합의:\n{consensus}\n\n"
        f"피드백 보고서를 마크다운으로 작성하세요.\n"
        f"포함: 종합 평가, 강점, 개선 항목(우선순위), 액션아이템",
        max_tokens=1500)
    write_workspace(workspace, "docs/피드백_분석보고서.md", report)
    yield sse({"type": "doc_saved", "agent": "jimin", "file": "docs/피드백_분석보고서.md",
               "path": f"{workspace}/docs/피드백_분석보고서.md"})

    yield sse({"type": "writing_doc", "agent": "lead", "doc": "docs/액션아이템.md"})
    actions = doc_call("lead", task,
        f"팀 합의:\n{consensus}\n\n"
        f"액션아이템을 테이블로. 각 항목: 무엇을 | 우선순위 | 임팩트",
        max_tokens=400)
    write_workspace(workspace, "docs/액션아이템.md", actions)
    yield sse({"type": "doc_saved", "agent": "lead", "file": "docs/액션아이템.md",
               "path": f"{workspace}/docs/액션아이템.md"})

    final, _ = agent_call("lead", task,
        f"피드백 분석 완료. 핵심 합의:\n{consensus}\n\n최종 결론 한 줄.")
    save_fn("lead", final, "synthesis")
    write_workspace(workspace, "00_결론.md", final)
    yield sse({"type": "synthesis", "content": final, "agent": "lead", "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})


def _run_review(task: str, workspace: str, save_fn, rag_context: str = ""):
    # ── Round 1: 전문 영역별 검토 ─────────────────────────────────
    yield sse({"type": "round", "round": 1, "label": "전문 영역 검토", "total": 3})

    review_focus = {
        "suyoung": "아키텍처·코드 구조·확장성·기술 부채 관점에서 CRITICAL/MAJOR/MINOR로 분류해 리뷰하세요.",
        "jimin":   "코드 품질·테스트 커버리지·에러 처리·엣지 케이스 관점에서 CRITICAL/MAJOR/MINOR로 분류해 리뷰하세요.",
        "yujin":   "보안 취약점·성능 병목·불필요한 복잡성 관점에서 CRITICAL/MAJOR/MINOR로 분류해 리뷰하세요.",
        "junhyuk": "더 나은 기술·패턴 적용 가능성, 혁신 포인트를 CRITICAL/MAJOR/MINOR로 분류해 제안하세요.",
        "mina":    "사용자 경험·UI 일관성·접근성 관점에서 CRITICAL/MAJOR/MINOR로 분류해 리뷰하세요.",
        "lead":    "전체 완성도·즉시 수정 필수 이슈·실용성을 CRITICAL/MAJOR/MINOR로 분류해 리뷰하세요.",
    }

    def make_review_prompt(aid, prev_results):
        prev = "\n".join(
            f"{AGENTS[a]['name']}: {prev_results[a]}" for a in AGENTS if a in prev_results
        )
        prev_note = f"\n\n이미 나온 리뷰:\n{prev}" if prev else ""
        return (
            f"리뷰 대상:\n{task}\n\n{review_focus[aid]}\n"
            f"이슈마다 [CRITICAL]/[MAJOR]/[MINOR] 태그 붙여서 150자 이내."
            f"{prev_note}"
        )

    reviews = yield from _collect_individual_analysis(
        task, make_review_prompt, max_tokens=200, ctx_key="analyze"
    )

    # ── Round 2: 크리티컬 이슈 집중 토론 ─────────────────────────
    yield sse({"type": "round", "round": 2, "label": "크리티컬 이슈 토론", "total": 3})

    review_summary = "\n".join(
        f"{AGENTS[a]['name']}: {t[:180]}" for a, t in reviews.items() if t
    )
    review_topic = f"각자 리뷰 결과:\n{review_summary}\n\nCRITICAL 이슈 중 반드시 수정해야 할 것 3개를 선정하고 해결 방향을 합의하세요."
    if rag_context:
        review_topic = f"{rag_context}\n\n{review_topic}"
    stream, buf = _extract_consensus(deliberate(
        task, review_topic, list(AGENTS.keys()), rounds=2, workspace=workspace,
    ))
    yield from stream
    consensus = buf[0] or ""

    # ── Round 3: 리뷰 보고서 ─────────────────────────────────────
    yield sse({"type": "round", "round": 3, "label": "리뷰 보고서", "total": 3})

    yield sse({"type": "writing_doc", "agent": "suyoung", "doc": "docs/코드리뷰_보고서.md"})
    report = doc_call("suyoung", task,
        f"리뷰 대상:\n{task}\n\n팀 리뷰:\n{review_summary}\n\n합의:\n{consensus}\n\n"
        f"코드리뷰 보고서를 마크다운으로. 포함: 총평, 이슈 목록(CRITICAL/MAJOR/MINOR), 수정 권고",
        max_tokens=1500)
    write_workspace(workspace, "docs/코드리뷰_보고서.md", report)
    yield sse({"type": "doc_saved", "agent": "suyoung", "file": "docs/코드리뷰_보고서.md",
               "path": f"{workspace}/docs/코드리뷰_보고서.md"})

    final, _ = agent_call("lead", task,
        f"코드리뷰 완료. 핵심 수정사항:\n{consensus}\n\n리뷰 결론 한 줄.")
    save_fn("lead", final, "synthesis")
    write_workspace(workspace, "00_리뷰결론.md", final)
    yield sse({"type": "synthesis", "content": final, "agent": "lead", "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})


def _run_discuss(task: str, workspace: str, save_fn, rag_context: str = ""):
    # ── Round 1: 초기 입장 표명 ───────────────────────────────────
    yield sse({"type": "round", "round": 1, "label": "초기 입장 표명", "total": 3})

    def make_position_prompt(aid, prev_results):
        prev = "\n".join(
            f"{AGENTS[a]['name']}: {prev_results[a]}" for a in AGENTS if a in prev_results
        )
        prev_note = f"\n\n이미 나온 입장:\n{prev}" if prev else ""
        return (
            f"토론 주제: {task}\n\n"
            f"당신의 입장과 핵심 근거 1가지. 100자 이내."
            f"{prev_note}"
        )

    positions = yield from _collect_individual_analysis(
        task, make_position_prompt, max_tokens=150, ctx_key="debate"
    )

    # ── Round 2: 다자 토론 ────────────────────────────────────────
    yield sse({"type": "round", "round": 2, "label": "다자 토론", "total": 3})

    pos_summary = "\n".join(
        f"{AGENTS[a]['name']}: {t[:180]}" for a, t in positions.items() if t
    )
    discuss_topic = f"각자의 초기 입장:\n{pos_summary}\n\n핵심 쟁점을 집중 공략하세요. 상대방 이름을 직접 언급하며 반박하거나 지지하세요."
    if rag_context:
        discuss_topic = f"{rag_context}\n\n{discuss_topic}"
    stream, buf = _extract_consensus(deliberate(
        task, discuss_topic, list(AGENTS.keys()), rounds=3, workspace=workspace,
    ))
    yield from stream
    conclusion = buf[0] or ""

    # ── Round 3: 결론 도출 ────────────────────────────────────────
    yield sse({"type": "round", "round": 3, "label": "결론 도출", "total": 3})

    all_pos = "\n".join(
        f"{AGENTS[a]['name']}: {t[:200]}" for a, t in positions.items() if t
    )
    yield sse({"type": "writing_doc", "agent": "lead", "doc": "docs/토론_결과.md"})
    discussion_doc = doc_call("lead", task,
        f"토론 주제: {task}\n\n각자 입장:\n{all_pos}\n\n결론:\n{conclusion}\n\n"
        f"토론 결과 보고서를 마크다운으로. 포함: 요약, 핵심 주장, 합의된 결론, 소수의견",
        max_tokens=1200)
    write_workspace(workspace, "docs/토론_결과.md", discussion_doc)
    yield sse({"type": "doc_saved", "agent": "lead", "file": "docs/토론_결과.md",
               "path": f"{workspace}/docs/토론_결과.md"})

    final, _ = agent_call("lead", task,
        f"토론 마무리. 결론:\n{conclusion}\n\n최종 결론 한 줄.")
    save_fn("lead", final, "synthesis")
    write_workspace(workspace, "00_결론.md", final)
    yield sse({"type": "synthesis", "content": final, "agent": "lead", "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})


def _run_plan(task: str, workspace: str, save_fn, rag_context: str = ""):
    # ── Round 1: 방향 토론 ────────────────────────────────────────
    yield sse({"type": "round", "round": 1, "label": "방향 토론", "total": 3})

    plan_topic = f"'{task}' — 핵심 방향, 주요 가정, 가장 큰 리스크를 토론하세요."
    if rag_context:
        plan_topic = f"{rag_context}\n\n{plan_topic}"
    stream, buf = _extract_consensus(deliberate(
        task, plan_topic, list(AGENTS.keys()), rounds=2, workspace=workspace,
    ))
    yield from stream
    direction_consensus = buf[0] or ""

    # ── Round 2: 범위·우선순위 합의 ──────────────────────────────
    yield sse({"type": "round", "round": 2, "label": "범위·우선순위 합의", "total": 3})

    stream, buf = _extract_consensus(deliberate(
        task,
        f"합의된 방향:\n{direction_consensus}\n\n"
        f"MVP에 반드시 들어갈 것, v2로 미룰 것, 절대 하지 않을 것을 구체적으로 정하세요.",
        WORKFLOW_AGENTS["plan"]["scope"], rounds=2, workspace=workspace,
    ))
    yield from stream
    scope_consensus = buf[0] or ""

    # ── Round 3: 기획 문서 작성 ───────────────────────────────────
    yield sse({"type": "round", "round": 3, "label": "기획 문서 작성", "total": 3})

    combined = f"{direction_consensus}\n\n범위 합의:\n{scope_consensus}"
    docs_stream, docs_buf = _consume_docs(write_project_docs(task, workspace, consensus=combined))
    yield from docs_stream
    docs_content = docs_buf[0]

    doc_summary_short = "\n".join(
        f"{k}: {v['content'][:200]}" for k, v in docs_content.items()
    )
    can_proceed, block_reasons = True, []
    for item in _run_team_gate(task, doc_summary_short, "기획 완료", 3, consensus=combined, workspace=workspace):
        if isinstance(item, GateResultSignal):
            can_proceed, block_reasons = item.can_proceed, item.block_reasons
        else:
            yield item

    if not can_proceed:
        block_text = "; ".join(block_reasons)
        yield sse({"type": "error", "msg": f"기획 검증 미통과 — 작업 중단: {block_text}"})
        yield sse({"type": "done", "workspace": workspace, "failed": True})
        return

    summary = scope_consensus or direction_consensus or "기획 문서 작성 완료"
    save_fn("lead", summary, "synthesis")
    yield sse({"type": "synthesis", "content": summary, "agent": "lead",
               "workspace": workspace})
    yield sse({"type": "done", "workspace": workspace})
