# code/models.py
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Text, Float,
    ForeignKey, DateTime, Enum, JSON
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class JobLevel(PyEnum):
    JUNIOR = "junior"
    MID = "mid"        # 3년
    SENIOR = "senior"  # 5년+


class JobCategory(PyEnum):
    DEVELOPMENT = "development"
    MARKETING = "marketing"
    PLANNING = "planning"
    DESIGN = "design"


class AnswerType(PyEnum):
    TEXT = "text"
    VOICE = "voice"


# ──────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String(255), unique=True, nullable=False, index=True)
    name       = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)

    sessions = relationship("Session", back_populates="user",
                            cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ──────────────────────────────────────────
class Session(Base):
    """면접 세션 1회 = 직군 + 레벨 + 질문 묶음"""
    __tablename__ = "sessions"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    job_category = Column(Enum(JobCategory), nullable=False)
    job_level    = Column(Enum(JobLevel), nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at     = Column(DateTime, nullable=True)

    user      = relationship("User", back_populates="sessions")
    questions = relationship("Question", back_populates="session",
                             cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (f"<Session id={self.id} "
                f"category={self.job_category} level={self.job_level}>")


# ──────────────────────────────────────────
class Question(Base):
    """LLM이 생성한 예상 질문 (세션당 10~20개)"""
    __tablename__ = "questions"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    content    = Column(Text, nullable=False)          # 질문 본문
    order_idx  = Column(Integer, nullable=False)       # 세션 내 순서
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("Session", back_populates="questions")
    answer  = relationship("Answer", back_populates="question",
                           uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Question id={self.id} order={self.order_idx}>"


# ──────────────────────────────────────────
class Answer(Base):
    """사용자 답변 (질문당 1개, 텍스트 or 음성→텍스트 변환)"""
    __tablename__ = "answers"

    id          = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id",
                         ondelete="CASCADE"), nullable=False, unique=True,
                         index=True)
    content     = Column(Text, nullable=False)          # 답변 본문
    answer_type = Column(Enum(AnswerType),
                         default=AnswerType.TEXT, nullable=False)
    audio_url   = Column(String(512), nullable=True)    # 음성 원본 경로
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("Question", back_populates="answer")
    feedback = relationship("Feedback", back_populates="answer",
                            uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Answer id={self.id} type={self.answer_type}>"


# ──────────────────────────────────────────
class Feedback(Base):
    """STAR 구조 기반 LLM 피드백 + 항목별 점수"""
    __tablename__ = "feedbacks"

    id        = Column(Integer, primary_key=True, index=True)
    answer_id = Column(Integer, ForeignKey("answers.id",
                       ondelete="CASCADE"), nullable=False, unique=True,
                       index=True)

    # 항목별 점수 (0.0 ~ 10.0)
    score_logic     = Column(Float, nullable=False)   # 논리성
    score_specific  = Column(Float, nullable=False)   # 구체성
    score_job_fit   = Column(Float, nullable=False)   # 직무적합성

    # STAR 구조 분석 결과 (JSON: {"S":..,"T":..,"A":..,"R":..})
    star_breakdown  = Column(JSON, nullable=True)

    # 종합 피드백 텍스트
    summary         = Column(Text, nullable=False)

    # LLM 메타 (모델명, 토큰 수 등 — 디버깅·비용 추적용)
    llm_meta        = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    answer = relationship("Answer", back_populates="feedback")

    def __repr__(self) -> str:
        return (f"<Feedback id={self.id} "
                f"logic={self.score_logic} "
                f"specific={self.score_specific} "
                f"job_fit={self.score_job_fit}>")