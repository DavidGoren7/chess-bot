"""Finding the board on screen.

A board is four corners in screen points, always listed as they appear on
screen: top-left, top-right, bottom-right, bottom-left. Which colour sits at
the bottom is worked out later by vision.py.
"""

import json

import cv2
import numpy as np

from . import mouse
from .paths import DATA_DIR

SEARCH_WIDTH = 800
MIN_BOARD_FRACTION = 0.2
SIZE_STEP = 1.025
REFINE_SIZE = 160
REFINE_STEPS = (6.0, 3.0, 1.5, 0.75)
MIN_MATCH_SCORE = 0.45

CORNERS_FILE = DATA_DIR / "corners.json"


def checker_pattern(size):
    """A perfect 8x8 board image. On every chess board the top-left square is
    light, whichever side is at the bottom."""
    cells = np.indices((8, 8)).sum(axis=0) % 2
    pattern = (1 - cells).astype(np.float32) * 255
    return cv2.resize(pattern, (size, size), interpolation=cv2.INTER_NEAREST)


def _coarse_search(gray):
    """Slide checker patterns of many sizes over the image. Returns the best
    (score, x, y, size)."""
    height, width = gray.shape
    best = (-1.0, 0, 0, 0)
    size = int(min(height, width) * MIN_BOARD_FRACTION)
    while size <= min(height, width):
        scores = cv2.matchTemplate(gray, checker_pattern(size), cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score > best[0]:
            best = (float(score), x, y, size)
        size = max(size + 1, int(size * SIZE_STEP))
    return best


def _warp_score(gray, corners, ideal):
    target = np.float32(
        [[0, 0], [REFINE_SIZE, 0], [REFINE_SIZE, REFINE_SIZE], [0, REFINE_SIZE]]
    )
    matrix = cv2.getPerspectiveTransform(np.float32(corners), target)
    warped = cv2.warpPerspective(gray, matrix, (REFINE_SIZE, REFINE_SIZE))
    return float(cv2.matchTemplate(warped, ideal, cv2.TM_CCOEFF_NORMED)[0, 0])


def _refine(gray, corners):
    """Nudge each corner while that improves the match, to absorb the slight
    perspective of a tilted 3D board."""
    ideal = checker_pattern(REFINE_SIZE)
    corners = np.array(corners, dtype=np.float32)
    best = _warp_score(gray, corners, ideal)
    for step in REFINE_STEPS:
        improved = True
        while improved:
            improved = False
            for corner in range(4):
                for axis in range(2):
                    for delta in (-step, step):
                        trial = corners.copy()
                        trial[corner, axis] += delta
                        score = _warp_score(gray, trial, ideal)
                        if score > best + 1e-4:
                            best, corners, improved = score, trial, True
    return corners, best


def find_board(image):
    """Locate a board in a BGR image. Returns (corners in image pixels, score),
    or (None, score) if nothing convincing is there."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    factor = min(1.0, SEARCH_WIDTH / gray.shape[1])
    small = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    small = small.astype(np.float32)

    score, x, y, size = _coarse_search(small)
    if score <= 0:
        return None, score
    start = [[x, y], [x + size, y], [x + size, y + size], [x, y + size]]
    corners, score = _refine(small, start)
    if score < MIN_MATCH_SCORE:
        return None, score
    return corners / factor, score


def ask_for_corners():
    """Manual fallback: hover over each corner and press Enter in the terminal."""
    corners = []
    for name in ("top-left", "top-right", "bottom-right", "bottom-left"):
        input(f"Hover the mouse over the {name} corner of the 64 squares, then press Enter here.")
        corners.append(mouse.position())
    return np.array(corners, dtype=np.float32)


def load_corners():
    """Corners you showed us by hand, if any."""
    if not CORNERS_FILE.exists():
        return None
    return np.array(json.loads(CORNERS_FILE.read_text()), dtype=np.float32)


def save_corners(corners):
    CORNERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CORNERS_FILE.write_text(json.dumps(np.asarray(corners).tolist()))
