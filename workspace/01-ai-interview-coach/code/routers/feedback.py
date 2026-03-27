import os, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_pipeline import InterviewAIPipeline

router = APIRouter(prefix="/feedback", tags=["feedback"])
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = InterviewAIPipeline(api_key=os.environ.get("OPENAI_API_KEY"))
    return _pipeline


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    job_role: str
    career_level: str


class ScoreOut(BaseModel):
    logic: int
    specificity: int
    job_fit: int
    total: int


class FeedbackResponse(BaseModel):
    id: str
    star_situation: str
    star_task: str
    star_action: str
    star_result: str
    missing_elements: list[str]
    overall_comment: str
    score: ScoreOut
    improvement_tips: list[str]


@router.post("/evaluate", response_model=FeedbackResponse)
async def evaluate_answer(req: FeedbackRequest):
    try:
        result = get_pipeline().evaluate_answer(
            question=req.question,
            answer=req.answer,
            role=req.job_role,
            level=req.career_level,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}")

    return FeedbackResponse(
        id=str(uuid.uuid4()),
        star_situation=result.star.situation,
        star_task=result.star.task,
        star_action=result.star.action,
        star_result=result.star.result,
        missing_elements=result.star.missing_elements,
        overall_comment=result.star.overall_comment,
        score=ScoreOut(
            logic=result.score.logic,
            specificity=result.score.specificity,
            job_fit=result.score.job_fit,
            total=result.score.total,
        ),
        improvement_tips=result.improvement_tips,
    )
