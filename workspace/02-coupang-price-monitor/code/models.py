"""
상품 및 모니터링 데이터 모델 정의
Pydantic v2 기반 — 검증, 직렬화, 타입 안전성 확보
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class AlertStatus(str, Enum):
    PENDING   = "pending"
    TRIGGERED = "triggered"
    SNOOZED   = "snoozed"


class MonitorStatus(str, Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    ERROR    = "error"


class Product(BaseModel):
    product_id : str
    url        : str
    name       : Optional[str] = Field(None)
    created_at : datetime      = Field(default_factory=datetime.utcnow)

    @field_validator("url")
    @classmethod
    def validate_coupang_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if "coupang.com" not in parsed.netloc:
            raise ValueError(f"쿠팡 URL이 아닙니다: {v}")
        if not parsed.scheme.startswith("http"):
            raise ValueError("http 또는 https URL이어야 합니다.")
        return v

    @model_validator(mode="after")
    def parse_product_id(self) -> Product:
        if self.product_id:
            return self
        parsed = urlparse(self.url)
        segments = [s for s in parsed.path.split("/") if s]
        try:
            idx = segments.index("products")
            self.product_id = segments[idx + 1]
        except (ValueError, IndexError):
            raise ValueError(f"URL에서 상품 ID를 추출할 수 없습니다: {self.url}")
        return self

    model_config = {"frozen": False}


class PriceRecord(BaseModel):
    product_id   : str
    price        : int           = Field(..., ge=0)
    is_available : bool          = Field(True)
    collected_at : datetime      = Field(default_factory=datetime.utcnow)
    raw_text     : Optional[str] = Field(None)

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: int) -> int:
        if v < 0:
            raise ValueError("가격은 0 이상이어야 합니다.")
        return v


class MonitoringTarget(BaseModel):
    target_id        : str
    product_id       : str
    target_price     : int           = Field(..., ge=1)
    interval_seconds : int           = Field(3600, ge=60)
    status           : MonitorStatus = Field(MonitorStatus.ACTIVE)
    alert_status     : AlertStatus   = Field(AlertStatus.PENDING)
    created_at       : datetime      = Field(default_factory=datetime.utcnow)
    last_checked_at  : Optional[datetime] = Field(None)
    last_error       : Optional[str]      = Field(None)

    @field_validator("target_price")
    @classmethod
    def target_price_reasonable(cls, v: int) -> int:
        if v > 100_000_000:
            raise ValueError("목표가가 너무 큽니다. 단위를 확인하세요 (원).")
        return v

    def is_alert_needed(self, current_price: int) -> bool:
        return (
            self.status == MonitorStatus.ACTIVE
            and self.alert_status == AlertStatus.PENDING
            and current_price <= self.target_price
        )

    def mark_triggered(self) -> None:
        self.alert_status = AlertStatus.TRIGGERED

    def mark_error(self, message: str) -> None:
        self.status = MonitorStatus.ERROR
        self.last_error = message

    def reset_error(self) -> None:
        self.status = MonitorStatus.ACTIVE
        self.last_error = None

    model_config = {"frozen": False}


class AlertEvent(BaseModel):
    alert_id      : str
    target_id     : str
    product_id    : str
    product_name  : Optional[str]
    target_price  : int
    actual_price  : int
    triggered_at  : datetime = Field(default_factory=datetime.utcnow)

    @property
    def discount_amount(self) -> int:
        return self.target_price - self.actual_price

    @property
    def discount_rate(self) -> float:
        if self.target_price == 0:
            return 0.0
        return round((self.discount_amount / self.target_price) * 100, 1)

    model_config = {"frozen": True}
