# AX Team Office

6명의 AI 에이전트가 실제 팀처럼 **토론하고, 반대하고, 합의**해서 프로젝트 문서와 코드를 자동 생성하는 멀티 에이전트 협업 시뮬레이터.

단순한 프롬프트 체인이 아니다. 에이전트들은 서로의 발언을 보고 반응하며, 품질 기준을 충족하지 못하면 전원 투표로 재작성을 요구한다. 모든 과정은 SSE(Server-Sent Events)로 브라우저에 실시간 스트리밍된다.

![AX Team Office 화면](docs/screenshot.png)

---

## 목차

1. [팀 구성](#1-팀-구성)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [워크플로우 설계](#3-워크플로우-설계)
4. [핵심 기술적 도전](#4-핵심-기술적-도전)
5. [실제 생성 사례](#5-실제-생성-사례)
6. [개발 과정 (v1 → v5)](#6-개발-과정-v1--v5)
7. [한계 및 향후 계획](#7-한계-및-향후-계획)
8. [실행 방법](#8-실행-방법)
9. [디렉토리 구조](#9-디렉토리-구조)

---

## 1. 팀 구성

역할 분리 대신 **성향 차이**로 설계했다. 같은 태스크에도 다른 관점이 충돌해야 실제 토론처럼 느껴지기 때문이다.

| 이름 | 성향 | 한 마디 |
|------|------|---------|
| 승우 | 속도파 | "일단 돌아가게 만들자" |
| 지민 | 품질파 | "검증 없이 넘어가면 나중에 두 배 더 걸려" |
| 주혁 | 혁신파 | "기존 방식 그대로는 아까워" |
| 유진 | 실용파 | "필요한 것만. 오버엔지니어링 하지 말자" |
| 수영 | 아키텍처파 | "지금 잘못 설계하면 나중에 다 갈아엎어야 해" |
| 민아 | 사용자파 | "기술적으로 완벽해도 쓰기 불편하면 소용없어" |

---

## 2. 시스템 아키텍처

### 전체 데이터 흐름

```mermaid
flowchart TD
    User(["🧑 사용자"])
    User -->|"POST /api/team-task"| App

    subgraph Server["Flask Server"]
        App["app.py\n라우트 · 파일 검증"]
        App --> Runner["runner.py\nrun_autonomous_task()"]

        Runner -->|"태스크 분류"| Classify["deliberation.py\nclassify_task()"]
        Classify -->|"build / feedback\nreview / discuss / plan"| Runner

        Runner -->|"6명 병렬 킥오프"| Kickoff["킥오프 발언\n+ 1:1 대화"]

        Kickoff --> WF

        subgraph WF["workflows.py"]
            direction TB
            W1["_run_build"]
            W2["_run_feedback"]
            W3["_run_review"]
            W4["_run_discuss"]
            W5["_run_plan"]
        end

        WF -->|"순차 토론 + 합의"| Deliberate["deliberation.py\ndeliberate()"]
        Deliberate -->|"체크리스트 합의문"| WF

        WF -->|"병렬 생성"| Gen["generation.py\nwrite_project_docs()\nwrite_code_files()"]
        Gen -->|"docs · code"| WF

        WF -->|"6명 투표"| Gate["deliberation.py\nteam_gate()"]
        Gate -->|"PASS / BLOCK"| WF
    end

    Gen -->|"파일 저장"| Workspace[("workspace/\nNN-type-slug/")]
    Server -->|"SSE 스트림"| Browser(["🖥 브라우저\n실시간 렌더링"])
```

### API 호출 계층

| 함수 | 용도 | 모델 | 토큰 |
|------|------|------|------|
| `agent_call()` | 토론 발언, 반응 | Claude Haiku | ~150 |
| `doc_call()` | 문서·코드 생성 | Claude Sonnet | 800~8192 |
| `tool_agent_call()` | 파일 읽기·검색 (ReAct) | Claude Sonnet | ~1024 |

비용 최적화를 위해 짧은 발언은 Haiku, 긴 생성 작업은 Sonnet을 분리 사용한다.

---

## 3. 워크플로우 설계

### 태스크 분류 → 워크플로우 라우팅

`classify_task()`가 입력 태스크를 분석해 5가지 타입 중 하나로 분류하고, 각각 다른 실행 흐름을 선택한다.

| 타입 | 트리거 예시 | 라운드 | 특징 |
|------|------------|--------|------|
| `build` | "만들어줘", "구현해줘" | 기획→개발→검증 | team_gate 최대 3회 재시도, 블락 시 지적 파일만 타겟 수정 |
| `feedback` | "피드백해줘", "분석해줘" | 심층분석→교차토론→보고서 | 전원 개별 분석 후 deliberate |
| `review` | "검토해줘", "리뷰해줘" | 전문검토→이슈토론→보고서 | CRITICAL/MAJOR/MINOR 분류 |
| `discuss` | "토론해봐", "어떻게 생각해" | 입장표명→다자토론→결론 | deliberate 3라운드 |
| `plan` | "계획 세워줘", "로드맵 잡아줘" | 방향토론→범위합의→문서작성 | write_project_docs 후 team_gate |

### build 워크플로우 상세

```mermaid
flowchart TD
    Start(["태스크 입력"]) --> R1

    subgraph R1["Round 1 · 기획"]
        direction TB
        R1A["deliberate()\n5명 방향 토론"] --> R1B["요구사항 체크리스트 합의"]
        R1B --> R1C["write_project_docs()\n문서 4종 병렬 생성"]
        R1C --> R1D{"team_gate()\n6명 투표"}
        R1D -->|"BLOCK"| R1C
        R1D -->|"PASS (최대 3회)"| R2
    end

    subgraph R2["Round 2 · 개발"]
        direction TB
        R2A["deliberate()\n코드 구조 토론"] --> R2B["코드 체크리스트 합의"]
        R2B --> R2C["write_code_files()\n파일 병렬 생성\n잘림 감지 시 최대 3회 이어쓰기"]
        R2C --> R2D{"team_gate()\n6명 투표"}
        R2D -->|"BLOCK"| R2E["지적 파일만\n타겟 수정"]
        R2E --> R2D
        R2D -->|"PASS"| R3
    end

    subgraph R3["Round 3 · 검증"]
        direction TB
        R3A["결과보고서 작성"] --> R3B{"team_gate()\n최종 검증"}
        R3B -->|"PASS"| R3C["승우 최종 결론"]
    end

    R3C --> Done(["workspace/ 저장 완료"])
```

### 합의 체크리스트

토론 후 각 에이전트가 핵심 요구사항 1가지를 직접 표명하고, 이를 체크리스트로 합성해 문서·코드 생성 프롬프트에 삽입한다.

```
【팀 합의 체크리스트】
- 승우: 2주 안에 돌아가는 버전
- 지민: 에러 처리 및 기본 테스트 포함
- 수영: DB 스키마 먼저 확정
- 유진: 외부 라이브러리 최소화
- 주혁: AI 기능 1개 이상 포함
- 민아: 모바일 반응형 UI
```

이 체크리스트를 `team_gate()`에서 각 에이전트가 자기 요구사항이 결과물에 반영됐는지 직접 검증한다. 1명이라도 BLOCK이면 재작성.

---

## 4. 핵심 기술적 도전

### Generator 기반 신호 시스템

워크플로우 함수들은 전부 Python generator로 구현된다. 클라이언트로 보낼 SSE 문자열(`str`)과 내부 제어 신호(`dataclass`)를 같은 generator에서 `yield`하고, `make_sse_stream()`이 분기 처리한다.

```python
# signals.py — 타입화된 내부 신호
@dataclass
class ConsensusSignal:
    text: str          # deliberate → 워크플로우로 합의문 전달

@dataclass
class GateResultSignal:
    passed: bool
    block_reasons: list[str]   # team_gate → 워크플로우로 투표 결과 전달
```

초기엔 `{"__consensus__": ...}` 같은 마법 딕셔너리 키를 사용했는데, 오타로 인한 묵묵한 버그가 반복됐다. dataclass 타입으로 교체 후 `isinstance()` 체크가 명시적이 됐고 버그가 사라졌다.

### 코드 잘림 감지 및 이어쓰기

LLM이 `max_tokens` 한도 내에 파일을 다 못 쓰고 함수 중간에서 절단되는 문제가 반복됐다. 에러 없이 조용히 잘려 저장 시점에 알 수 없었다.

```python
def is_truncated(code: str) -> bool:
    """코드가 중간에 잘렸는지 감지"""
    # 언더스코어로 끝남 (식별자 중간 절단)
    # 중괄호 불균형
    # 함수/클래스 선언 후 본문 없음
    ...
```

감지 시 "이어서 작성해줘" 프롬프트로 최대 3회 이어쓰기. 이어쓰기 결과에서 코드 블록 마커(```` ```python ````)를 제거하는 후처리도 추가했다.

### Rate Limit 대응

`utils.py`의 `with_rate_limit_retry()`가 모든 API 호출의 rate limit 처리를 담당한다. 재시도 로직이 `doc_call()`과 `tool_agent_call()` 양쪽에 복붙되어 있던 것을 하나로 통합했다.

```
1차 실패 → 15초 대기
2차 실패 → 30초 대기
3차 실패 → raise
```

병렬 생성 시 API 호출 제출 간격(`_CALL_STAGGER = 2.0초`)과 동시 워커 수(`_MAX_WORKERS = 3`)를 조정해 rate limit을 회피한다.

### SSE 이벤트 타입

| 이벤트 | 설명 |
|--------|------|
| `workflow` | 분류된 워크플로우 타입과 페이즈 목록 |
| `thinking` | 에이전트 로딩 표시 |
| `response` | 에이전트 발언 (`ctx`: kickoff/debate/gate/analyze/bilateral) |
| `consensus` | 팀 합의 체크리스트 |
| `gate` | team_gate 투표 결과 (`passed`, `block_reasons`) |
| `writing_doc` / `doc_saved` | 파일 생성 중/완료 |
| `round` | 현재 라운드 번호와 라벨 |
| `synthesis` / `done` | 최종 결론 및 워크플로우 완료 |

---

## 5. 실제 생성 사례

AX Team으로 직접 돌려본 프로젝트들. 결과물은 `workspace/` 폴더에 저장된다.

| # | 태스크 | 워크플로우 | 결과 | 주요 이슈 |
|---|--------|-----------|------|-----------|
| 01 | AI 면접 코치 | build | FastAPI + SQLite + GPT-4o 면접 질문/STAR 피드백 서비스 | import 불일치, rate limit으로 라우터 2개 생성 실패 |
| 02 | 쿠팡 가격 모니터 | build | CLI 기반 가격 추적 + 목표가 알림 도구 | agent ID 버그로 프론트 생성 실패, 5개 파일 설명 텍스트 혼입 |
| 03 | K리그 AI 해설 | feedback | 기존 AI 해설 서비스 심층 분석 및 개선 제안 | — |
| 04 | SpotMind AI B2B | build | FastAPI + PostgreSQL + Redis + React 기반 B2B SaaS | 의존성 과중 (PostgreSQL, Redis, Node.js 모두 필요) |
| 05 | 테트리스 vs AI | build | Dellacherie 휴리스틱 AI 대전 테트리스 (단일 HTML) | index.html 토큰 초과 절단, Python 파일 마커 오염 |
| 06 | 할일 앱 | build | 파일 10개짜리 to-do 앱 | 전형적인 오버엔지니어링 |

### 반복적으로 발견된 버그들과 대응

생성 사례를 쌓으면서 ax-team 코드베이스 자체를 고쳐온 기록이다.

**① 설명 텍스트 혼입** (01, 02)
에이전트가 코드 앞에 "설계 먼저 짚고 갈게요." 같은 설명을 붙이는 경우, `extract_code()`의 정규식 매칭이 실패해 설명까지 파일에 그대로 저장됐다.
→ 마크다운 앞·뒤 텍스트를 제거하는 전처리 로직 추가.

**② 코드 잘림** (01, 02, 05)
`max_tokens` 한도 내에 파일을 다 못 쓰고 함수 중간에서 절단됐다. 에러 없이 조용히 잘려 저장 시점에 알 수 없었다.
→ `is_truncated()` 감지 패턴 강화, 이어쓰기 1회 → 최대 3회 루프로 변경.

**③ 병렬 생성 시 import 불일치** (01, 02)
파일 6개를 동시에 생성할 때 서로 뭘 만드는지 모른 채 독립적으로 작성돼 실제로 없는 경로나 메서드를 참조하는 코드가 만들어졌다.
→ 체크리스트 기반 합의문을 생성 프롬프트에 삽입, team_gate로 불일치 검출.

**④ agent ID 버그** (02)
민아 에이전트 ID가 코드 내에 `mina`로 잘못 등록되어 있어 생성 자체가 실패했다.
→ `agents.py`에서 ID 일관성 점검 후 수정.

**⑤ 마커 오염** (05)
이어쓰기 시 새 LLM 응답이 코드 블록 마커째로 기존 파일에 붙어버렸다.
→ `extract_code()`가 이어쓰기 결과를 파싱할 때 마커 제거 처리 추가.

---

## 6. 개발 과정 (v1 → v5)

### v1 — CLI 스크립트

터미널에서 태스크를 입력하면 마케팅·개발·비즈니스 3명이 순서대로 의견을 내는 단순한 CLI. 각자 한 번씩 발언하고 퍼실리테이터가 종합하는 구조. 실시간성도 없고, 파일도 안 만들고, 캐릭터도 없었다.

**한계:** 발언 순서가 고정이라 실제 토론처럼 느껴지지 않았다. 결과물이 텍스트 출력뿐이라 뭔가 만들어졌다는 느낌이 없었다.

### v2 — Flask + SSE + 역할 기반 에이전트

웹으로 전환. SSE로 에이전트 응답을 실시간 스트리밍. 역할도 6명으로 늘리고(마케팅·개발·기획·비즈니스·데이터·팀장) 문서 4종 + 코드 파일까지 생성하도록 했다. 승우(팀장)가 단독으로 PASS/REVISE를 판단하는 게이트키퍼 구조.

**한계:** 에이전트들이 각자 역할에 맞는 작업을 기계적으로 수행할 뿐 실제 논의가 없었다. 어떤 태스크를 넣어도 무조건 문서→코드→검증 파이프라인이 실행됐다. 승우 혼자 게이트키퍼라서 팀 전체 관점이 반영되지 않았다.

### v3 — 역할 → 성향, deliberate + team_gate

**역할 → 성향으로 재설계**: 마케팅담당·기획담당을 없애고 전원 개발자로 통일. 대신 속도파·품질파·혁신파·실용파·아키텍처파·사용자파로 성향 차이를 두었다.

**기계적 실행 → 토론 + 합의**: `deliberate()`로 라운드 내 병렬 발언, 라운드 간 이전 발언에 반응하는 구조. 마지막에 승우가 합의 도출.

**승우 단독 → team_gate()**: 6명이 전부 PASS/BLOCK 투표. 1명이라도 BLOCK이면 통과 못함.

**고정 파이프라인 → classify_task() 라우팅**: 태스크를 먼저 분류하고 타입에 맞는 워크플로우 실행.

### v4 — 합의 품질 개선 + 코드 강화

- 합의문을 2줄 요약에서 **6명 체크리스트**로 구조화 — 각자 요구사항이 생성 프롬프트에 반영됨
- team_gate: 2명 BLOCK → **1명 BLOCK**으로 기준 강화
- Path traversal 차단, 서버 파일 타입 검증 추가
- `deliberate()` history를 `deque(maxlen=20)`으로 메모리 최적화
- 단위 테스트 12개 추가

### v5 — 코드 구조 정리

- 마법 딕셔너리 키 → **dataclass 신호 타입** (`signals.py`)
- 중복 rate limit 재시도 → `with_rate_limit_retry()` 통합
- 반복 패턴 → `_collect_individual_analysis()` 헬퍼 추출

---

## 7. 한계 및 향후 계획

### 현재 한계

| 항목 | 내용 |
|------|------|
| 코드 일관성 | 병렬 생성 시 파일들이 서로의 구조를 모르고 작성돼 import 불일치 가능. team_gate가 잡아내지만 완벽하지 않음 |
| Rate Limit | Claude API 분당 출력 토큰 한도로 병렬 생성 시 간헐적 실패 가능 |
| 실행 보장 없음 | 생성된 코드는 실행 가능한 초안 수준. 실제 환경 맞춤 수정 필요 |
| 한글 slug | 한글 태스크명은 workspace 폴더가 `project`로 생성됨 (영문 태스크 권장) |

### 향후 계획

- **코드 실행 검증**: 생성된 코드를 샌드박스에서 실행해 에러 자동 수정
- **RAG 강화**: 과거 성공 사례를 컨텍스트로 제공해 품질 개선
- **Streaming 코드 생성**: 코드 파일을 실시간 스트리밍으로 렌더링

---

## 8. 실행 방법

```bash
cd ax-team
pip install flask anthropic supabase python-dotenv

# .env 파일
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_KEY=...

python3 app.py
# → http://localhost:5001
```

개발 모드 (자동 재시작):
```bash
FLASK_ENV=development python3 app.py
```

---

## 9. 디렉토리 구조

```
ax-team/
├── app.py              Flask 진입점 — HTTP 라우트, 파일 타입 검증
├── agents.py           에이전트 정의 — 성향, 시스템 프롬프트, WORKFLOW_AGENTS
├── signals.py          Generator 제어 신호 dataclass 타입 정의
├── utils.py            공통 유틸 — Anthropic 클라이언트, SSE, rate limit 재시도
├── workspace_utils.py  폴더 생성, 파일 저장, 코드 추출/잘림 감지, 경로 검증
├── generation.py       문서·코드 병렬 생성 (MAX_WORKERS=3)
├── deliberation.py     토론, 체크리스트 합의, 투표, 태스크 분류
├── workflows.py        타입별 실행 흐름 — 공통 헬퍼 + 5가지 워크플로우
├── runner.py           킥오프 → 분류 → 워크플로우 라우팅
├── db.py               Supabase 세션/메시지 저장
├── rag.py              과거 유사 태스크 RAG 검색
├── tools.py            도구 정의 — list_files, read_file, search_memory
├── static/             프론트엔드 JS/CSS
├── templates/          HTML 템플릿
├── tests/              단위 테스트 (pytest)
├── migrations/         Supabase 스키마 SQL
└── workspace/          태스크 실행 결과물 저장
    └── NN-{type}-{slug}/
        ├── docs/       기획 문서 4종
        ├── code/       생성된 코드 파일
        └── 00_결론.md
```

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 백엔드 | Flask, Python generator (SSE 스트리밍) |
| AI | Anthropic Claude (Haiku + Sonnet 분리 사용) |
| DB | Supabase (PostgreSQL) |
| 패턴 | Multi-agent, ReAct (tool use), Generator 신호 시스템 |
| 테스트 | pytest |
