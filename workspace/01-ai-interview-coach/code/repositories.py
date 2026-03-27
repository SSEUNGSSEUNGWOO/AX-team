# code/repositories.py
"""
DB CRUD 추상화 레이어
- 각 도메인별 Repository 분리
- SQLAlchemy Session 기반
- 인터페이스(추상 클래스) → 구현체 구조로 확장성 확보
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Session, relationship


# ──────────────────────────────────────────────
# Base Model
# ──────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# ORM Models
# ──────────────────────────────────────────────

class JobRoleModel(Base):
    """직군 마스터 데이터"""
    __tablename__ = "job_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)  # e.g. "개발", "마케팅"
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    sessions = relationship("InterviewSessionModel", back_populates="job_role")


class InterviewSessionModel(Base):
    """면접 세션 — F3 세션 관리 핵심 엔티티"""
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    job_role_id = Column(UUID(as_uuid=True), ForeignKey("job_roles.id"), nullable=False)
    career_level = Column(
        Enum("ENTRY", "MID", "SENIOR", name="career_level_enum"),
        nullable=False,
    )
    status = Column(
        Enum("ACTIVE", "COMPLETED", "ABANDONED", name="session_status_enum"),
        nullable=False,
        default="ACTIVE",
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    job_role = relationship("JobRoleModel", back_populates="sessions")
    questions = relationship(
        "QuestionModel", back_populates="session", cascade="all, delete-orphan"
    )


class QuestionModel(Base):
    """LLM이 생성한 예상 질문 — F1"""
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False)  # 질문 순서 보장
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    session = relationship("InterviewSessionModel", back_populates="questions")
    answer = relationship(
        "AnswerModel", back_populates="question", uselist=False, cascade="all, delete-orphan"
    )


class AnswerModel(Base):
    """사용자 답변 + AI 피드백 — F2"""
    __tablename__ = "answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 질문당 답변 1개
    )
    content = Column(Text, nullable=False)           # 사용자 원문 답변
    input_type = Column(
        Enum("TEXT", "VOICE", name="input_type_enum"),
        nullable=False,
        default="TEXT",
    )

    # AI 피드백 필드
    feedback_raw = Column(Text, nullable=True)         # LLM 원문 피드백
    score_logic = Column(Float, nullable=True)         # 논리성 점수 0~10
    score_specificity = Column(Float, nullable=True)   # 구체성 점수 0~10
    score_job_fit = Column(Float, nullable=True)       # 직무적합성 점수 0~10

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    question = relationship("QuestionModel", back_populates="answer")


# ──────────────────────────────────────────────
# Generic Repository Interface
# ──────────────────────────────────────────────

T = TypeVar("T", bound=Base)


class BaseRepository(ABC, Generic[T]):
    """모든 Repository의 공통 인터페이스"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @abstractmethod
    def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        ...

    @abstractmethod
    def save(self, entity: T) -> T:
        ...

    @abstractmethod
    def delete(self, entity_id: uuid.UUID) -> bool:
        ...

    def _commit_and_refresh(self, entity: T) -> T:
        """공통 저장 패턴 — flush → commit → refresh"""
        self._session.add(entity)
        self._session.flush()
        self._session.commit()
        self._session.refresh(entity)
        return entity


# ──────────────────────────────────────────────
# Concrete Repositories
# ──────────────────────────────────────────────

class JobRoleRepository(BaseRepository[JobRoleModel]):

    def get_by_id(self, entity_id: uuid.UUID) -> Optional[JobRoleModel]:
        return self._session.get(JobRoleModel, entity_id)

    def get_by_name(self, name: str) -> Optional[JobRoleModel]:
        return (
            self._session.query(JobRoleModel)
            .filter(JobRoleModel.name == name)
            .first()
        )

    def list_all(self) -> List[JobRoleModel]:
        return self._session.query(JobRoleModel).order_by(JobRoleModel.name).all()

    def save(self, entity: JobRoleModel) -> JobRoleModel:
        return self._commit_and_refresh(entity)

    def delete(self, entity_id: uuid.UUID) -> bool:
        entity = self.get_by_id(entity_id)
        if not entity:
            return False
        self._session.delete(entity)
        self._session.commit()
        return True


class InterviewSessionRepository(BaseRepository[InterviewSessionModel]):

    def get_by_id(self, entity_id: uuid.UUID) -> Optional[InterviewSessionModel]:
        return self._session