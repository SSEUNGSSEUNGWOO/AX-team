# code/config.py
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────
    APP_NAME: str = "AI Interview Coach"
    APP_ENV: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = False
    API_VERSION: str = "v1"

    # ── Server ───────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── OpenAI ───────────────────────────────────────
    OPENAI_API_KEY: str = Field(..., min_length=1)
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = Field(default=0.7, ge=0.0, le=2.0)
    OPENAI_MAX_TOKENS: int = Field(default=2048, ge=256, le=8192)
    OPENAI_TIMEOUT: int = 30  # seconds

    # ── Database ─────────────────────────────────────
    DATABASE_URL: str = Field(..., min_length=1)
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # ── Redis (세션 캐시) ─────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600  # 1 hour

    # ── Auth ─────────────────────────────────────────
    SECRET_KEY: str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── AI Pipeline ──────────────────────────────────
    QUESTION_COUNT_MIN: int = 10
    QUESTION_COUNT_MAX: int = 20
    FEEDBACK_SCORE_DIMENSIONS: list[str] = [
        "논리성",
        "구체성",
        "직무적합성",
    ]

    # ── Rate Limiting ─────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 20

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """싱글턴 설정 인스턴스 반환 — 앱 전역에서 이걸로 접근."""
    return Settings()


# 직군 / 경력 레벨 Enum 상수 (DB 마이그레이션 없이 확장 가능하도록 여기서 관리)
JOB_CATEGORIES: list[str] = [
    "개발",
    "마케팅",
    "기획",
    "디자인",
    "데이터",
    "영업",
]

CAREER_LEVELS: dict[str, str] = {
    "junior": "신입",
    "mid": "3년",
    "senior": "5년+",
}