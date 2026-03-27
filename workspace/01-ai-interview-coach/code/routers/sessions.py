import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Session as SessionModel, JobCategory, JobLevel

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    user_id: str
    job_category: str
    job_level: str


class SessionOut(BaseModel):
    id: str
    user_id: str
    job_category: str
    job_level: str
    created_at: str


@router.post("/", response_model=SessionOut, status_code=201)
async def create_session(req: SessionCreate, db: AsyncSession = Depends(get_db)):
    try:
        cat = JobCategory[req.job_category.upper()]
        lvl = JobLevel[req.job_level.upper()]
    except KeyError:
        raise HTTPException(400, "잘못된 job_category 또는 job_level")

    session = SessionModel(
        user_id=req.user_id,
        job_category=cat,
        job_level=lvl,
    )
    db.add(session)
    await db.flush()
    return SessionOut(
        id=str(session.id),
        user_id=session.user_id,
        job_category=session.job_category.value,
        job_level=session.job_level.value,
        created_at=session.created_at.isoformat(),
    )


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.get(SessionModel, session_id)
    if not result:
        raise HTTPException(404, "세션 없음")
    return SessionOut(
        id=str(result.id),
        user_id=result.user_id,
        job_category=result.job_category.value,
        job_level=result.job_level.value,
        created_at=result.created_at.isoformat(),
    )


@router.delete("/{session_id}", status_code=204)
async def close_session(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.get(SessionModel, session_id)
    if not result:
        raise HTTPException(404, "세션 없음")
    result.ended_at = datetime.now(timezone.utc)
    await db.flush()
