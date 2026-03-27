"""
쿠팡 가격 모니터링 스케줄러
- 상품 URL + 목표가 등록/관리 (JSON 영속성)
- 주기적 가격 조회 + 콘솔 알림
- Bot 탐지 우회: 헤더 위장 + 랜덤 딜레이
"""

import json
import time
import random
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_FILE = Path("data/products.json")
DEFAULT_INTERVAL_SEC = 3600
REQUEST_TIMEOUT_SEC = 15
MIN_DELAY_SEC = 2.0
MAX_DELAY_SEC = 5.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.coupang.com/",
}

PRICE_SELECTORS = [
    "span.total-price > strong",
    "span.price-value",
    "div.prod-sale-price > span.price-value",
    "li.total-price > strong",
]


# ── 도메인 모델 ───────────────────────────────────────────────────────────────
@dataclass
class Product:
    product_id: str
    url: str
    name: str
    target_price: int
    last_price: Optional[int] = None
    alerted: bool = False
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        return cls(**data)

    def is_target_met(self) -> bool:
        return self.last_price is not None and self.last_price <= self.target_price


# ── 저장소 ───────────────────────────────────────────────────────────────────
class ProductRepository:
    def __init__(self, path: Path = DATA_FILE):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._products: dict[str, Product] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._products = {k: Product.from_dict(v) for k, v in raw.items()}
                logger.info("저장소 로드 완료: 상품 %d개", len(self._products))
            except (json.JSONDecodeError, TypeError) as e:
                logger.error("저장소 로드 실패, 초기화합니다: %s", e)
                self._products = {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(
                {k: v.to_dict() for k, v in self._products.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def add(self, product: Product) -> None:
        if product.product_id in self._products:
            raise ValueError(f"이미 등록된 상품입니다: {product.product_id}")
        self._products[product.product_id] = product
        self._save()
        logger.info("상품 등록: [%s] %s", product.product_id, product.name)

    def update(self, product: Product) -> None:
        self._products[product.product_id] = product
        self._save()

    def remove(self, product_id: str) -> None:
        if product_id not in self._products:
            raise KeyError(f"존재하지 않는 상품: {product_id}")
        del self._products[product_id]
        self._save()

    def all(self) -> list[Product]:
        return list(self._products.values())

    def get(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)


# ── 가격 스크래퍼 ─────────────────────────────────────────────────────────────
class CoupangScraper:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    @staticmethod
    def extract_product_id(url: str) -> str:
        import re
        match = re.search(r"/products/(\d+)", url)
        if not match:
            raise ValueError(f"유효하지 않은 쿠팡 URL: {url}")
        return match.group(1)

    def fetch_price(self, url: str) -> Optional[int]:
        try:
            time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT_SEC)

            if resp.status_code == 403:
                logger.warning("403 Forbidden — 쿠팡 Bot 탐지. Selenium 전환을 고려하세요.")
                return None

            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for selector in PRICE_SELECTORS:
                el = soup.select_one(selector)
                if el:
                    import re
                    digits = re.sub(r"[^\d]", "", el.get_text())
                    if digits:
                        return int(digits)

            logger.warning("가격 요소를 찾지 못했습니다: %s", url)
            return None

        except requests.RequestException as e:
            logger.error("요청 실패: %s — %s", url, e)
            return None


# ── 모니터 ────────────────────────────────────────────────────────────────────
class PriceMonitor:
    def __init__(self, store: ProductRepository) -> None:
        self._store = store
        self._scraper = CoupangScraper()

    def check_all(self) -> None:
        products = self._store.all()
        if not products:
            logger.info("등록된 상품이 없습니다.")
            return

        for product in products:
            price = self._scraper.fetch_price(product.url)
            if price is None:
                logger.warning("[%s] 가격 조회 실패", product.name)
                continue

            product.last_price = price
            self._store.update(product)
            logger.info("[%s] 현재가: %d원 / 목표가: %d원", product.name, price, product.target_price)

            if not product.alerted and price <= product.target_price:
                self._alert(product, price)
                product.alerted = True
                self._store.update(product)

    def _alert(self, product: Product, price: int) -> None:
        print(f"\n{'='*50}")
        print(f"  🔔 목표가 달성!")
        print(f"  상품  : {product.name}")
        print(f"  현재가: {price:,}원")
        print(f"  목표가: {product.target_price:,}원")
        print(f"  URL   : {product.url}")
        print(f"{'='*50}\n")

    def run_loop(self, interval_seconds: int = DEFAULT_INTERVAL_SEC) -> None:
        logger.info("모니터링 시작 — %d초 주기", interval_seconds)
        while True:
            self.check_all()
            logger.info("다음 체크까지 %d초 대기...", interval_seconds)
            time.sleep(interval_seconds)
