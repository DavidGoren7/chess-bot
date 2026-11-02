"""Turning screen images into chess moves.

The bot always knows the full position, so it never has to read pieces off the
screen one by one. It compares two pictures of the board, sees which squares
changed, and asks which legal move would have changed exactly those squares.
"""

import time

import chess
import cv2
import numpy as np

from . import mouse

CELL = 64
BOARD = CELL * 8
MARGIN = CELL // 8  # ignore square edges, where hover and highlight borders sit
PATCH = CELL // 6  # corner patches that show the bare square colour

PIXEL_THRESHOLD = 36  # how far a pixel must be from the square colour to be a piece
# Comparing one square across two frames cancels its texture, so this can be
# low enough to see a dark piece leaving a dark square.
CHANGE_THRESHOLD = 16
MIN_CHANGED = 0.10  # share of a square that must change for the square to count
MAX_UNEXPLAINED = 0.45  # a change this big outside the move means something is wrong
MIN_MARGIN = 0.03  # how far the best explanation must beat the runner-up
TURNED_MIN_CELLS = 20  # this many changed squares means the whole board moved

EMPTY_MAX = 0.06  # an empty square has almost no pixels off its background
OCCUPIED_MIN = 0.10

STABLE_DIFFERENCE = 1.5
POLL_SECONDS = 0.12


def warp(image, corners):
    """Straighten the board in `image` into a BOARD x BOARD picture."""
    target = np.float32([[0, 0], [BOARD, 0], [BOARD, BOARD], [0, BOARD]])
    matrix = cv2.getPerspectiveTransform(np.float32(corners), target)
    return cv2.warpPerspective(image, matrix, (BOARD, BOARD), flags=cv2.INTER_AREA)


def _cells(frame):
    """Brightness of each square, as a (8, 8, CELL, CELL) array."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.int16)
    return gray.reshape(8, CELL, 8, CELL).transpose(0, 2, 1, 3)


def _foreground(frame):
    """Each square with its own background colour subtracted, so a tinted
    highlight behind a piece doesn't look like a new shape."""
    cells = _cells(frame)
    corners = np.concatenate(
        [
            cells[:, :, :PATCH, :PATCH],
            cells[:, :, :PATCH, -PATCH:],
            cells[:, :, -PATCH:, :PATCH],
            cells[:, :, -PATCH:, -PATCH:],
        ],
        axis=2,
    )
    # The median of the four corner means survives one corner being covered
    # by a piece from the next square or a coordinate label.
    background = np.median(corners.reshape(8, 8, 4, PATCH, -1).mean(axis=(3, 4)), axis=2)
    return cells - background.reshape(8, 8, 1, 1).astype(np.int16)


def square_changes(before, after):
    """For each of the 64 screen cells, the share of pixels that changed.

    A highlight appearing or fading changes the bare square but not the piece
    drawn on top of it. So a pixel only counts as changed if it differs both as
    it stands (which clears the piece) and with the square colour removed
    (which clears the bare square).
    """
    raw = np.abs(_cells(before) - _cells(after))
    relative = np.abs(_foreground(before) - _foreground(after))
    difference = np.minimum(raw, relative)
    inner = difference[:, :, MARGIN:-MARGIN, MARGIN:-MARGIN]
    return (inner > CHANGE_THRESHOLD).mean(axis=(2, 3))


def occupancy(frame):
    """For each cell, the share of pixels that are not plain background."""
    inner = np.abs(_foreground(frame))[:, :, MARGIN:-MARGIN, MARGIN:-MARGIN]
    return (inner > PIXEL_THRESHOLD).mean(axis=(2, 3))


class Orientation:
    def __init__(self, white_at_bottom):
        self.white_at_bottom = white_at_bottom

    def cell(self, square):
        """Screen (row, column) of a chess square; row 0 is the top of the screen."""
        rank = chess.square_rank(square)
        file_index = chess.square_file(square)
        if self.white_at_bottom:
            return 7 - rank, file_index
        return rank, 7 - file_index


def read_start_position(frame):
    """Check that a frame shows the starting position. Returns an Orientation,
    or None if the middle of the board isn't empty and the back ranks aren't
    full, which usually means the board was located wrongly."""
    filled = occupancy(frame)
    middle = filled[2:6]
    back = np.concatenate([filled[:2], filled[6:]])
    if np.median(middle) > EMPTY_MAX or np.median(back) < OCCUPIED_MIN:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    foreground = np.abs(_foreground(frame)).transpose(0, 2, 1, 3).reshape(BOARD, BOARD)
    pieces = foreground > PIXEL_THRESHOLD
    half = BOARD // 2
    top = gray[:half][pieces[:half]]
    bottom = gray[half:][pieces[half:]]
    if top.size == 0 or bottom.size == 0:
        return None
    return Orientation(bool(np.median(bottom) > np.median(top)))


