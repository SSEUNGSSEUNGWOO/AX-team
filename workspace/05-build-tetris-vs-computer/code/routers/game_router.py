from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio

from models.game_state import GameState
from services.game_engine import GameEngine
from config import GAME_CONFIG

router = APIRouter(prefix="/game", tags=["game"])

_engine: Optional[GameEngine] = None


def get_engine() -> GameEngine:
    global _engine
    if _engine is None:
        raise HTTPException(status_code=400, detail="Game not started")
    return _engine


class StartRequest(BaseModel):
    difficulty: Optional[str] = "medium"


class PlayerInputRequest(BaseModel):
    action: str  # "left" | "right" | "rotate" | "down" | "drop"


@router.post("/start")
async def start_game(req: StartRequest):
    global _engine
    _engine = GameEngine(difficulty=req.difficulty)
    _engine.start()
    return {"status": "started", "difficulty": req.difficulty}


@router.post("/input")
async def player_input(req: PlayerInputRequest):
    engine = get_engine()
    valid_actions = {"left", "right", "rotate", "down", "drop"}
    if req.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"Invalid action: {req.action}")
    result = engine.apply_player_action(req.action)
    return {"status": "ok", "result": result}


@router.post("/ai-step")
async def ai_step():
    engine = get_engine()
    result = engine.step_ai()
    return {"status": "ok", "result": result}


@router.get("/state")
async def get_state():
    engine = get_engine()
    state: GameState = engine.get_state()
    return state.to_dict()


@router.post("/reset")
async def reset_game():
    global _engine
    _engine = None
    return {"status": "reset"}
# main.py
from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="Tetris Battle API")

app.include_router(router, prefix="/game")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}