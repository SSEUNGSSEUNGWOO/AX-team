import asyncio
import time
from typing import Optional
from models.board import Board
from models.game_state import GameState, PlayerState
from services.ai_agent import AIAgent
from config import GAME_CONFIG

class GameEngine:
    def __init__(self):
        self.state = GameState()
        self._lock = asyncio.Lock()
        self.ai_agent = AIAgent()
        self._running = False

    async def start_game(self):
        self.state = GameState()
        self.state.human.board = Board()
        self.state.ai.board = Board()
        self._running = True
        await asyncio.gather(
            self._player_loop(),
            self._ai_loop()
        )

    async def _player_loop(self):
        while self._running:
            async with self._lock:
                if self.state.human.board.is_game_over():
                    self._running = False
                    self.state.winner = "ai"
                    break
                cleared = self.state.human.board.step()
                self._handle_clear(cleared, target=self.state.ai)
            await asyncio.sleep(GAME_CONFIG["player_tick"])

    async def _ai_loop(self):
        while self._running:
            async with self._lock:
                if self.state.ai.board.is_game_over():
                    self._running = False
                    self.state.winner = "human"
                    break
                move = self.ai_agent.get_best_move(self.state.ai.board)
                if move:
                    self.state.ai.board.apply_move(move)
                cleared = self.state.ai.board.step()
                self._handle_clear(cleared, target=self.state.human)
            await asyncio.sleep(GAME_CONFIG["ai_tick"])

    def _handle_clear(self, cleared_lines: int, target: PlayerState):
        if cleared_lines >= 2:
            penalty = cleared_lines - 1
            target.board.add_garbage_lines(penalty)
            target.score = max(0, target.score)
        sender = self.state.human if target is self.state.ai else self.state.ai
        sender.score += self._calc_score(cleared_lines)
        sender.lines_cleared += cleared_lines

    def _calc_score(self, lines: int) -> int:
        return {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}.get(lines, 0)

    async def apply_player_action(self, action: str):
        async with self._lock:
            board = self.state.human.board
            if action == "left":
                board.move_left()
            elif action == "right":
                board.move_right()
            elif action == "rotate":
                board.rotate()
            elif action == "down":
                board.move_down()
            elif action == "drop":
                board.hard_drop()

    def get_state(self) -> dict:
        return {
            "human": self.state.human.to_dict(),
            "ai": self.state.ai.to_dict(),
            "winner": self.state.winner,
            "running": self._running
        }

    def stop(self):
        self._running = False
# ──────────────────────────────────────────
# AI 플레이어 로직
# ──────────────────────────────────────────

class TetrisAI:
    """
    AI 플레이어: 각 피스에 대해 가능한 모든 배치를 평가하여
    최적의 이동을 결정합니다.
    """

    def __init__(self, board: TetrisBoard):
        self.board = board

    def choose_action(self) -> list[str]:
        """최적 배치를 위한 액션 시퀀스를 반환합니다."""
        best_score = float("-inf")
        best_sequence: list[str] = []

        piece = self.board.current_piece
        if piece is None:
            return []

        # 회전 횟수 0~3
        for rotations in range(4):
            # 시뮬레이션용 보드 복사
            sim_board = self._clone_board()
            sim_piece = sim_board.current_piece

            # 회전 적용
            for _ in range(rotations):
                sim_board.rotate()

            # 가능한 열 위치만큼 이동
            for direction in ["left", "right", "none"]:
                for steps in range(BOARD_WIDTH):
                    trial_board = self._clone_board()
                    trial_piece = trial_board.current_piece

                    # 회전
                    for _ in range(rotations):
                        trial_board.rotate()

                    # 수평 이동
                    if direction == "left":
                        for _ in range(steps):
                            trial_board.move_left()
                    elif direction == "right":
                        for _ in range(steps):
                            trial_board.move_right()
                    elif steps > 0:
                        break  # "none"이면 steps=0만 유효

                    # 하드 드롭 시뮬레이션
                    trial_board.hard_drop()

                    score = self._evaluate(trial_board)
                    if score > best_score:
                        best_score = score
                        best_sequence = (
                            ["rotate"] * rotations
                            + ([direction] * steps if direction != "none" else [])
                            + ["drop"]
                        )

        return best_sequence

    # ── 평가 함수 ───────────────────────────

    def _evaluate(self, board: "TetrisBoard") -> float:
        """보드 상태를 점수화합니다. 높을수록 좋은 배치."""
        grid = board.grid
        heights = self._column_heights(grid)

        aggregate_height = sum(heights)
        complete_lines  = self._complete_lines(grid)
        holes           = self._count_holes(grid, heights)
        bumpiness       = self._bumpiness(heights)

        # 가중치 (Pierre Dellacherie 휴리스틱 참고)
        return (
            -0.510066 * aggregate_height
            + 0.760666 * complete_lines
            - 0.35663  * holes
            - 0.184483 * bumpiness
        )

    def _column_heights(self, grid: list[list[int]]) -> list[int]:
        heights = []
        for col in range(BOARD_WIDTH):
            for row in range(BOARD_HEIGHT):
                if grid[row][col] != 0:
                    heights.append(BOARD_HEIGHT - row)
                    break
            else:
                heights.append(0)
        return heights

    def _complete_lines(self, grid: list[list[int]]) -> int:
        return sum(1 for row in grid if all(cell != 0 for cell in row))

    def _count_holes(self, grid: list[list[int]], heights: list[int]) -> int:
        holes = 0
        for col in range(BOARD_WIDTH):
            top = BOARD_HEIGHT - heights[col]
            for row in range(top + 1, BOARD_HEIGHT):
                if grid[row][col] == 0:
                    holes += 1
        return holes

    def _bumpiness(self, heights: list[int]) -> int:
        return sum(
            abs(heights[i] - heights[i + 1])
            for i in range(len(heights) - 1)
        )

    def _clone_board(self) -> "TetrisBoard":
        """현재 보드를 깊은 복사하여 반환합니다."""
        import copy
        return copy.deepcopy(self.board)


# ──────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────

def main():
    game = TetrisGame()
    game.start()

    print("테트리스 대결을 시작합니다! (Ctrl+C 로 종료)")
    try:
        while True:
            state = game.get_state()
            if not state["running"]:
                break
            if state["winner"]:
                print(f"게임 종료 — 승자: {state['winner']}")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("게임을 종료합니다.")
    finally:
        game.stop()


if __name__ == "__main__":
    main()