import stat
import textwrap
from pathlib import Path

import chess
import pytest

from chessbot import bots, game

EXAMPLE = Path(__file__).parent.parent / "examples" / "random_bot.py"

# A tiny UCI engine, so these tests don't need Stockfish.
FAKE_UCI = """#!/bin/sh
while read -r command rest; do
    case "$command" in
        uci) echo "id name Tiny Engine"; echo "uciok" ;;
        isready) echo "readyok" ;;
        go) echo "bestmove e2e4" ;;
        quit) exit 0 ;;
    esac
done
"""


@pytest.fixture(autouse=True)
def empty_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(bots, "DATA_DIR", tmp_path / "data")


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(textwrap.dedent(text))
    return path


def fake_engine(tmp_path):
    path = tmp_path / "tiny"
    path.write_text(FAKE_UCI)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_built_in_engine_always_listed_first():
    assert bots.installed_bots() == [bots.BUILT_IN_BOT]


def test_installs_python_bot_and_it_plays():
    bot = bots.install(EXAMPLE)
    assert bot.name == "Random Mover"
    assert bot in bots.installed_bots()
    board = chess.Board()
    assert bots.load(bot).choose_move(board, 0.1) in board.legal_moves


def test_installs_uci_engine_and_it_plays(tmp_path):
    bot = bots.install(fake_engine(tmp_path))
    assert (bot.name, bot.kind) == ("Tiny Engine", bots.UCI)
    engine = bots.load(bot)
    try:
        assert engine.choose_move(chess.Board(), 0.1).uci() == "e2e4"
    finally:
        engine.close()


def test_rejects_a_file_that_is_not_a_chess_engine(tmp_path):
    path = write(tmp_path, "notes.txt", "just some text")
    with pytest.raises(bots.BotError):
        bots.install(path)
    assert bots.installed_bots() == [bots.BUILT_IN_BOT]


def test_rejects_python_file_without_choose_move(tmp_path):
    with pytest.raises(bots.BotError, match="choose_move"):
        bots.install(write(tmp_path, "empty.py", "x = 1\n"))


def test_rejects_python_file_that_fails_to_load(tmp_path):
    with pytest.raises(bots.BotError, match="failed to load"):
        bots.install(write(tmp_path, "broken.py", "import nonexistent_module\n"))


def test_same_bot_cannot_be_installed_twice():
    bots.install(EXAMPLE)
    with pytest.raises(bots.BotError, match="already installed"):
        bots.install(EXAMPLE)


def test_bots_with_the_same_name_stay_distinct(tmp_path):
    first = bots.install(EXAMPLE)
    second = bots.install(write(tmp_path, "other.py", 'NAME = "Random Mover"\ndef choose_move(b, t): pass\n'))
    assert first.name != second.name


def test_remove_forgets_the_bot_but_keeps_the_file():
    bot = bots.install(EXAMPLE)
    bots.remove(bot)
    assert bots.installed_bots() == [bots.BUILT_IN_BOT]
    assert EXAMPLE.exists()


def test_a_deleted_bot_gives_a_clear_error(tmp_path):
    path = write(tmp_path, "gone.py", "def choose_move(b, t): pass\n")
    bot = bots.install(path)
    path.unlink()
    with pytest.raises(bots.BotError, match="moved or deleted"):
        bots.load(bot)


def make_game(engine):
    return game.Game(None, chess.Board(), None, chess.WHITE, engine, None, 0.1, {})


class StubBot:
    name = "Stub"

    def __init__(self, choose):
        self.choose_move = choose


def test_bot_choosing_an_illegal_move_stops_cleanly():
    bad = StubBot(lambda board, movetime: chess.Move.from_uci("e2e5"))
    with pytest.raises(bots.BotError, match="illegal"):
        make_game(bad)._choose_move()


def test_bot_crashing_stops_cleanly():
    def explode(board, movetime):
        raise RuntimeError("boom")

    with pytest.raises(bots.BotError, match="crashed"):
        make_game(StubBot(explode))._choose_move()


def test_stockfish_if_present():
    path = Path(__file__).parent.parent / "engines" / "stockfish"
    if not path.exists():
        pytest.skip("Stockfish isn't in the repo; download it to run this")
    assert "Stockfish" in bots.install(path).name
