# code/config.py

AI_WEIGHTS = {
    "WEIGHT_HOLES": -0.5,
    "WEIGHT_HEIGHT": -0.3,
    "WEIGHT_BUMPINESS": -0.2,
    "WEIGHT_LINES_CLEARED": 0.8,
}

GAME_CONFIG = {
    "MAX_SEARCH_DEPTH": 2,
    "AI_MOVE_INTERVAL": 0.5,
    "TICK_RATE": 1.0,
    "GARBAGE_LINES_MAP": {1: 0, 2: 1, 3: 2, 4: 4},
}

BOARD_CONFIG = {
    "WIDTH": 10,
    "HEIGHT": 20,
}