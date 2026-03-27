from code.models.board import Board
from code.models.piece import Piece
from code.services.ai_evaluator import AIEvaluator
from code.config import MAX_SEARCH_DEPTH

class AIAgent:
    def __init__(self):
        self.evaluator = AIEvaluator()
        self.max_search = MAX_SEARCH_DEPTH

    def get_best_move(self, board: Board, piece: Piece) -> dict:
        best_score = float('-inf')
        best_move = {"rotation": 0, "x": board.width // 2}
        search_count = 0

        for rotation in range(4):
            rotated = piece.rotate(rotation)
            for x in range(board.width):
                if search_count >= self.max_search:
                    return best_move
                search_count += 1

                if not board.is_valid_position(rotated, x, 0):
                    continue

                y = board.drop_height(rotated, x)
                if y is None:
                    continue

                test_board = board.copy()
                test_board.place_piece(rotated, x, y)
                score = self.evaluator.evaluate_board(test_board)

                if score > best_score:
                    best_score = score
                    best_move = {"rotation": rotation, "x": x}

        return best_move
class TetrisGame:
    def __init__(self):
        self.board = Board()
        self.player = Player()
        self.computer = Computer()
        self.current_piece = None
        self.computer_piece = None
        self.score = 0
        self.computer_score = 0
        self.game_over = False
        self.computer_game_over = False

    def new_piece(self):
        self.current_piece = Piece.random()

    def new_computer_piece(self):
        self.computer_piece = Piece.random()
        self.computer_move = self.computer.get_best_move(
            self.computer.board, self.computer_piece
        )

    def apply_computer_move(self):
        if self.computer_move is None:
            self.computer_game_over = True
            return

        rotation = self.computer_move["rotation"]
        x = self.computer_move["x"]
        rotated = self.computer_piece.rotate(rotation)
        y = self.computer.board.drop_height(rotated, x)

        if y is None:
            self.computer_game_over = True
            return

        self.computer.board.place_piece(rotated, x, y)
        lines = self.computer.board.clear_lines()
        self.computer_score += lines * 100

    def run(self):
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tetris vs Computer")
        clock = pygame.time.Clock()

        self.new_piece()
        self.new_computer_piece()

        fall_time = 0
        fall_speed = 500
        computer_fall_time = 0
        computer_fall_speed = 300

        while True:
            delta = clock.tick(60)
            fall_time += delta
            computer_fall_time += delta

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                self.player.handle_input(event, self.board, self.current_piece)

            if fall_time >= fall_speed:
                fall_time = 0
                if not self.player.move_down(self.board, self.current_piece):
                    self.board.place_piece(
                        self.current_piece.current_rotation(),
                        self.current_piece.x,
                        self.current_piece.y
                    )
                    lines = self.board.clear_lines()
                    self.score += lines * 100
                    self.new_piece()
                    if not self.board.is_valid_position(
                        self.current_piece.current_rotation(),
                        self.current_piece.x, 0
                    ):
                        self.game_over = True

            if computer_fall_time >= computer_fall_speed and not self.computer_game_over:
                computer_fall_time = 0
                self.apply_computer_move()
                self.new_computer_piece()

            screen.fill(BLACK)
            self.board.draw(screen, BOARD_OFFSET_X, BOARD_OFFSET_Y)
            self.computer.board.draw(screen, COMPUTER_BOARD_OFFSET_X, BOARD_OFFSET_Y)
            draw_score(screen, self.score, self.computer_score)

            if self.game_over:
                draw_game_over(screen, "Player")
            if self.computer_game_over:
                draw_game_over(screen, "Computer")

            pygame.display.flip()


if __name__ == "__main__":
    game = TetrisGame()
    game.run()