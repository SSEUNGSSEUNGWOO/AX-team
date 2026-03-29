# 공통 유틸 — Anthropic 클라이언트, SSE 포맷터, agent_call/doc_call API 래퍼

import json, re, queue, threading, contextvars, time, os
from typing import Generator, Any, Callable, TypeVar
import anthropic
from dotenv import load_dotenv
from agents import AGENTS

load_dotenv()

T = TypeVar("T")

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL_FAST  = "claude-haiku-4-5-20251001"  # 토론 발언, 짧은 반응
MODEL_SMART = "claude-sonnet-4-6"           # 문서/코드 생성, 판단, tool-use
MODEL = MODEL_SMART  # 하위 호환

# 현재 실행 중인 태스크의 첨부 파일 (이미지 or PDF)
# contextvars.ContextVar: 요청별 격리 + ThreadPoolExecutor 자동 전파
_attachment_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_attachment_var", default=None
)


def set_attachment(attachment: dict | None) -> None:
    _attachment_var.set(attachment)


def _build_content(text: str) -> list | str:
    """첨부 파일이 있으면 text + file block, 없으면 text 그대로."""
    attachment = _attachment_var.get()
    if attachment is None:
        return text
    media_type = attachment["media_type"]
    b64 = attachment["data"]
    if media_type == "application/pdf":
        file_block = {"type": "document", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    else:
        file_block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    return [{"type": "text", "text": text}, file_block]


def with_rate_limit_retry(fn: Callable[[], T], label: str = "", max_attempts: int = 3) -> T:
    """rate_limit 예외 시 exponential backoff으로 최대 max_attempts회 재시도.
    재시도 불가 예외나 시도 소진 시 그대로 raise."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < max_attempts - 1:
                wait = 15 * (2 ** attempt)  # 15s, 30s (exponential)
                print(f"[rate limit] {label} 재시도 {attempt + 1}/{max_attempts - 1} — {wait}s 대기")
                time.sleep(wait)
            else:
                raise


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def make_sse_stream(gen: Generator) -> Generator[str, None, None]:
    """제너레이터를 백그라운드 스레드에서 실행하고 15초마다 keepalive 전송.
    중간에 예외가 나도 error + done 이벤트를 보내고 깔끔하게 종료."""
    q = queue.Queue()
    ctx = contextvars.copy_context()  # Flask 요청 컨텍스트 스냅샷 (ContextVar 전파)

    def _worker():
        try:
            for item in gen:
                q.put(item)
        except Exception as e:
            q.put(sse({"type": "error", "msg": f"오류 발생: {e}"}))
            q.put(sse({"type": "done", "workspace": ""}))
        finally:
            q.put(None)

    threading.Thread(target=ctx.run, args=(_worker,), daemon=True).start()

    while True:
        try:
            item = q.get(timeout=15)
            if item is None:
                return
            yield item
        except queue.Empty:
            yield ": keepalive\n\n"


def parse_intention(text: str) -> dict[str, Any] | None:
    match = re.search(r'\[NEXT:\s*want:([\w]+)\|(.*?)\]', text)
    if match:
        return {"action": "want", "target": match.group(1), "reason": match.group(2).strip()}
    match = re.search(r'\[NEXT:\s*idle\|(.*?)\]', text)
    if match:
        return {"action": "idle", "target": None, "reason": match.group(1).strip()}
    return None


def strip_next(text: str) -> str:
    return re.sub(r'\[NEXT:.*?\]', '', text).strip()


def agent_call(agent_id: str, task: str, user_msg: str, max_tokens: int = 150) -> tuple[str, dict[str, Any] | None]:
    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=max_tokens,
        system=f"현재 태스크: {task}\n\n{AGENTS[agent_id]['system']}",
        messages=[{"role": "user", "content": _build_content(user_msg)}],
    )
    raw = resp.content[0].text
    return strip_next(raw), parse_intention(raw)


def doc_call(agent_id: str, task: str, prompt: str, max_tokens: int = 800,
             return_meta: bool = False):
    """문서/코드 생성 전용 — rate limit 대응: 기본 1200토큰 + 429 시 재시도.
    return_meta=True 시 (text, truncated: bool) 튜플 반환."""
    base_system = AGENTS[agent_id]['system'].split('[NEXT')[0]
    # 토론용 글자수 제한 제거 (문서/코드 생성에는 적용 안 함)
    base_system = re.sub(r'반드시 한국어로.*?끝낼 것\.\n?', '', base_system)
    base_system = re.sub(r'토론 중 코드 작성 금지[^\n]*\n?', '', base_system).strip()

    def _call():
        return client.messages.create(
            model=MODEL_SMART,
            max_tokens=max_tokens,
            system=f"현재 태스크: {task}\n\n{base_system}",
            messages=[{"role": "user", "content": _build_content(prompt)}],
        )

    resp = with_rate_limit_retry(_call, label=agent_id)
    text = resp.content[0].text
    if return_meta:
        return text, resp.stop_reason == "max_tokens"
    return text


def tool_agent_call(agent_id: str, task: str, prompt: str,
                    workspace: str = "", max_tokens: int = 500,
                    max_rounds: int = 3, model: str = None) -> str:
    """도구 사용 가능한 에이전트 호출 — 생각→도구호출→관찰 루프 (ReAct).
    최종 텍스트 응답 반환. rate limit 시 exponential backoff 재시도.
    model 미지정 시 MODEL_SMART(Sonnet) 사용. 단순 발언은 MODEL_FAST(Haiku) 전달 가능."""
    from tools import TOOL_DEFINITIONS, execute_tool

    model_to_use = model or MODEL_SMART
    base_system = AGENTS[agent_id]['system'].split('[NEXT')[0]
    base_system = re.sub(r'반드시 한국어로.*?끝낼 것\.\n?', '', base_system)
    base_system = re.sub(r'토론 중 코드 작성 금지[^\n]*\n?', '', base_system).strip()
    messages = [{"role": "user", "content": _build_content(prompt)}]

    for _ in range(max_rounds):
        resp = with_rate_limit_retry(
            lambda: client.messages.create(
                model=model_to_use,
                max_tokens=max_tokens,
                system=f"현재 태스크: {task}\n\n{base_system}",
                tools=TOOL_DEFINITIONS,
                messages=messages,
            ),
            label=f"tool_agent_call {agent_id}",
        )

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, workspace)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        else:  # end_turn
            for block in resp.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

    return ""


def review_call(agent_id: str, task: str, hist_text: str) -> tuple[str, bool]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=150,
        system=(
            f"현재 태스크: {task}\n\n"
            f"당신은 {AGENTS[agent_id]['name']}({AGENTS[agent_id]['role']})입니다. "
            f"성격: {AGENTS[agent_id]['personality']}\n"
            f"반드시 JSON으로만 답하세요: "
            f'{{\"satisfied\": true 또는 false, \"feedback\": \"한 줄 피드백\"}}'
        ),
        messages=[{"role": "user", "content": f"지금까지 팀 작업 결과:\n{hist_text}\n\n충분한가요?"}],
    )
    text = resp.content[0].text
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("feedback", text[:80]), bool(data.get("satisfied", False))
        except Exception:
            pass
    satisfied = any(w in text for w in ["충분", "좋아", "완료", "만족", "됐"])
    return text[:80], satisfied
