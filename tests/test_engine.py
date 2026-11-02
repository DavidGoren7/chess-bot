import time

import chess
import pytest

from chessbot.engine import OwnEngine
from chessbot.engine.evaluate import evaluate

MOVETIME = 1.0


def best(fen, movetime=MOVETIME):
    return OwnEngine().choose_move(chess.Board(fen), movetime)


@pytest.mark.parametrize(
    "fen, expected",
    [
        ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8"),  # back rank
        ("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "h5f7"),  # scholar's mate
        ("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1", "f7f8"),  # queen and king
    ],
)
def test_finds_mate_in_one(fen, expected):
    assert best(fen).uci() == expected


def test_mate_in_two_is_delivered():
    board = chess.Board("2bqkbn1/2pppp2/np2N3/r3P1p1/p2N2B1/5Q2/PPPPKPP1/RNB2r2 w - - 0 1")
    engine = OwnEngine()
    board.push(engine.choose_move(board, 3.0))
    assert engine.last_score > 90_000


def test_takes_hanging_queen():
    assert best("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1").uci() == "e4d5"


def test_does_not_lose_queen_to_pawn():
    board = chess.Board("4k3/8/2p5/8/8/8/8/3QK3 w - - 0 1")
    board.push(best(board.fen()))
    queen = board.pieces(chess.QUEEN, chess.WHITE).pop()
    assert not board.is_attacked_by(chess.BLACK, queen)


def test_avoids_stalemating_when_winning():
    board = chess.Board("7k/8/5K2/6Q1/8/8/8/8 w - - 0 1")
    board.push(OwnEngine().choose_move(board, MOVETIME))
    assert not board.is_stalemate()


def test_winning_side_avoids_repeating_the_position():
    # White is a rook up and shuffling. Going back to e1 would repeat a
    # position already on the move stack, which scores as a draw.
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1")
    for san in ("Re2", "Kf8", "Re1", "Kg8", "Re2", "Kf8"):
        board.push_san(san)
    move = OwnEngine().choose_move(board, MOVETIME)
    assert board.san(move) != "Re1"


def test_plays_whole_game_legally_against_itself():
    board = chess.Board()
    engine = OwnEngine()
    for _ in range(40):
        if board.is_game_over():
            break
        move = engine.choose_move(board, 0.05)
        assert move in board.legal_moves
        board.push(move)


def test_respects_time_limit():
    board = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P1B2/2PBPN2/PP1N1PPP/R2QK2R w KQ - 0 9")
    start = time.monotonic()
    OwnEngine().choose_move(board, 0.5)
    assert time.monotonic() - start < 0.8


def test_evaluation_is_symmetric():
    fen = "r1bqkb1r/pp1p1ppp/2n1pn2/2p5/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 5"
    board = chess.Board(fen)
    assert evaluate(board) == evaluate(board.mirror())
