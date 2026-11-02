from pathlib import Path

import chess
import cv2
import numpy as np
import pytest

from chessbot import game as bot
from chessbot import vision
from chessbot.locate import find_board

FIXTURES = Path(__file__).parent / "fixtures"
WHITE_BOTTOM = vision.Orientation(True)
OPENING = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "O-O", "Nxe4"]
FRAMES = [
    "mac_after_e5",
    "mac_after_nf3",
    "mac_after_nc6",
    "mac_after_bc4",
    "mac_after_nf6",
    "mac_after_castle",
    "mac_after_nxe4",
]


def load(name):
    """A real screenshot of the Mac Chess app. These stay out of the repo, since
    they show Apple's artwork, so these tests only run where they exist."""
    path = FIXTURES / f"{name}.jpg"
    if not path.exists():
        pytest.skip("real screenshots aren't in the repo")
    return cv2.imread(str(path))


@pytest.fixture(scope="module")
def corners():
    found, _ = find_board(load(FRAMES[0]))
    return found


@pytest.fixture(scope="module")
def frames(corners):
    return [vision.warp(load(name), corners) for name in FRAMES]


def position_after(count):
    board = chess.Board()
    for san in OPENING[:count]:
        board.push_san(san)
    return board


def test_finds_real_3d_board_automatically():
    found, score = find_board(load("mac_start_flat"))
    assert found is not None
    expected = [[243, 133], [730, 133], [747, 628], [220, 630]]
    # Bottom-left is a touch loose by eye, so allow about a quarter of a square.
    assert np.abs(found - np.array(expected)).max() < 15


def test_reads_start_position_and_orientation():
    image = load("mac_start_flat")
    found, _ = find_board(image)
    frame = vision.warp(image, found)
    assert vision.read_start_position(frame).white_at_bottom


def test_steeply_tilted_board_is_rejected_not_misread():
    image = load("mac_start_tilted")
    found, _ = find_board(image)
    assert found is None or vision.read_start_position(vision.warp(image, found)) is None


@pytest.mark.parametrize("index, san", list(enumerate(OPENING[2:])))
def test_identifies_each_real_move(frames, index, san):
    board = position_after(2 + index)
    changes = vision.square_changes(frames[index], frames[index + 1])
    assert vision.explain(changes, board, WHITE_BOTTOM) == [board.parse_san(san)]


def test_no_change_means_no_move(frames):
    changes = vision.square_changes(frames[0], frames[0])
    assert vision.explain(changes, position_after(2), WHITE_BOTTOM) == []


def test_rejected_drag_counts_as_no_move(frames, corners):
    rejected = vision.warp(load("mac_rejected_drag"), corners)
    changes = vision.square_changes(frames[5], rejected)
    assert vision.explain(changes, position_after(7), WHITE_BOTTOM) == []


def test_untangles_our_move_and_instant_reply(frames):
    board = position_after(6)
    changes = vision.square_changes(frames[4], frames[6])
    moves = vision.explain(changes, board, WHITE_BOTTOM, follow_replies=True)
    assert [board.san(moves[0])] == ["O-O"]
    assert moves[1].uci() == "f6e4"


def test_board_covered_by_a_window_is_not_a_move(frames):
    covered = frames[0].copy()
    covered[100:420, 60:460] = (235, 235, 235)
    changes = vision.square_changes(frames[0], covered)
    assert vision.explain(changes, position_after(2), WHITE_BOTTOM) is None


# Flat boards, drawn the way websites draw them.
LIGHT = (210, 235, 235)
DARK = (86, 149, 115)
HIGHLIGHT = np.array((60, 200, 230), dtype=np.float32)


