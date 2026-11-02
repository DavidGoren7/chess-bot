# Chess Bot

Open a chess game, press Play, and the bot takes over. It watches the board on your screen, works out each move, thinks of a reply, and plays it with the mouse. It works from pixels alone, so it doesn't need to know which app the board is in.

Mac only.

## Getting it running

You'll need Python 3 from [python.org](https://www.python.org/downloads/).

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

Then build the app:

```bash
scripts/build_app.sh
```

That creates `dist/Chess Bot.app`, which you can double-click or drag into Applications. To skip building, run `.venv/bin/python run_app.py` instead.

**macOS permissions.** The first time you open it, macOS needs your OK. In System Settings → Privacy & Security, turn on Chess Bot under both of these, then quit and reopen it. The app has buttons that take you to each page.

- **Screen Recording**, so it can see the board
- **Accessibility**, so it can move the mouse

Each new build counts as a new app to macOS, so you'll need to turn these on again after rebuilding.

## Playing

1. Open a new game, with the whole board visible.
2. Open Chess Bot and press **Play**. It stays on top of other windows, near the right edge of your screen. Make sure it isn't covering the board.
3. The bot finds the board by itself and starts playing. If no game is open yet, it keeps looking until one is.

Press **Stop** at any time, or push the mouse into the top-left corner of the screen.

With the default setting, the bot plays whichever colour is at the bottom of the board.

### In the Mac Chess app

1. Press **⌘N** and set players to **Human vs. Human**.
2. **Tilt the board flat:** drag downward from the wood frame near a bottom corner, until it stops changing. The bot can't find a steeply tilted board by itself.
3. Keep the Game Log panel closed, or open it before pressing Play. Opening it mid-game shrinks the board.

**The bot plays White and you play Black here.** In a two-human game, Chess spins the board 180° after every move so the next player faces it. The bot waits for the board to spin back after your move, then reads your move from there, which only works if it saw the board from White's side first.

If the game ends on your move, the bot may not notice, so press Stop.

### On a website such as chess.com

**Read this first:** chess.com's [Fair Play Policy](https://www.chess.com/legal/fair-play) bans engines and bots in games against other people, and accounts get closed for it. Unrated games with a friend are reported to be allowed only if you tell them first, so check the policy yourself. Games against chess.com's own computer opponents aren't games against other users.

## Installing your own bots

Press **Add Bot…** and pick a file. Two kinds work:

- **A UCI chess engine.** This is the standard format, so most engines work, such as [Stockfish](https://stockfishchess.org/download/). Download the Mac version and choose the program file.
- **A Python file** with a `choose_move(board, movetime)` function. It gets a [python-chess](https://python-chess.readthedocs.io/) board and returns a legal move. Start from [examples/random_bot.py](examples/random_bot.py).

The file stays where it is on your Mac, so don't move it after adding it. **Remove** only takes a bot off the list. It doesn't delete the file.

A bot is a program running on your Mac, so only add ones you trust. Inside the packaged app, Python bots can only import python-chess, numpy and common standard modules such as `random`, `math` and `collections`.

Your bots, settings and any saved board position live in `~/Library/Application Support/Chess Bot`.

## Things to know

- The bot borrows your mouse for a moment on its turn. Leave the mouse alone while it moves.
- Don't move, resize or cover the board during a game. If you do, press Stop and start again.
- It doesn't read the clock. It takes the **Time per move** you set, so lower that for fast games.
- If the board changes in a way no legal move explains, it refuses to click and tells you.
- It has to see a game from the starting position, because it follows the moves rather than recognising every piece. To join a game already in progress, paste the position as FEN and choose a side, with the bot's side at the bottom.
- If it can't find the board by itself, press **Show Me Where the Board Is** and hold the mouse over each corner as it asks.

## How strong is it?

At 1 second per move, the built-in engine scored 7.5/8 against Stockfish limited to 1320 Elo, 6/8 against 1600, and 4/8 against 1900. That suggests somewhere around 1900 on Stockfish's scale, but 8 games per level is a small sample and it isn't a chess.com rating. Installing Stockfish as a bot is far stronger.

## Command line

The app isn't required:

```bash
.venv/bin/python -m chessbot --bot "Stockfish 19" --movetime 1
```

Add `--watch` to print the moves it sees without touching the mouse, or `--help` for the rest.

## How it works

| File | Job |
| --- | --- |
| `chessbot/app.py` | The app window |
| `chessbot/game.py` | Finds the game, then runs the watch, think, move loop |
| `chessbot/locate.py` | Finds the board by matching a perfect checker pattern, then nudges the corners to fit perspective |
| `chessbot/vision.py` | Straightens the board, sees which squares changed, and finds the legal move that explains them |
| `chessbot/engine/` | The built-in alpha-beta engine, and the UCI connection |
| `chessbot/bots.py` | Installing and loading bots |
| `chessbot/mouse.py` | Moves the mouse through macOS Quartz events |

Run the tests with:

```bash
.venv/bin/python -m pytest
```

The screenshots of the Mac Chess app aren't in this repo, because they show Apple's artwork, so the tests that need them skip themselves.

## Licence

GPL-3.0, because this project uses [python-chess](https://github.com/niklasf/python-chess), which is GPL-3.0. See [LICENSE](LICENSE).
