"""Playing a game: finding the board, watching it, and making moves.

The app window and the command line both come through play().
"""

import time
from dataclasses import dataclass
from pathlib import Path

import chess
import cv2

from . import bots, capture, locate, mouse, vision
from .bots import BotError
from .paths import DATA_DIR
from .profiles import profile_for

CONFIRM_POLLS = 2  # a move must look the same twice, to skip a piece held mid-drag
VERIFY_SECONDS = 3.0
MOVE_ATTEMPTS = 2
PROMOTION_PICKER_DELAY = 0.3
WARN_AFTER_POLLS = 25
SEARCH_PAUSE = 1.0
HINT_AFTER_SEARCHES = 8
DEBUG_DIR = DATA_DIR / "debug"
SPUN = "spun"  # our move can't be seen because the whole board has turned


@dataclass
class Settings:
    bot: bots.Bot = bots.BUILT_IN_BOT
    movetime: float = 2.0
    side: chess.Color | None = None  # None means the side at the bottom
    fen: str = ""  # join a game in progress at this position
    flipped: bool = False  # with fen: the bot's side is at the top
    watch: bool = False  # only report moves, never touch the mouse


class Game:
    def __init__(self, view, board, orientation, side, engine, profile, movetime, templates, log=print):
        self.view = view
        self.board = board
        self.orientation = orientation
        self.side = side  # None means only watch, never touch the mouse
        self.engine = engine
        self.profile = profile
        self.movetime = movetime
        self.templates = templates
        self.log = log
        self.reference = None

    def run(self):
        self.reference = self._wait_for_frame()
        while not self.board.is_game_over(claim_draw=True):
            if self.board.turn == self.side:
                self._play_our_move()
            else:
                self._wait_for_move()
        self.log(f"Game over: {self.board.result(claim_draw=True)}")

    def _wait_for_frame(self):
        while True:
            frame = self.view.stable_frame()
            if frame is not None:
                return frame

    def _record(self, moves, frame):
        for move in moves:
            color = self.board.turn
            move = vision.promotion_piece(move, frame, self.orientation, self.templates, color)
            who = "Bot" if color == self.side else "Opponent"
            self.log(f"{who}: {self.board.san(move)}")
            self.board.push(move)
        self.reference = frame

    def _wait_for_move(self, our_move=None):
        """Watch until the side to move has clearly played.

        The Mac Chess app spins the board after every move in a two-human game,
        so nothing can be compared while it's turned away. With `our_move`, that
        move hasn't been recorded yet: wait for the board to spin back, then
        read our move and the reply together from a frame in the same pose.
        """
        pending = None
        confirmations = 0
        confused_polls = 0
        while True:
            frame = self._wait_for_frame()
            changes = vision.square_changes(self.reference, frame)
            if our_move is None:
                moves = vision.explain(changes, self.board, self.orientation)
            elif vision.board_turned(changes):
                moves = None
            else:
                moves = vision.explain(changes, self.board, self.orientation, follow_replies=True)
                if not moves or len(moves) != 2 or moves[0] != our_move:
                    moves = None

            if moves is None:
                confused_polls += 1
                pending = None
                if confused_polls == WARN_AFTER_POLLS and our_move is None:
                    self._report_confusion(frame)
                continue

            confused_polls = 0
            if not moves:
                pending = None
            elif moves == pending:
                confirmations += 1
                if confirmations >= CONFIRM_POLLS:
                    self._record(moves, frame)
                    return
            else:
                pending = moves
                confirmations = 1

    def _report_confusion(self, frame):
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBUG_DIR / f"unexplained_ply{self.board.ply()}.png"
        cv2.imwrite(str(path), frame)
        self.log(
            "The board changed in a way no legal move explains, so I'm not clicking. "
            f"Is it covered, or did the game end? Saved what I see to {path}."
        )

    def _choose_move(self):
        try:
            move = self.engine.choose_move(self.board, self.movetime)
        except Exception as error:
            raise BotError(f"{self.engine.name} crashed: {error}") from error
        if move not in self.board.legal_moves:
            raise BotError(f"{self.engine.name} chose an illegal move: {move}")
        if move.promotion is not None:
            return chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
        return move

    def _play_our_move(self):
        move = self._choose_move()
        for _ in range(MOVE_ATTEMPTS):
            self._perform(move)
            moves, frame = self._see_our_move(move)
            if moves is SPUN:
                self._after_spin(move, frame)
                return
            if moves is not None:
                self._record(moves, frame)
                return

        self.log(f"{self.board.san(move)} didn't show up on the board. Please play it by hand.")
        self._wait_for_move()

    def _after_spin(self, move, frame):
        after = self.board.copy(stack=False)
        after.push(move)
        if after.is_game_over(claim_draw=True):
            self._record([move], frame)
        else:
            self._wait_for_move(our_move=move)

    def _perform(self, move):
        start = self.view.center(*self.orientation.cell(move.from_square))
        end = self.view.center(*self.orientation.cell(move.to_square))
        resting_place = mouse.position()
        mouse.activate_window_at(*start)
        mouse.drag(start, end)
        if move.promotion is not None and self.profile.click_to_promote:
            time.sleep(PROMOTION_PICKER_DELAY)
            mouse.click(*end)
        mouse.move_to(*resting_place)

    def _see_our_move(self, move):
        """Check the board shows `move`, perhaps with the reply already played.
        Returns (moves, frame): moves is a list, SPUN, or None if nothing landed."""
        deadline = time.monotonic() + VERIFY_SECONDS
        while time.monotonic() < deadline:
            frame = self.view.stable_frame()
            if frame is None:
                continue
            changes = vision.square_changes(self.reference, frame)
            if vision.board_turned(changes):
                return SPUN, frame
            moves = vision.explain(changes, self.board, self.orientation, follow_replies=True)
            if moves and moves[0] == move:
                return moves, frame
        return None, None


