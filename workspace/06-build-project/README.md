# 할일 관리 앱

ax-team AI 에이전트 팀이 생성한 할일 관리 웹앱 (build 워크플로우).

## 실행 방법

```bash
# 별도 서버 없이 브라우저에서 직접 열기
open static/index.html
```

## 주요 기능

- 할일 추가 / 완료 체크 / 삭제
- 전체 · 진행중 · 완료 필터
- 로컬스토리지 자동 저장 (새로고침해도 유지)
- 엔터키 입력 지원, 빈 입력 시 에러 표시

## 파일 구조

```
static/index.html          ← 실행 파일 (단일 HTML)
code/
  app.js                   ← 에이전트가 생성한 초안 (미사용)
  components/TodoItem.js
  components/TodoList.js
  models/todo.js
  services/todoService.js
  storage/localStorageAdapter.js
  utils/migrationUtil.js
  utils/validator.js
docs/
  01_요구사항정의서.md
  02_기술설계서.md
  03_시장조사보고서.md
  04_진행계획서.md
  결과보고서.md
```

---

## 생성 과정 기록

### 무슨 일이 있었나

이 프로젝트는 ax-team의 **첫 번째 build 워크플로우 실제 실행** 케이스.
당시 코드에 버그가 있어서 결과물이 실행 불가능한 상태로 저장됐다.

### 발생한 문제

**1. index.html JS 코드가 중간에 잘림**

LLM이 긴 코드를 생성하다 `max_tokens` 한도에 걸려 출력이 중단됐다.
당시 `extract_code()`는 닫는 ` ``` ` 마커가 없으면 추출 실패,
`is_truncated()`는 마지막 줄이 `STORAGE_`로 끝나는 것을 감지하지 못함.
결과: ` ```html ` 마커가 파일 1줄에 그대로 남은 채 JS가 절반만 저장됨.

**2. 오버엔지니어링**

수영(아키텍처 파)의 영향으로 단순 할일 앱에 파일 10개짜리 구조를 설계함.
`migrationUtil.js`, `validator.js` 등 실제로 필요 없는 파일들이 생성됨.
승우 결론에도 "전형적인 오버엔지니어링"이라고 적혀 있음.

### 이후 수정된 내용 (ax-team 코드베이스)

- `extract_code()`: 닫는 ` ``` ` 없이 잘린 블록도 내용 추출 가능하도록 수정
- `is_truncated()`: `_` 로 끝나는 경우, 중괄호 불균형, mid-identifier 패턴 감지 추가
- 이어쓰기 로직: 1회 → 최대 3회 루프로 변경
- 이 파일(`static/index.html`)은 수동으로 JS를 완성해 실행 가능하게 복구함

### 현재 상태

`static/index.html` 단독으로 실행 가능.
`code/` 하위 파일들은 에이전트가 생성한 초안이며 실제로 연결되어 있지 않음.
