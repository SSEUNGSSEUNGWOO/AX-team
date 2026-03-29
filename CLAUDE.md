# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실행 방법

```bash
# 의존성 설치
pip install flask anthropic supabase python-dotenv chromadb

# .env 파일 필요
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_KEY=...

# 서버 실행
python3 app.py
# → http://localhost:5001

# 테스트 실행
pytest tests/ -v
# 또는 단일 파일
pytest tests/test_workspace_utils.py -v
```

## 아키텍처 개요

Flask + SSE(Server-Sent Events) 기반 AI 팀 협업 시뮬레이터. 태스크를 입력하면 6명의 AI 에이전트가 토론·투표·생성 과정을 실시간 스트리밍으로 처리한다.

### 핵심 데이터 흐름

```
POST /api/team-task
  → runner.py: run_autonomous_task()
      → rag.py: search()               ← 과거 유사 프로젝트 벡터 검색 (chromadb)
      → deliberation.py: classify_task()  ← Claude API로 태스크 분류
      → 킥오프: 6명 병렬 첫 반응
      → workflows.py: _run_build / _run_feedback / _run_review / _run_discuss / _run_plan
          → deliberation.py: deliberate()  ← 순차 토론 + ConsensusSignal 반환
          → generation.py: write_project_docs() / write_code_files()  ← 병렬 문서/코드 생성
          → deliberation.py: team_gate()  ← 6명 PASS/BLOCK 투표 (1명이라도 BLOCK이면 재시도)
      → rag.py: index_workspace()      ← 결과물을 벡터 DB에 저장
  → SSE 스트림으로 프론트엔드에 실시간 전달
```

### SSE 이벤트 타입

모든 응답은 `utils.py:sse()` 로 포맷팅된 JSON. 주요 타입:
- `workflow` — 분류된 워크플로우 타입과 페이즈 목록
- `thinking` — 에이전트 로딩 표시
- `response` — 에이전트 발언 (`ctx`: kickoff/debate/gate/analyze/bilateral/requirement)
- `consensus` — 합의 체크리스트 (팀원별 핵심 요구사항)
- `gate` — team_gate 투표 결과 (`passed`, `block_reasons`)
- `writing_doc` / `doc_saved` — 파일 생성 중/완료
- `round` — 현재 라운드 번호와 라벨
- `synthesis` / `done` — 최종 결론 및 워크플로우 완료

### generator 패턴과 Signal 타입

워크플로우 함수들은 모두 Python generator. `str` 아이템은 클라이언트로 전송할 SSE 문자열, `Signal` 인스턴스는 generator 간 내부 제어 신호다. `signals.py`에 정의된 타입:
- `ConsensusSignal` — `deliberate()` → 호출자: 합의 체크리스트 전달
- `GateSignal` — `team_gate()` → `_run_team_gate()`: 투표 결과 전달
- `GateResultSignal` — `_run_team_gate()` → 워크플로우: 최종 게이트 통과 여부
- `DocsSignal` — `write_project_docs()` → 워크플로우: 생성된 문서 dict 전달
- `CodeSignal` — `write_code_files()` → 워크플로우: 파일 플랜 + 코드 dict 전달
- `BriefSignal` — `_collect_team_brief()` → 호출자: 팀 전원 의견 요약 전달

`make_sse_stream()`이 generator를 백그라운드 스레드에서 실행하며 15초마다 keepalive를 전송한다.

### 에이전트 API 호출 구분

- `agent_call()` — 짧은 발언 (토론, 반응). `MODEL_FAST`(Haiku) 사용. 기본 150 토큰. `[NEXT: want:대상|이유]` 의도 파싱 포함.
- `doc_call()` — 문서/코드 생성. `MODEL_SMART`(Sonnet) 사용. 기본 800~1500 토큰. rate limit 시 exponential backoff(15s→30s) 최대 3회 재시도.
- `tool_agent_call()` — ReAct 루프 (생각→도구호출→관찰). 기본 `MODEL_SMART`, 단순 발언은 `MODEL_FAST` 지정 가능. `tools.py`의 `read_file` / `list_files` / `search_memory` 도구 사용.

`deliberate()` 내에서 첫 발언은 `tool_agent_call` + `MODEL_SMART`(파일 조사), 이후 발언은 `tool_agent_call` + `MODEL_FAST`(빠른 반응).

### 병렬 생성 설정

```python
# generation.py 및 deliberation.py 공통
_CALL_STAGGER = 2.0   # 콜 제출 간격 (초)
_MAX_WORKERS  = 3     # 동시 최대 API 콜 수 (generation.py)
```
rate limit 발생 시 이 값을 조정한다.

### RAG 시스템

`rag.py`는 chromadb(로컬 `./rag_store/`)를 사용해 완료된 태스크 결과물을 벡터화·검색한다.
- `search(query)` — 유사 과거 프로젝트 검색 → 프롬프트 주입용 문자열 반환
- `index_workspace(workspace, task, type)` — 태스크 완료 후 결론 + 기획 문서를 인덱싱

### 워크스페이스 구조

태스크 실행마다 `workspace/NN-{type}-{slug}/` 폴더 생성:
- `docs/` — 기획 문서 4종 (요구사항, 기술설계, 시장조사, 진행계획)
- `code/` — 생성된 코드 파일들
- `00_결론.md` — 승우 최종 결론

### DB (Supabase)

`db.py`는 세션(`sessions`)과 메시지(`messages`) 테이블만 사용. 스키마는 `migrations/schema.sql`. DB 오류는 워크플로우를 중단시키지 않고 `print`로만 로깅한다.

### 첨부 파일

`utils.py`의 `_attachment_var`(`contextvars.ContextVar`)가 현재 태스크의 이미지/PDF를 요청별 격리로 보관. `set_attachment()`로 설정하고 태스크 완료 후 `None`으로 초기화. `_build_content()`가 Claude API 메시지에 파일 블록을 추가한다.

## 워크플로우별 특징

| 타입 | 라운드 | 특징 |
|------|--------|------|
| `build` | 기획→개발→검증 | team_gate 최대 3회 재시도, 실패 시 지적 파일만 타겟 수정 |
| `feedback` | 심층분석→교차토론→보고서 | 전원 개별 분석 후 deliberate |
| `review` | 전문검토→이슈토론→보고서 | CRITICAL/MAJOR/MINOR 분류 |
| `discuss` | 입장표명→다자토론→결론 | deliberate 3라운드 |
| `plan` | 방향토론→범위합의→문서작성 | write_project_docs 후 team_gate |

## 에이전트 구성 (`agents.py`)

6명: 승우(lead·속도파), 지민(백엔드·품질파), 주혁(혁신파), 유진(실용파·YAGNI), 수영(백엔드·AI·아키텍처파), 민아(프론트·사용자파). `WORKFLOW_AGENTS`로 워크플로우별 토론 참여자 서브셋 지정. `main.py`(루트)는 사용되지 않는 레거시 CLI 스텁.
