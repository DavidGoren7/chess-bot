"""The bots you can play with: the built-in engine plus any you install.

An installed bot is either a UCI chess engine (a program, like Stockfish) or a
Python file defining choose_move(board, movetime). See examples/random_bot.py.
Bots stay where they are on disk, since UCI engines often need files next to
them. Installing just remembers the path.
"""

import asyncio
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

import chess.engine

from .engine import OwnEngine, UciEngine
from .paths import DATA_DIR

BUILT_IN = "built-in"
UCI = "uci"
PYTHON = "python"


class BotError(Exception):
    """A bot couldn't be installed or didn't behave. The message is for you."""


@dataclass(frozen=True)
class Bot:
    name: str
    kind: str
    path: str = ""


BUILT_IN_BOT = Bot("Built-in engine", BUILT_IN)


def _registry():
    return DATA_DIR / "bots.json"


def _save(bots):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entries = [{"name": b.name, "kind": b.kind, "path": b.path} for b in bots]
    _registry().write_text(json.dumps(entries, indent=2))


def installed_bots():
    """Every installed bot, built-in first."""
    bots = [BUILT_IN_BOT]
    if _registry().exists():
        bots += [Bot(**entry) for entry in json.loads(_registry().read_text())]
    return bots


class PythonBot:
    def __init__(self, path):
        spec = importlib.util.spec_from_file_location("installed_bot", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            raise BotError(f"{Path(path).name} failed to load: {error}") from error
        if not callable(getattr(module, "choose_move", None)):
            raise BotError(f"{Path(path).name} has no choose_move(board, movetime) function.")
        self.module = module
        self.name = getattr(module, "NAME", Path(path).stem)

    def choose_move(self, board, movetime):
        return self.module.choose_move(board.copy(), movetime)

    def close(self):
        pass


def _kind_of(path):
    return PYTHON if Path(path).suffix == ".py" else UCI


def _open(kind, path):
    if kind == BUILT_IN:
        return OwnEngine()
    if not Path(path).exists():
        raise BotError(f"Can't find {path}. Was it moved or deleted?")
    if kind == PYTHON:
        return PythonBot(path)
    try:
        return UciEngine(path)
    except (OSError, chess.engine.EngineError, asyncio.TimeoutError) as error:
        raise BotError(f"{Path(path).name} didn't start as a UCI chess engine: {error}") from error


def load(bot):
    """Start a bot, ready to choose moves."""
    return _open(bot.kind, bot.path)


def describe_file(path):
    """Try out a bot file. Returns the Bot it would install as, without
    installing it."""
    path = str(Path(path).expanduser().resolve())
    kind = _kind_of(path)
    engine = _open(kind, path)
    try:
        return Bot(engine.name, kind, path)
    finally:
        engine.close()


def install(path):
    """Check that a file really is a bot, then remember it."""
    bot = describe_file(path)
    bots = installed_bots()
    if any(existing.path == bot.path for existing in bots):
        raise BotError(f"{bot.name} is already installed.")
    names = {existing.name for existing in bots}
    if bot.name in names:
        bot = Bot(f"{bot.name} ({Path(bot.path).name})", bot.kind, bot.path)
    _save(bots[1:] + [bot])
    return bot


def remove(bot):
    """Forget an installed bot. Its file stays where it is."""
    _save([b for b in installed_bots()[1:] if b != bot])


def find(name_or_path):
    """An installed bot by name, or a bot file by path without installing it."""
    for bot in installed_bots():
        if bot.name == name_or_path:
            return bot
    if Path(name_or_path).expanduser().exists():
        return describe_file(name_or_path)
    raise BotError(f"No installed bot or file called {name_or_path}.")