def draw_board(board, cell=70, highlight=(), white_at_bottom=True, offset=(150, 90), size=(900, 1300)):
    canvas = np.full((*size, 3), 38, dtype=np.uint8)
    orientation = vision.Orientation(white_at_bottom)
    left, top = offset
    for square in chess.SQUARES:
        row, column = orientation.cell(square)
        x, y = left + column * cell, top + row * cell
        color = LIGHT if (row + column) % 2 == 0 else DARK
        patch = canvas[y:y + cell, x:x + cell]
        patch[:] = color
        if square in highlight:
            patch[:] = (patch * 0.5 + HIGHLIGHT * 0.5).astype(np.uint8)
        piece = board.piece_at(square)
        if piece:
            fill = (245, 245, 245) if piece.color == chess.WHITE else (40, 40, 40)
            center = (x + cell // 2, y + cell // 2)
            radius = cell // 4 + piece.piece_type * 2
            cv2.circle(canvas, center, radius, fill, -1, cv2.LINE_AA)
            cv2.circle(canvas, center, radius, (20, 20, 20), 2, cv2.LINE_AA)
            cv2.putText(canvas, piece.symbol().upper(), (center[0] - 9, center[1] + 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 120, 120), 2)
    return canvas


@pytest.mark.parametrize(
    "cell, offset, size",
    [
        (70, (150, 90), (900, 1300)),
        (90, (400, 60), (982, 1512)),
        (45, (800, 200), (982, 1512)),
        (200, (300, 100), (1964, 3024)),  # Retina
    ],
)
def test_finds_flat_board_accurately(cell, offset, size):
    found, _ = find_board(draw_board(chess.Board(), cell=cell, offset=offset, size=size))
    left, top = offset
    right, bottom = left + 8 * cell, top + 8 * cell
    expected = np.array([[left, top], [right, top], [right, bottom], [left, bottom]])
    # Must land well inside the border that vision ignores on every square.
    assert np.abs(found - expected).max() < cell * vision.MARGIN / vision.CELL / 2


def test_flat_board_from_black_side():
    image = draw_board(chess.Board(), white_at_bottom=False)
    found, _ = find_board(image)
    assert not vision.read_start_position(vision.warp(image, found)).white_at_bottom


def flat(board, **kwargs):
    corners = [[150, 90], [710, 90], [710, 650], [150, 650]]
    return vision.warp(draw_board(board, **kwargs), corners)


def replay(sans, start=None):
    """Play moves on drawn boards with last-move highlights, as websites show
    them, and check each one is read back correctly."""
    board = chess.Board(start) if start else chess.Board()
    previous = flat(board)
    for san in sans:
        move = board.parse_san(san)
        after = board.copy()
        after.push(move)
        current = flat(after, highlight=(move.from_square, move.to_square))
        changes = vision.square_changes(previous, current)
        assert vision.explain(changes, board, WHITE_BOTTOM) == [move], san
        board = after
        previous = current
    return board


def test_flat_game_with_highlights():
    replay(["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "d4", "Nf6", "Nf3", "Bf5", "Bc4", "e6", "O-O"])


def test_en_passant():
    replay(["exd6"], start="4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")


def test_queenside_castling():
    replay(["O-O-O"], start="4k3/8/8/8/8/8/8/R3K3 w Q - 0 1")


def test_identifies_underpromotion():
    start = chess.Board()
    templates = vision.learn_pieces(flat(start), WHITE_BOTTOM)
    board = chess.Board("6k1/P7/8/8/8/8/8/6K1 w - - 0 1")
    after = board.copy()
    after.push(chess.Move.from_uci("a7a8n"))
    frame = flat(after)

    moves = vision.explain(vision.square_changes(flat(board), frame), board, WHITE_BOTTOM)
    assert moves == [chess.Move.from_uci("a7a8q")]  # provisional, all four look alike here
    resolved = vision.promotion_piece(moves[0], frame, WHITE_BOTTOM, templates, chess.WHITE)
    assert resolved.promotion == chess.KNIGHT


def test_unclear_promotion_on_3d_board_stays_a_queen():
    # A real black bishop on c1 of the Mac board, too round to tell from a rook.
    corners, _ = find_board(load("mac_start_flat"))
    templates = vision.learn_pieces(vision.warp(load("mac_start_flat"), corners), WHITE_BOTTOM)
    frame = load("mac_promoted_bishop")
    assert vision.identify_promotion(frame, (7, 2), chess.BLACK, templates) == chess.QUEEN


class SlidingView(vision.BoardView):
    """Shows a piece gliding across the board, then coming to rest."""

    def __init__(self, frames):
        self.frames = list(frames)

    def frame(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]


def test_slow_slide_is_not_a_settled_board(monkeypatch):
    monkeypatch.setattr(vision, "POLL_SECONDS", 0.005)
    monkeypatch.setattr(vision, "SETTLE_SECONDS", 0.05)
    empty = flat(chess.Board("8/8/8/8/8/8/8/8 w - - 0 1"))
    frames = []
    for y in range(40, 240, 2):
        frame = empty.copy()
        cv2.circle(frame, (300, y), 22, (40, 40, 40), -1)
        frames.append(frame)

    settled = SlidingView(frames).stable_frame()
    assert np.array_equal(settled, frames[-1])


# The whole game loop, with a scripted screen in place of the real one.
class ScriptedView:
    def __init__(self, board, opponent_moves):
        self.board = board
        self.opponent_moves = iter(opponent_moves)
        self.drags = []

    def stable_frame(self, timeout=5.0):
        if self.board.turn == chess.BLACK:
            move = next(self.opponent_moves, None)
            if move is not None:
                self.board.push(self.board.parse_san(move))
        return flat(self.board)

    def center(self, row, column):
        return float(column), float(row)


class ScriptedEngine:
    name = "script"

    def __init__(self, moves):
        self.moves = iter(moves)

    def choose_move(self, board, movetime):
        return board.parse_san(next(self.moves))

    def close(self):
        pass


def test_full_game_loop(monkeypatch):
    screen_board = chess.Board()
    view = ScriptedView(screen_board, ["e5", "Nc6", "Nf6"])

    def fake_perform(self, move):
        view.drags.append(move)
        screen_board.push(move)

    monkeypatch.setattr(bot.Game, "_perform", fake_perform)
    engine = ScriptedEngine(["e4", "Bc4", "Qh5", "Qxf7#"])
    game = bot.Game(view, chess.Board(), WHITE_BOTTOM, chess.WHITE, engine, None, 0.01, {})
    game.run()

    assert game.board.is_checkmate()
    assert [m.uci() for m in view.drags] == ["e2e4", "f1c4", "d1h5", "h5f7"]


class FrameSequenceView:
    """Plays back a fixed list of frames, repeating the last."""

    def __init__(self, frames):
        self.frames = list(frames)

    def stable_frame(self, timeout=5.0):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]


def test_mac_board_spinning_between_moves(monkeypatch):
    # These frames have the Game Log closed, so the board sits elsewhere.
    corners, _ = find_board(load("mac_start_flat"))
    start = vision.warp(load("mac_start_flat"), corners)
    black_at_bottom = vision.warp(load("mac_spin_black_bottom"), corners)
    back = vision.warp(load("mac_spin_after_e5"), corners)
    assert vision.board_turned(vision.square_changes(start, black_at_bottom))

    view = FrameSequenceView([black_at_bottom, black_at_bottom, black_at_bottom, back])
    monkeypatch.setattr(bot.Game, "_perform", lambda self, move: None)
    engine = ScriptedEngine(["e4"])
    game = bot.Game(view, chess.Board(), WHITE_BOTTOM, chess.WHITE, engine, None, 0.01, {})
    game.reference = start
    game._play_our_move()

    assert [m.uci() for m in game.board.move_stack] == ["e2e4", "e7e5"]


def test_game_loop_retries_a_move_that_did_not_land(monkeypatch):
    screen_board = chess.Board()
    view = ScriptedView(screen_board, [])
    attempts = []

    def fake_perform(self, move):
        attempts.append(move)
        if len(attempts) == 2:
            screen_board.push(move)

    monkeypatch.setattr(bot.Game, "_perform", fake_perform)
    monkeypatch.setattr(bot, "VERIFY_SECONDS", 0.02)
    engine = ScriptedEngine(["e4"])
    game = bot.Game(view, chess.Board(), WHITE_BOTTOM, chess.WHITE, engine, None, 0.01, {})
    game.reference = flat(chess.Board())
    game._play_our_move()

    assert len(attempts) == 2
    assert game.board.peek().uci() == "e2e4"
