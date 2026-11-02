"""Any UCI chess engine, such as Stockfish, run as a separate program."""

import chess.engine


class UciEngine:
    def __init__(self, path):
        self.engine = chess.engine.SimpleEngine.popen_uci(str(path))
        self.name = self.engine.id.get("name", "UCI engine")

    def choose_move(self, board, movetime):
        return self.engine.play(board, chess.engine.Limit(time=movetime)).move

    def close(self):
        self.engine.quit()
