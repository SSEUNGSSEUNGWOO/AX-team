# Coupang Price Monitor

쿠팡 상품 URL을 등록하면 목표가 이하로 내려왔을 때 알림을 주는 가격 모니터링 도구.

## 실행 방법

```bash
cd 02-coupang-price-monitor/code
pip install -r requirements.txt

# 상품 등록
python cli.py add "https://www.coupang.com/vp/products/..." 29900 --name "무선 마우스"

# 목록 확인
python cli.py list

# 1회 가격 체크
python cli.py run --once

# 주기적 모니터링 (기본 3600초)
python cli.py run --interval 1800

# 단일 상품 즉시 조회
python cli.py status <product_id>
```

> ⚠️ 쿠팡은 봇 탐지가 강합니다. 403 반복 시 Selenium/Playwright 전환이 필요합니다.
> 상업적 이용은 쿠팡 ToS 위반 소지가 있으므로 개인 용도로만 사용하세요.

---

## AX Team 생성 결과 분석

> AX Team (승우·지민·주혁·유진·수영·민아) 이 자율 협업으로 생성한 결과물에 대한 사후 분석.

### AX Team이 만든 것

| 파일 | 상태 | 내용 |
|------|------|------|
| `01_요구사항정의서.md` | ✅ 정상 | 기능 요구사항, 우선순위 잘 작성됨 |
| `02_시장조사보고서.md` | ✅ 정상 | 가격 비교 앱 시장, 경쟁사 분석 포함 |
| `03_기술설계서.md` | ✅ 정상 | 스크래핑 전략, 스케줄러 설계, 데이터 모델 |
| `04_진행계획서.md` | ✅ 정상 | 마일스톤, MVP 범위 |
| `code/models.py` | ⚠️ 부분 생성 | 설명 텍스트 혼입 + `discount_rate` property 잘림 |
| `code/scraper.py` | ⚠️ 부분 생성 | 설명 텍스트 혼입 + `_check_blocked()` 함수 잘림 |
| `code/monitor.py` | ⚠️ 부분 생성 | 설명 텍스트 혼입 + `resp.raise_` 에서 잘림 |
| `code/storage.py` | ✅ 정상 | JSON 파일 기반 CRUD, 완전히 작동 |
| `code/requirements.txt` | ❌ 오류 | 마크다운 텍스트와 코드블록이 혼입되어 pip install 불가 |
| `code/cli.py` | ❌ 오류 | 설명 텍스트 혼입 + 없는 모듈 import + 없는 메서드 참조 |
| `static/index.html` | ❌ 생성 실패 | agent ID 버그로 에러 텍스트만 저장됨 |

### 왜 이렇게 됐나

**1. 설명 텍스트 혼입 — 5개 파일**

수영 에이전트가 파일을 작성할 때 "설계 먼저 짚고 갈게요.", "기술 스택 확정 전에 크리틱 한 번 부탁해요." 같은 설명을 코드 앞에 붙이는 습관이 있다. `extract_code()` 함수는 코드 블록 내용만 추출하도록 설계됐는데, 모든 코드가 backtick 블록 안에 있어도 그 앞의 마크다운 설명이 함께 저장됐다.

**2. 코드 잘림 — 3개 파일**

`models.py`의 `discount_rate`, `scraper.py`의 `_check_blocked()`, `monitor.py`의 `fetch_price()` 가 모두 토큰 한도(max_tokens=2000) 초과로 중간에 끊겼다. 특히 수영이 설명을 앞에 붙이는 습관 때문에 실제 코드에 쓸 수 있는 토큰이 더 줄어들었다. 에러 없이 조용히 잘려서 저장 시점에는 알 수 없었다.

**3. import 불일치 — cli.py**

cli.py가 `from product_store import ProductStore`를 참조했는데 실제 파일은 `storage.py`이고 클래스가 아닌 함수 모음이다. 또한 `store.list_all()`, `p.is_target_met()`, `p.id` 같은 메서드를 사용했는데, `storage.py`의 함수 이름은 `list_products()`, Product dataclass의 필드는 `product_id`였다. 병렬 생성 시 cli.py가 다른 파일의 실제 구조를 모르고 독립적으로 작성됐기 때문.

**4. 프론트엔드 생성 실패**

민아 에이전트의 ID가 `minseo`인데 코드 내에 `mina`로 잘못 등록되어 있어서 생성 자체가 실패했다. 에러 텍스트 `'mina'`만 파일로 저장됨.

### Claude가 수정/추가한 것

| 항목 | 내용 |
|------|------|
| `requirements.txt` | 마크다운 제거, 순수 패키지 목록만 남김 |
| `scraper.py` | 설명 텍스트 제거, `_check_blocked()` 완성, 퍼블릭 `scrape()` 함수 추가 |
| `models.py` | 설명 텍스트 제거, `discount_rate` property 완성 |
| `monitor.py` | 설명 텍스트 제거, `fetch_price()` 완성, `is_target_met()` 메서드 추가, `PriceMonitor` 클래스 완성 |
| `cli.py` | 설명 텍스트 제거, import를 실제 파일 구조에 맞게 수정, 메서드명 일치화, 디스패처 완성 |
| `static/index.html` | 처음부터 새로 작성 (원본 생성 실패) |
