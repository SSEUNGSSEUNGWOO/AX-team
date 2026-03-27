import os, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

from ai_pipeline import InterviewAIPipeline, JobRole, CareerLevel

router = APIRouter(prefix="/questions", tags=["questions"])
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = InterviewAIPipeline(api_key=os.environ.get("OPENAI_API_KEY"))
    return _pipeline


class QuestionRequest(BaseModel):
    job_role: str = Field(..., description="직군 (개발/마케팅/기획/디자인)")
    career_level: str = Field(..., description="경력 (신입/3년/5년+)")
    count: int = Field(default=10, ge=5, le=20)
    focus_area: Optional[str] = None


class QuestionItem(BaseModel):
    index: int
    content: str
    category: str


class QuestionResponse(BaseModel):
    request_id: str
    job_role: str
    career_level: str
    questions: list[QuestionItem]


@router.post("/generate", response_model=QuestionResponse)
async def generate_questions(req: QuestionRequest):
    try:
        questions = get_pipeline().generate_questions(
            role=req.job_role,
            level=req.career_level,
            count=req.count,
            keywords=req.focus_area or "",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}")

    return QuestionResponse(
        request_id=str(uuid.uuid4()),
        job_role=req.job_role,
        career_level=req.career_level,
        questions=[QuestionItem(index=q.index, content=q.content, category=q.category)
                   for q in questions],
    )


@router.get("/roles")
async def get_roles():
    return {
        "job_roles": ["개발", "마케팅", "기획", "디자인"],
        "career_levels": ["신입", "3년", "5년+"],
    }