def to_screen_points(corners, scale, monitor):
    return corners / scale + (monitor["left"], monitor["top"])


def _candidate_corners(screens):
    """Where the board might be: found on each display, then shown by hand."""
    for screen in screens:
        image, scale = screen.grab()
        corners, _ = locate.find_board(image)
        if corners is not None:
            yield screen, to_screen_points(corners, scale, screen.monitor)
    saved = locate.load_corners()
    if saved is not None:
        yield screens[0], saved


def _try_to_find_board(screens, expect_start):
    """One look for a board. With `expect_start`, a location only counts if the
    starting position shows there, which rules out a board found one rank off."""
    for screen, corners in _candidate_corners(screens):
        view = vision.BoardView(screen, corners)
        frame = view.stable_frame()
        if frame is None:
            continue
        orientation = vision.read_start_position(frame) if expect_start else None
        if orientation is not None or not expect_start:
            return view, frame, orientation
    return None


def wait_for_board(expect_start, log):
    """Keep looking until a board appears. Returns (view, frame, orientation)."""
    screens = capture.all_screens()
    log("Looking for a new game on your screen...")
    searches = 0
    while True:
        mouse.check_stop()
        found = _try_to_find_board(screens, expect_start)
        if found is not None:
            return found
        searches += 1
        if searches == HINT_AFTER_SEARCHES:
            log(
                "Still looking. The whole board must be visible, at the starting position. "
                "In the Mac Chess app, drag a corner of the board to tilt it flat."
            )
        time.sleep(SEARCH_PAUSE)


def play(settings, log=print):
    """Find a board and play it until the game ends or you stop it."""
    view, frame, orientation = wait_for_board(expect_start=not settings.fen, log=log)

    if settings.fen:
        board = chess.Board(settings.fen)
        orientation = vision.Orientation((settings.side == chess.WHITE) != settings.flipped)
        templates = {}
    else:
        board = chess.Board()
        templates = vision.learn_pieces(frame, orientation)

    if settings.watch:
        side = None
    elif settings.side is not None:
        side = settings.side
    else:
        side = chess.WHITE if orientation.white_at_bottom else chess.BLACK

    app = mouse.app_at(*view.center(4, 4))
    profile = profile_for(app.bundleIdentifier() if app is not None else None)

    engine = bots.load(settings.bot)
    try:
        if side is None:
            log("Found the board. Watching only.")
        else:
            log(f"Found the board. {engine.name} is playing {chess.COLOR_NAMES[side]}.")
        Game(view, board, orientation, side, engine, profile, settings.movetime, templates, log).run()
    finally:
        engine.close()
