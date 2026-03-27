from dataclasses import dataclass, field
from typing import Optional
from code.models.board import Board
from code.models.piece import Piece


@dataclass
class PlayerState:
    board: Board = field(default_factory=Board)
    current_piece: Optional[Piece] = None
    next_piece: Optional[Piece] = None
    score: int = 0
    level: int = 1
    lines_cleared: int = 0
    is_game_over: bool = False
    pending_garbage_lines: int = 0

    def add_score(self, cleared_lines: int) -> None:
        points = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        self.score += points.get(cleared_lines, 0) * self.level

    def update_level(self) -> None:
        self.level = self.lines_cleared // 10 + 1


@dataclass
class GameState:
    human: PlayerState = field(default_factory=PlayerState)
    ai: PlayerState = field(default_factory=PlayerState)
    tick: int = 0
    is_running: bool = False

    def is_finished(self) -> bool:
        return self.human.is_game_over or self.ai.is_game_over

    def winner(self) -> Optional[str]:
        if not self.is_finished():
            return None
        if self.human.is_game_over and self.ai.is_game_over:
            return "draw"
        return "ai" if self.human.is_game_over else "human"