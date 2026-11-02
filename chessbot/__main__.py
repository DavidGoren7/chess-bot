"""Run the bot from the command line: python -m chessbot"""

import argparse
import sys

import chess

from . import bots, capture, game, locate, mouse


def check_permissions(needs_mouse):
    missing = []
    if not capture.has_screen_recording():
        missing.append("Screen Recording")
    if needs_mouse and not mouse.has_accessibility():
        missing.append("Accessibility")
    if missing:
        sys.exit(
            f"macOS hasn't given this app {' or '.join(missing)} permission.\n"
            "Open System Settings > Privacy & Security, turn on the app you ran this "
            "from (for example Terminal) under each one, then restart that app."
        )


def parse_args():
    parser = argparse.ArgumentParser(prog="chessbot", description=__doc__)
    parser.add_argument("--bot", help="installed bot name, or a path to a bot file")
    parser.add_argument("--side", choices=["white", "black"], help="side the bot plays (default: the side at the bottom)")
    parser.add_argument("--movetime", type=float, default=2.0, help="seconds to think per move")
    parser.add_argument("--recalibrate", action="store_true", help="show the board corners by hand")
    parser.add_argument("--fen", help="join a game in progress at this position (needs --side)")
    parser.add_argument("--flipped", action="store_true", help="with --fen: the bot's side is at the top")
    parser.add_argument("--watch", action="store_true", help="only print moves; never touch the mouse")
    args = parser.parse_args()
    if args.fen and not args.side:
        parser.error("--fen needs --side")
    return args


def main():
    args = parse_args()
    check_permissions(needs_mouse=not args.watch)
    if args.recalibrate:
        locate.save_corners(locate.ask_for_corners())

    settings = game.Settings(movetime=args.movetime, fen=args.fen or "", flipped=args.flipped, watch=args.watch)
    if args.side:
        settings.side = chess.WHITE if args.side == "white" else chess.BLACK
    try:
        if args.bot:
            settings.bot = bots.find(args.bot)
        print("To stop: Ctrl+C, or push the mouse into the top-left corner of the screen.", flush=True)
        game.play(settings, log=lambda message: print(message, flush=True))
    except (KeyboardInterrupt, mouse.StopRequested):
        print("Stopped.")
    except bots.BotError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
