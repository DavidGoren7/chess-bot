"""The smallest possible bot. Copy this to write your own, then add it in the app
with Add Bot.

Your file needs a choose_move function. It receives a python-chess board (your
own copy, so changing it is fine) and the seconds you have to think, and returns
one legal move. NAME is optional and is what the app shows.
"""

import random

NAME = "Random Mover"


def choose_move(board, movetime):
    return random.choice(list(board.legal_moves))
