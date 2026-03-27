# AI Interview Coach

## 실행 방법

```bash
# 1. 의존성 설치
cd ai-interview-coach
pip install -r requirements.txt

# 2. .env 파일에 OpenAI API 키 입력
# OPENAI_API_KEY=sk-...

# 3. 서버 실행
cd code
export $(cat ../.env | xargs)
uvicorn main:app --port 8001 --reload
```

브라우저에서 `http://localhost:8001` 열면 프론트엔드 접속 가능.
API 문서: `http://localhost:8001/docs`

---

## 프로젝트 개요

직군별 면접 예상 질문을 AI가 생성하고, 사용자의 답변을 STAR 구조로 분석해 항목별 피드백을 제공하는 서비스.

## 기술 스택

- **Backend**: FastAPI, SQLAlchemy (SQLite), Pydantic
- **AI**: OpenAI GPT-4o (질문 생성 + STAR 피드백)
- **Frontend**: Vanilla HTML/CSS/JS

## API

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /api/v1/questions/generate` | 직군/경력 기반 면접 질문 생성 |
| `POST /api/v1/feedback/evaluate` | 답변 STAR 분석 + 점수 |
| `GET /api/v1/questions/roles` | 지원 직군/경력 목록 |
| `POST /api/v1/sessions/` | 면접 세션 생성 |

---

---

## AX Team 생성 결과 분석

> AX Team (승우·지민·주혁·유진·수영·민아) 이 자율 협업으로 생성한 결과물에 대한 사후 분석.

### AX Team이 만든 것

| 파일 | 상태 | 내용 |
|------|------|------|
| `01_요구사항정의서.md` | ✅ 정상 | 기능 요구사항, 우선순위 잘 작성됨 |
| `02_시장조사보고서.md` | ✅ 정상 | TAM/SAM/SOM, 경쟁사 분석 포함 |
| `03_기술설계서.md` | ✅ 정상 | 시스템 아키텍처, API 설계, DB 스키마 |
| `04_진행계획서.md` | ✅ 정상 | 마일스톤, MVP 범위 |
| `code/models.py` | ✅ 정상 | SQLAlchemy ORM 모델 잘 작성됨 |
| `code/schemas.py` | ✅ 정상 | Pydantic 스키마 |
| `code/database.py` | ✅ 정상 (단, PostgreSQL 기준) | async SQLAlchemy 설정 |
| `code/ai_pipeline.py` | ⚠️ 부분 생성 | 코드 앞에 설명 텍스트 붙음 + 마지막 함수 잘림 |
| `code/services.py` | ⚠️ 부분 생성 | 코드 앞에 설명 텍스트 붙음 |
| `code/repositories.py` | ⚠️ 부분 생성 | 코드 앞에 설명 텍스트 붙음 |
| `code/main.py` | ❌ 오류 | 존재하지 않는 경로 import |
| `code/requirements.txt` | ❌ 오류 | 마크다운 텍스트가 섞여 pip install 불가 |
| `code/routers/questions.py` | ❌ 오류 | 없는 서비스 클래스 import |
| `code/routers/sessions.py` | ❌ 생성 실패 | Rate limit으로 에러 텍스트만 저장됨 |
| `code/routers/feedback.py` | ❌ 생성 실패 | Rate limit으로 에러 텍스트만 저장됨 |

### 왜 이렇게 됐나

**1. 병렬 생성의 한계 — import 불일치**

AX Team은 코드 파일 6개를 동시에 병렬로 생성했다. 각 파일은 다른 파일이 뭘 만들고 있는지 모르는 상태에서 독립적으로 작성됐기 때문에, `main.py`는 `app.api.v1.router`를 참조하고 `questions.py`는 `LLMService`를 참조하는 등 서로 맞지 않는 구조가 만들어졌다. 실제로 존재하는 파일 구조와 전혀 다른 경로를 가정하고 작성된 것이다.

**2. Rate Limit — 429 에러**

Claude API는 분당 출력 토큰 한도(8,000 토큰/분)가 있다. 파일당 최대 2,000토큰으로 6개 파일을 동시에 생성하면 이론상 12,000토큰이 필요해서 한도를 초과했다. `routers/sessions.py`와 `routers/feedback.py`는 이 때문에 생성에 실패했고, 에러 메시지가 그대로 파일에 저장됐다.

**3. 설명 텍스트 추출 실패**

수영 에이전트가 코드를 작성할 때 "설계 검토했어요. 파이프라인 작성합니다." 같은 설명을 앞에 붙이고, 그 다음에 코드 블록을 작성했다. `extract_code()` 함수는 코드 블록을 찾아 추출하도록 설계됐는데, 역따옴표(backtick) 인코딩 방식 차이로 정규식 매칭이 실패해서 설명 텍스트까지 통째로 저장됐다.

**4. 코드 잘림**

`ai_pipeline.py`의 `_parse_feedback()` 함수가 중간에 잘렸다. 토큰 한도(2,000) 내에 전체 파일을 다 쓰지 못한 것이다. 에러 없이 조용히 잘렸기 때문에 저장 시점에는 문제를 알 수 없었다.

### Claude가 수정/추가한 것

| 항목 | 내용 |
|------|------|
| `requirements.txt` | 마크다운 제거, PostgreSQL·Redis·Whisper 등 제거, SQLite 기반 최소화 |
| `database.py` | PostgreSQL → SQLite로 변경해 로컬 즉시 실행 가능하게 수정 |
| `main.py` | 없는 경로 import 제거, 실제 파일 구조에 맞게 재작성 |
| `ai_pipeline.py` | 설명 텍스트 제거, 잘린 `_parse_feedback()` 함수 완성 |
| `services.py` | 설명 텍스트 제거 |
| `repositories.py` | 설명 텍스트 제거 |
| `routers/questions.py` | 없는 의존성 제거, `ai_pipeline` 직접 연결로 재작성 |
| `routers/sessions.py` | 처음부터 새로 작성 (원본 생성 실패) |
| `routers/feedback.py` | 처음부터 새로 작성 (원본 생성 실패) |
| `code/__init__.py` | 누락된 패키지 초기화 파일 추가 |
| `code/routers/__init__.py` | 누락된 패키지 초기화 파일 추가 |
| `static/index.html` | 프론트엔드 전체 새로 작성 (AX Team 미생성) |
| `.env` | 플레이스홀더 파일 생성 |
| 폴더명 | `20260325_1700_AI_면접_코치_서비스___직군별_예상_질문_생성` → `ai-interview-coach` |
