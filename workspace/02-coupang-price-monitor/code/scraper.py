"""
쿠팡 상품 가격 스크래핑 모듈

한계:
    - 쿠팡 JS 렌더링 의존 상품은 가격 추출 실패 가능
    - 쿠팡 HTML 구조 변경 시 selector 업데이트 필요
    - 상업적 스크래핑은 쿠팡 ToS 위반 소지 있음 — 개인 용도로만 사용
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 예외 정의
# ---------------------------------------------------------------------------
class ScraperError(Exception):
    """스크래퍼 기본 예외"""


class NetworkError(ScraperError):
    """네트워크 요청 실패"""


class PriceNotFoundError(ScraperError):
    """HTML 파싱 성공했으나 가격 요소를 찾지 못함"""


class BlockedError(ScraperError):
    """봇 탐지 또는 접근 차단으로 추정"""


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
COUPANG_BASE_URL = "https://www.coupang.com"

PRICE_SELECTORS = [
    "span.total-price > strong",
    "span.price-value",
    "div.prod-sale-price > span.price-value",
    "li.total-price > strong",
]

TITLE_SELECTORS = [
    "h1.prod-buy-header__title",
    "h2.prod-buy-header__title",
    "div.prod-title",
]

REQUEST_TIMEOUT = 10

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
]

REQUEST_DELAY_RANGE = (2.0, 5.0)


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------
@dataclass
class ScrapeResult:
    """스크래핑 결과 VO"""
    url: str
    title: Optional[str]
    price: int
    raw_price_text: str


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------
def _build_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": COUPANG_BASE_URL,
    }


def _parse_price(raw: str) -> int:
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        raise ValueError(f"가격 파싱 실패: '{raw}'")
    return int(digits)


def _extract_price(soup: BeautifulSoup) -> tuple[int, str]:
    for selector in PRICE_SELECTORS:
        element = soup.select_one(selector)
        if element:
            raw = element.get_text(strip=True)
            try:
                return _parse_price(raw), raw
            except ValueError:
                logger.debug("selector '%s' 텍스트 파싱 실패: %s", selector, raw)
                continue
    raise PriceNotFoundError(
        "가격 요소를 찾지 못했습니다. "
        "JS 렌더링 필요 상품이거나 HTML 구조가 변경되었을 수 있습니다."
    )


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    for selector in TITLE_SELECTORS:
        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
    return None


def _check_blocked(soup: BeautifulSoup, status_code: int) -> None:
    if status_code in (403, 429):
        raise BlockedError(f"HTTP {status_code} — 접근 차단됨")

    block_signals = ["robot", "captcha", "보안문자", "비정상적인 접근", "access denied"]
    page_text = soup.get_text().lower()
    if any(signal in page_text for signal in block_signals):
        raise BlockedError("봇 탐지 페이지 감지됨")


# ---------------------------------------------------------------------------
# 퍼블릭 API
# ---------------------------------------------------------------------------
def scrape(url: str) -> ScrapeResult:
    """
    쿠팡 상품 URL에서 가격과 제목을 추출.

    Raises:
        NetworkError: 요청 실패
        BlockedError: 봇 탐지/차단
        PriceNotFoundError: 가격 요소 없음
    """
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    try:
        resp = requests.get(url, headers=_build_headers(), timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise NetworkError(f"요청 실패: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")
    _check_blocked(soup, resp.status_code)

    price, raw_text = _extract_price(soup)
    title = _extract_title(soup)

    logger.info("스크래핑 성공 — %s: %d원", title or url, price)
    return ScrapeResult(url=url, title=title, price=price, raw_price_text=raw_text)
