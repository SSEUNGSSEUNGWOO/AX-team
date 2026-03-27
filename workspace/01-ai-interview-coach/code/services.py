# code/services.py
"""
비즈니스 로직 레이어
- 세션 관리 (생성/조회/종료)
- 질문 생성 오케스트레이션
- 답변 피드백 오케스트레이션
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, Sequence

# ---------------------------------------------------------------------------
# 도메인 열거형
# ---------------------------------------------------------------------------

class CareerLevel(str, Enum):
    JUNIOR = "신입"
    MID = "3년"
    SENIOR = "5년+"


class JobRole(str, Enum):
    DEVELOPER = "개발"
    MARKETING = "마케팅"
    PLANNING = "기획"
    DESIGN = "디자인"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass
class Question:
    id: str
    content: str
    order: int


@dataclass
class FeedbackScore:
    logic: float        # 논리성  0~10
    specificity: float  # 구체성  0~10
    job_fit: float      # 직무적합성 0~10

    @property
    def total(self) -> float:
        return round((self.logic + self.specificity + self.job_fit) / 3, 2)


@dataclass
class AnswerFeedback:
    question_id: str
    raw_answer: str
    star_feedback: str      # STAR 구조 피드백 텍스트
    improvement: str        # 개선 제안
    score: FeedbackScore
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InterviewSession:
    id: str
    user_id: str
    job_role: JobRole
    career_level: CareerLevel
    questions: list[Question] = field(default_factory=list)
    feedbacks: list[AnswerFeedback] = field(default_factory=list)
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 포트(Port) — 외부 의존성 추상화
# ---------------------------------------------------------------------------

class QuestionGeneratorPort(Protocol):
    """LLM 질문 생성 어댑터가 구현해야 할 인터페이스"""

    def generate(
        self,
        job_role: JobRole,
        career_level: CareerLevel,
        count: int,
    ) -> Sequence[str]:
        ...


class FeedbackGeneratorPort(Protocol):
    """LLM 피드백 생성 어댑터가 구현해야 할 인터페이스"""

    def generate(
        self,
        question: str,
        answer: str,
        job_role: JobRole,
        career_level: CareerLevel,
    ) -> tuple[str, str, FeedbackScore]:
        """Returns (star_feedback, improvement, score)"""
        ...


class SessionRepositoryPort(Protocol):
    """세션 영속성 어댑터가 구현해야 할 인터페이스"""

    def save(self, session: InterviewSession) -> None: ...
    def find_by_id(self, session_id: str) -> InterviewSession | None: ...
    def find_by_user(self, user_id: str) -> list[InterviewSession]: ...
    def delete(self, session_id: str) -> None: ...


# ---------------------------------------------------------------------------
# 서비스 예외
# ---------------------------------------------------------------------------

class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"세션을 찾을 수 없습니다: {session_id}")


class SessionAlreadyClosedError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"이미 종료된 세션입니다: {session_id}")


class QuestionNotFoundError(Exception):
    def __init__(self, question_id: str) -> None:
        super().__init__(f"질문을 찾을 수 없습니다: {question_id}")


# ---------------------------------------------------------------------------
# 서비스 레이어
# ---------------------------------------------------------------------------

class InterviewSessionService:
    """
    세션 생명주기 + 질문/피드백 오케스트레이션 담당.
    모든 외부 의존성은 포트로 주입받아 테스트 가능성 확보.
    """

    DEFAULT_QUESTION_COUNT = 10

    def __init__(
        self,
        session_repo: SessionRepositoryPort,
        question_generator: QuestionGeneratorPort,
        feedback_generator: FeedbackGeneratorPort,
    ) -> None:
        self._repo = session_repo
        self._question_gen = question_generator
        self._feedback_gen = feedback_generator

    # ------------------------------------------------------------------
    # 세션 관리
    # ------------------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        job_role: JobRole,
        career_level: CareerLevel,
        question_count: int = DEFAULT_QUESTION_COUNT,
    ) -> InterviewSession:
        """새 면접 세션 생성 + 질문 자동 생성"""
        if not (10 <= question_count <= 20):
            raise ValueError("질문 수는 10~20 사이여야 합니다.")

        raw_questions = self._question_gen.generate(
            job_role=job_role,
            career_level=career_level,
            count=question_count,
        )

        questions = [
            Question(id=str(uuid.uuid4()), content=content, order=idx)
            for idx, content in enumerate(raw_questions, start=1)
        ]

        session = InterviewSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            job_role=job_role,
            career_level=career_level,
            questions=questions,
        )

        self._repo.save(session)
        return session

    def get_session(self, session_id: str) -> InterviewSession:
        session = self._repo.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def list_sessions(self, user_id: str) -> list[InterviewSession]:
        return self._repo.find_by_user(user_id)

    def close_session(self, session_id: str) -> InterviewSession:
        session = self._get_active_session(session_id)
        session.status = SessionStatus.COMPLETED
        session.updated_at = datetime.now(timezone.utc)
        self._repo.save(session)
        return session

    # ------------------------------------------------------------------
    # 질문 조회
    # ------------------------------------------------------------------

    def get_questions(self, session_id: str) -> list[Question]:
        session = self.get_session(session_id)
        return sorted(session.questions