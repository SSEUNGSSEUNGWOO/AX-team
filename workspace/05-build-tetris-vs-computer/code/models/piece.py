from dataclasses import dataclass, field
from typing import List, Tuple
import copy

TETROMINOES = {
    'I': {
        'color': '#00FFFF',
        'shapes': [
            [(0,0),(0,1),(0,2),(0,3)],
            [(0,0),(1,0),(2,0),(3,0)],
            [(0,0),(0,1),(0,2),(0,3)],
            [(0,0),(1,0),(2,0),(3,0)],
        ]
    },
    'O': {
        'color': '#FFFF00',
        'shapes': [
            [(0,0),(0,1),(1,0),(1,1)],
            [(0,0),(0,1),(1,0),(1,1)],
            [(0,0),(0,1),(1,0),(1,1)],
            [(0,0),(0,1),(1,0),(1,1)],
        ]
    },
    'T': {
        'color': '#FF00FF',
        'shapes': [
            [(0,1),(1,0),(1,1),(1,2)],
            [(0,0),(1,0),(1,1),(2,0)],
            [(1,0),(1,1),(1,2),(2,1)],
            [(0,1),(1,0),(1,1),(2,1)],
        ]
    },
    'S': {
        'color': '#00FF00',
        'shapes': [
            [(0,1),(0,2),(1,0),(1,1)],
            [(0,0),(1,0),(1,1),(2,1)],
            [(0,1),(0,2),(1,0),(1,1)],
            [(0,0),(1,0),(1,1),(2,1)],
        ]
    },
    'Z': {
        'color': '#FF0000',
        'shapes': [
            [(0,0),(0,1),(1,1),(1,2)],
            [(0,1),(1,0),(1,1),(2,0)],
            [(0,0),(0,1),(1,1),(1,2)],
            [(0,1),(1,0),(1,1),(2,0)],
        ]
    },
    'J': {
        'color': '#0000FF',
        'shapes': [
            [(0,0),(1,0),(1,1),(1,2)],
            [(0,0),(0,1),(1,0),(2,0)],
            [(1,0),(1,1),(1,2),(2,2)],
            [(0,1),(1,1),(2,0),(2,1)],
        ]
    },
    'L': {
        'color': '#FF7F00',
        'shapes': [
            [(0,2),(1,0),(1,1),(1,2)],
            [(0,0),(1,0),(2,0),(2,1)],
            [(1,0),(1,1),(1,2),(2,0)],
            [(0,0),(0,1),(1,1),(2,1)],
        ]
    },
}

PIECE_TYPES = list(TETROMINOES.keys())


@dataclass
class Piece:
    piece_type: str
    rotation: int = 0
    row: int = 0
    col: int = 3

    def __post_init__(self):
        if self.piece_type not in TETROMINOES:
            raise ValueError(f"Unknown piece type: {self.piece_type}")

    @property
    def color(self) -> str:
        return TETROMINOES[self.piece_type]['color']

    @property
    def cells(self) -> List[Tuple[int, int]]:
        shape = TETROMINOES[self.piece_type]['shapes'][self.rotation % 4]
        return [(self.row + r, self.col + c) for r, c in shape]

    def rotated(self, direction: int = 1) -> 'Piece':
        new_rotation = (self.rotation + direction) % 4
        return Piece(
            piece_type=self.piece_type,
            rotation=new_rotation,
            row=self.row,
            col=self.col,
        )

    def moved(self, dr: int = 0, dc: int = 0) -> 'Piece':
        return Piece(
            piece_type=self.piece_type,
            rotation=self.rotation,
            row=self.row + dr,
            col=self.col + dc,
        )

    def clone(self) -> 'Piece':
        return copy.copy(self)
