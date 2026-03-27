from typing import List, Optional
import copy

BOARD_WIDTH = 10
BOARD_HEIGHT = 20

class Board:
    def __init__(self, width: int = BOARD_WIDTH, height: int = BOARD_HEIGHT):
        self.width = width
        self.height = height
        self.grid: List[List[int]] = [[0] * width for _ in range(height)]
        self.lines_cleared_total: int = 0
        self.last_lines_cleared: int = 0

    def clone(self) -> "Board":
        new_board = Board(self.width, self.height)
        new_board.grid = copy.deepcopy(self.grid)
        new_board.lines_cleared_total = self.lines_cleared_total
        new_board.last_lines_cleared = self.last_lines_cleared
        return new_board

    def is_valid_position(self, cells: List[tuple], offset_x: int = 0, offset_y: int = 0) -> bool:
        for (x, y) in cells:
            nx, ny = x + offset_x, y + offset_y
            if nx < 0 or nx >= self.width:
                return False
            if ny < 0 or ny >= self.height:
                return False
            if self.grid[ny][nx] != 0:
                return False
        return True

    def place_piece(self, cells: List[tuple], color: int) -> bool:
        for (x, y) in cells:
            if x < 0 or x >= self.width or y < 0 or y >= self.height:
                return False
            self.grid[y][x] = color
        return True

    def clear_lines(self) -> int:
        new_grid = [row for row in self.grid if any(cell == 0 for cell in row)]
        cleared = self.height - len(new_grid)
        empty_rows = [[0] * self.width for _ in range(cleared)]
        self.grid = empty_rows + new_grid
        self.lines_cleared_total += cleared
        self.last_lines_cleared = cleared
        return cleared

    def add_garbage_lines(self, count: int, gap: Optional[int] = None) -> None:
        import random
        if gap is None:
            gap = random.randint(0, self.width - 1)
        garbage_row = [9] * self.width
        garbage_row[gap] = 0
        self.grid = self.grid[count:] + [list(garbage_row) for _ in range(count)]

    def get_column_heights(self) -> List[int]:
        heights = []
        for x in range(self.width):
            height = 0
            for y in range(self.height):
                if self.grid[y][x] != 0:
                    height = self.height - y
                    break
            heights.append(height)
        return heights

    def count_holes(self) -> int:
        holes = 0
        for x in range(self.width):
            block_found = False
            for y in range(self.height):
                if self.grid[y][x] != 0:
                    block_found = True
                elif block_found:
                    holes += 1
        return holes

    def get_bumpiness(self) -> int:
        heights = self.get_column_heights()
        return sum(abs(heights[i] - heights[i + 1]) for i in range(len(heights) - 1))

    def get_aggregate_height(self) -> int:
        return sum(self.get_column_heights())

    def is_game_over(self) -> bool:
        return any(self.grid[0][x] != 0 for x in range(self.width))

    def to_dict(self) -> dict:
        return {
            "grid": self.grid,
            "width": self.width,
            "height": self.height,
            "lines_cleared_total": self.lines_cleared_total,
            "last_lines_cleared": self.last_lines_cleared,
        }
