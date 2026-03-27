from config import AI_WEIGHTS

class AIEvaluator:
    def __init__(self, weights: dict = None):
        self.weights = weights or AI_WEIGHTS

    def evaluate_board(self, board) -> float:
        try:
            holes = self._count_holes(board)
            height = self._aggregate_height(board)
            bumpiness = self._bumpiness(board)
            lines = self._complete_lines(board)

            score = (
                self.weights["WEIGHT_LINES"] * lines
                - self.weights["WEIGHT_HOLES"] * holes
                - self.weights["WEIGHT_HEIGHT"] * height
                - self.weights["WEIGHT_BUMPINESS"] * bumpiness
            )
            return score
        except Exception:
            return 0.0

    def _column_heights(self, board) -> list:
        heights = []
        for col in range(board.width):
            h = 0
            for row in range(board.height):
                if board.grid[row][col] != 0:
                    h = board.height - row
                    break
            heights.append(h)
        return heights

    def _aggregate_height(self, board) -> int:
        return sum(self._column_heights(board))

    def _count_holes(self, board) -> int:
        holes = 0
        for col in range(board.width):
            block_found = False
            for row in range(board.height):
                if board.grid[row][col] != 0:
                    block_found = True
                elif block_found:
                    holes += 1
        return holes

    def _bumpiness(self, board) -> int:
        heights = self._column_heights(board)
        return sum(abs(heights[i] - heights[i+1]) for i in range(len(heights)-1))

    def _complete_lines(self, board) -> int:
        return sum(1 for row in board.grid if all(cell != 0 for cell in row))


evaluate_board = AIEvaluator().evaluate_board