def learn_pieces(frame, orientation):
    """Store how every piece looks, taken from the starting position."""
    brightness = _cells(frame)
    foreground = _foreground(frame)
    templates = {}
    board = chess.Board()
    for square, piece in board.piece_map().items():
        cell = orientation.cell(square)
        templates.setdefault((piece.piece_type, piece.color), (brightness[cell], foreground[cell]))
    return templates


def identify_promotion(frame, cell, color, templates):
    """Which piece did a pawn become? Compares the promotion square against the
    learned pieces, looking only at piece pixels since the learned piece may
    have stood on the other square colour. Queen if there's nothing to compare."""
    if not templates:
        return chess.QUEEN
    observed = _cells(frame)[cell]
    observed_shape = np.abs(_foreground(frame)[cell]) > PIXEL_THRESHOLD

    def mismatch(piece):
        brightness, foreground = templates[(piece, color)]
        shape = np.abs(foreground) > PIXEL_THRESHOLD
        either = shape | observed_shape
        return np.abs(observed - brightness)[either].mean() if either.any() else 0.0

    return min((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), key=mismatch)


def changed_cells(before, after, orientation):
    """Screen cells whose contents differ between two positions."""
    cells = set()
    for square in chess.SQUARES:
        if before.piece_at(square) != after.piece_at(square):
            cells.add(orientation.cell(square))
    return cells


def board_turned(changes):
    """True when far more squares changed than any move could touch."""
    return int((changes >= MIN_CHANGED).sum()) >= TURNED_MIN_CELLS


def _score(changes, predicted):
    """How well a set of predicted cells explains what was seen. Returns
    (score, fully explained?)."""
    score = 0.0
    explained = True
    for row in range(8):
        for column in range(8):
            value = float(changes[row, column])
            if (row, column) in predicted:
                score += value
                explained = explained and value >= MIN_CHANGED
            else:
                if value >= MIN_CHANGED:
                    score -= value
                explained = explained and value < MAX_UNEXPLAINED
    return score, explained


def _hypotheses(board, follow_replies):
    """Every line of play that might have happened: no move, one move, and
    optionally that move plus a reply. Promotions are grouped, since all four
    choices change the same squares."""
    yield [], board
    for move in board.legal_moves:
        if move.promotion not in (None, chess.QUEEN):
            continue
        after = board.copy(stack=False)
        after.push(move)
        yield [move], after
        if follow_replies:
            for reply in after.legal_moves:
                if reply.promotion not in (None, chess.QUEEN):
                    continue
                final = after.copy(stack=False)
                final.push(reply)
                yield [move, reply], final


def explain(changes, board, orientation, follow_replies=False):
    """Find the moves that explain the observed changes.

    Returns a list of moves (empty when nothing has happened), or None when no
    legal line clearly fits. None means: do not act on this picture.
    """
    candidates = []
    for moves, after in _hypotheses(board, follow_replies):
        predicted = changed_cells(board, after, orientation)
        score, explained = _score(changes, predicted)
        if explained:
            candidates.append((score, moves))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < MIN_MARGIN:
        return None
    return candidates[0][1]


def promotion_piece(move, frame, orientation, templates, color):
    """Replace a provisional queen promotion with the piece actually shown."""
    if move.promotion is None:
        return move
    piece = identify_promotion(frame, orientation.cell(move.to_square), color, templates)
    return chess.Move(move.from_square, move.to_square, promotion=piece)


class BoardView:
    """A live view of one board on screen, with corners in screen points."""

    def __init__(self, screen, corners):
        self.screen = screen
        self.corners = np.float32(corners)
        low = np.floor(self.corners.min(axis=0)).astype(int)
        high = np.ceil(self.corners.max(axis=0)).astype(int)
        self.region = {
            "left": int(low[0]),
            "top": int(low[1]),
            "width": int(high[0] - low[0]),
            "height": int(high[1] - low[1]),
        }
        self.origin = low.astype(np.float32)
        target = np.float32([[0, 0], [8, 0], [8, 8], [0, 8]])
        self.to_screen = cv2.getPerspectiveTransform(target, self.corners)

    def frame(self):
        image, scale = self.screen.grab(self.region)
        return warp(image, (self.corners - self.origin) * scale)

    def center(self, row, column):
        """Screen point at the middle of a cell."""
        point = np.float32([[[column + 0.5, row + 0.5]]])
        x, y = cv2.perspectiveTransform(point, self.to_screen)[0, 0]
        return float(x), float(y)

    def stable_frame(self, timeout=5.0):
        """Wait for animations to finish. None if the picture never settles."""
        deadline = time.monotonic() + timeout
        previous = self.frame()
        while time.monotonic() < deadline:
            mouse.check_stop()
            time.sleep(POLL_SECONDS)
            current = self.frame()
            if cv2.absdiff(previous, current).mean() < STABLE_DIFFERENCE:
                return current
            previous = current
        return None
