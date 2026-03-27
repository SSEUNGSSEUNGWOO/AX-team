# 테트리스 대결 (Human vs AI)

ax-team AI 에이전트 팀이 생성한 테트리스 대전 웹앱 (build 워크플로우).

## 실행 방법

```bash
# 별도 서버 없이 브라우저에서 직접 열기
open static/index.html
```

## 조작법

| 키 | 동작 |
|----|------|
| ← → | 좌우 이동 |
| ↑ | 회전 (월킥 포함) |
| ↓ | 소프트 드롭 (+1점/칸) |
| Space | 하드 드롭 (+2점/칸) |

## 주요 기능

- 플레이어 vs AI 동시 진행 (두 보드 나란히)
- Dellacherie 휴리스틱 AI (-0.51×높이 + 0.76×완성줄 - 0.36×구멍 - 0.18×울퉁불퉁함)
- 고스트 피스 (낙하 위치 미리보기)
- 다음 피스 미리보기
- 레벨 10당 속도 증가 (800ms → 최소 80ms)
- 줄 지운 수에 따른 점수 (1줄=100, 2줄=300, 3줄=500, 4줄=800 × 레벨)

## 파일 구조

```
static/index.html      ← 실행 파일 (단일 HTML, 서버 불필요)
code/
  main.py              ← FastAPI 서버 진입점 (미사용)
  config.py
  models/
    board.py           ← Board 클래스 (에이전트 초안)
    piece.py           ← Piece 클래스 (에이전트 초안)
    game_state.py
  services/
    game_engine.py     ← GameEngine (에이전트 초안, async/sync 불일치)
    ai_agent.py        ← AIAgent (에이전트 초안)
    ai_evaluator.py    ← 평가 함수 (에이전트 초안)
  routers/
    game_router.py     ← FastAPI 라우터 (에이전트 초안)
docs/
  01_요구사항정의서.md
  02_기술설계서.md
  03_시장조사보고서.md
  04_진행계획서.md
```

---

## 생성 과정 기록

### 무슨 일이 있었나

이 프로젝트는 ax-team의 두 번째 build 워크플로우 실제 실행 케이스. 결과물이 심각하게 파편화된 상태로 저장됐다.

### 발생한 문제

**1. 아키텍처 혼선**

에이전트들이 설계 단계에서 FastAPI + WebSocket 백엔드 방식으로 설계했으나, 실제 구현 단계에서 일관성 없이 REST API, 순수 JS, FastAPI가 뒤섞였다. 최종적으로 `static/index.html`은 백엔드 없이 동작하는 단일 HTML로 방향이 바뀌었지만, `code/` 하위의 Python 파일들은 FastAPI 서버 구조 그대로 남았다.

**2. index.html 코드 잘림**

LLM 출력이 `max_tokens` 한도에 걸려 HTML body 중간에서 절단됐다. 당시 `is_truncated()`가 HTML 태그 중간 잘림을 감지하지 못해 불완전한 파일이 저장됐다.

**3. Python 파일에 ` ```python ` 마커 삽입**

이어쓰기(continuation) 시 새 LLM 응답이 코드 블록 마커(` ```python `)를 포함한 채 기존 파일에 그대로 붙어버렸다. `extract_code()`가 이어쓰기 결과를 제대로 추출하지 못한 것이 원인.

영향받은 파일:
- `board.py`: 97번째 줄 이후에 TetrisAI, TetrisPiece, TetrisGame 클래스가 통째로 붙음
- `piece.py`: ` ```python ` 마커 이후에 Board 클래스 코드가 붙음
- `ai_evaluator.py`: ` ```python ` 마커 이후에 game.py 코드가 붙음

**4. game_engine.py async/sync 불일치**

`GameEngine`이 `async def` 메서드를 쓰지만 내부에서 `threading.Thread`를 쓰는 등 async/sync가 뒤섞임. `Board` 클래스에 존재하지 않는 메서드(`drop_height`, `move_left`, `move_right`, `rotate`)를 호출하는 코드도 있어 실행 불가.

### 이후 수정된 내용 (ax-team 코드베이스)

- `extract_code()`: 닫는 ` ``` ` 없이 잘린 블록도 내용 추출 가능하도록 수정
- `is_truncated()`: `_`로 끝나는 경우, 중괄호 불균형, mid-identifier 패턴 감지 추가
- 이어쓰기 로직: 1회 → 최대 3회 루프로 변경
- `board.py`, `piece.py`, `ai_evaluator.py`: ` ```python ` 마커 이후 오염된 코드 수동 제거
- `static/index.html`: 완전한 standalone HTML/JS 테트리스 게임으로 수동 완성

### 현재 상태

`static/index.html` 단독으로 실행 가능. AI는 Dellacherie 휴리스틱으로 동작하며 서버 불필요.

`code/` 하위 Python 파일들은 에이전트가 생성한 초안이며 실제로 연결되어 있지 않음. 아키텍처 혼선과 메서드 불일치로 인해 그대로 실행 불가.
