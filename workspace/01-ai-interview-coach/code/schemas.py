# code/schemas.py
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class JobRole(str, Enum):
    DEVELOPER = "개발"
    MARKETING = "마케팅"
    PLANNING = "기획"
    DESIGN = "디자인"


class CareerLevel(str, Enum):
    ENTRY = "신입"
    MID = "3년"
    SENIOR = "5년+"


# ── 질문 생성 ──────────────────────────────────────────

class QuestionGenerateRequest(BaseModel):
    job_role: JobRole = Field(..., description="직군")
    career_level: CareerLevel = Field(..., description="경력 레벨")
    count: int = Field(default=10, ge=10, le=20, description="생성 질문 수")


class QuestionGenerateResponse(BaseModel):
    session_id: str = Field(..., description="세션 식별자")
    job_role: JobRole
    career_level: CareerLevel
    questions: list[str] = Field(..., description="생성된 예상 질문 목록")


# ── 답변 피드백 ────────────────────────────────────────

class AnswerFeedbackRequest(BaseModel):
    session_id: str = Field(..., description="세션 식별자")
    question: str = Field(..., description="질문 내용")
    answer: str = Field(..., min_length=10, description="사용자 답변")


class STARScore(BaseModel):
    situation: int = Field(..., ge=0, le=100, description="상황 설명 점수")
    task: int = Field(..., ge=0, le=100, description="과제 정의 점수")
    action: int = Field(..., ge=0, le=100, description="행동 서술 점수")
    result: int = Field(..., ge=0, le=100, description="결과 기술 점수")


class DetailScore(BaseModel):
    logic: int = Field(..., ge=0, le=100, description="논리성")
    specificity: int = Field(..., ge=0, le=100, description="구체성")
    job_fit: int = Field(..., ge=0, le=100, description="직무적합성")


class AnswerFeedbackResponse(BaseModel):
    session_id: str
    question: str
    star_score: STARScore
    detail_score: DetailScore
    overall_score: int = Field(..., ge=0, le=100, description="종합 점수")
    feedback_text: str = Field(..., description="STAR 기반 서술형 피드백")
    improvement_points: list[str] = Field(..., description="개선 포인트 목록")


# ── 세션 관리 ──────────────────────────────────────────

class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: str


class SessionSummaryResponse(BaseModel):
    session_id: str
    job_role: JobRole
    career_level: CareerLevel
    total_questions: int
    answered_count: int
    average_score: Optional[float] = Field(None, description="세션 평균 점수")