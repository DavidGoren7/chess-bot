"""Our own chess engine: picks a move by searching the game tree.

Iterative deepening alpha-beta (negamax form) with a transposition table,
quiescence search, null-move pruning and late-move reductions.
"""

import time

import chess

from .evaluate import MATERIAL, evaluate

INFINITY = 1_000_000
MATE = 100_000
MATE_THRESHOLD = MATE - 1_000
MAX_DEPTH = 64
MAX_QUIESCE_DEPTH = 8
TT_LIMIT = 2_000_000
DELTA_MARGIN = 200

EXACT, LOWER, UPPER = 0, 1, 2


class _OutOfTime(Exception):
    pass


class OwnEngine:
    name = "own engine"

    def __init__(self):
        self.tt = {}
        self.nodes = 0
        self.depth_reached = 0
        self.last_score = 0

    def close(self):
        pass

    def choose_move(self, board, movetime):
        """Return the best move found within `movetime` seconds."""
        legal = list(board.legal_moves)
        if not legal:
            raise ValueError("no legal moves in this position")
        if len(legal) == 1:
            return legal[0]

        history = self._position_history(board)
        working = board.copy(stack=False)
        self.nodes = 0
        self.depth_reached = 0
        self.killers = [[None, None] for _ in range(MAX_DEPTH * 2)]
        self.history_scores = {}
        self.deadline = time.monotonic() + movetime
        if len(self.tt) > TT_LIMIT:
            self.tt.clear()

        best_move = legal[0]
        ordered = legal
        for depth in range(1, MAX_DEPTH):
            self.seen = set(history)
            try:
                best_move, score, ordered = self._search_root(working, ordered, depth, best_move)
            except _OutOfTime:
                break
            self.depth_reached = depth
            self.last_score = score
            if abs(score) >= MATE_THRESHOLD:
                break
            # A new iteration takes several times longer than the last, so
            # starting one this late would mostly be thrown away.
            if time.monotonic() > self.deadline - movetime * 0.5:
                break
        return best_move

    @staticmethod
    def _position_history(board):
        """Positions already played in the game, for spotting repetitions."""
        replay = board.root()
        keys = {replay._transposition_key()}
        for move in board.move_stack:
            replay.push(move)
            keys.add(replay._transposition_key())
        keys.discard(board._transposition_key())
        return keys

    def _search_root(self, board, moves, depth, previous_best):
        moves = sorted(moves, key=lambda m: m != previous_best)
        alpha, beta = -INFINITY, INFINITY
        best_move = moves[0]
        scored = []
        for move in moves:
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            except _OutOfTime:
                board.pop()
                raise
            board.pop()
            scored.append((score, move))
            if score > alpha:
                alpha = score
                best_move = move
        scored.sort(key=lambda item: item[0], reverse=True)
        return best_move, alpha, [move for _, move in scored]

    def _negamax(self, board, depth, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 1023 and time.monotonic() >= self.deadline:
            raise _OutOfTime

        key = board._transposition_key()
        if board.halfmove_clock >= 100 or key in self.seen:
            return 0

        in_check = board.is_check()
        if in_check:
            depth += 1
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply, 0)

        original_alpha = alpha
        tt_move = None
        entry = self.tt.get(key)
        if entry is not None:
            tt_depth, tt_flag, tt_score, tt_move = entry
            if tt_depth >= depth:
                tt_score = self._from_tt(tt_score, ply)
                if tt_flag == EXACT:
                    return tt_score
                if tt_flag == LOWER and tt_score >= beta:
                    return tt_score
                if tt_flag == UPPER and tt_score <= alpha:
                    return tt_score

        if (
            depth >= 3
            and not in_check
            and beta < MATE_THRESHOLD
            and self._has_pieces(board)
            and evaluate(board) >= beta
        ):
            board.push(chess.Move.null())
            try:
                score = -self._negamax(board, depth - 3, -beta, -beta + 1, ply + 1)
            finally:
                board.pop()
            if score >= beta:
                return beta

        moves = self._ordered_moves(board, tt_move, ply)
        if not moves:
            return -(MATE - ply) if in_check else 0

        self.seen.add(key)
        try:
            best_score = -INFINITY
            best_move = moves[0]
            for index, move in enumerate(moves):
                quiet = not board.is_capture(move) and move.promotion is None
                board.push(move)
                try:
                    if index == 0:
                        score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
                    else:
                        reduced = depth - 1
                        if depth >= 3 and index >= 4 and quiet and not in_check and not board.is_check():
                            reduced -= 1
                        score = -self._negamax(board, reduced, -alpha - 1, -alpha, ply + 1)
                        if alpha < score < beta or (reduced < depth - 1 and score > alpha):
                            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
                finally:
                    board.pop()

                if score > best_score:
                    best_score = score
                    best_move = move
                alpha = max(alpha, score)
                if alpha >= beta:
                    if quiet:
                        self._record_cutoff(move, depth, ply)
                    break
        finally:
            self.seen.discard(key)

        flag = EXACT
        if best_score <= original_alpha:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        self.tt[key] = (depth, flag, self._to_tt(best_score, ply), best_move)
        return best_score

    def _quiesce(self, board, alpha, beta, ply, qdepth):
        """Keep searching captures so we never evaluate mid-exchange."""
        self.nodes += 1
        if not self.nodes & 1023 and time.monotonic() >= self.deadline:
            raise _OutOfTime

        in_check = board.is_check()
        if in_check and qdepth < MAX_QUIESCE_DEPTH:
            moves = self._ordered_moves(board, None, ply)
            if not moves:
                return -(MATE - ply)
            best = -INFINITY
        else:
            stand_pat = evaluate(board)
            if stand_pat >= beta or qdepth >= MAX_QUIESCE_DEPTH:
                return stand_pat
            alpha = max(alpha, stand_pat)
            best = stand_pat
            moves = sorted(board.generate_legal_captures(), key=lambda m: self._capture_rank(board, m), reverse=True)

        for move in moves:
            if not in_check and self._cannot_raise_alpha(board, move, best, alpha):
                continue
            board.push(move)
            try:
                score = -self._quiesce(board, -beta, -alpha, ply + 1, qdepth + 1)
            finally:
                board.pop()
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best

    @staticmethod
    def _cannot_raise_alpha(board, move, stand_pat, alpha):
        """Delta pruning: even winning this piece outright would not help."""
        if move.promotion is not None:
            return False
        victim = board.piece_type_at(move.to_square)
        gain = MATERIAL[victim] if victim is not None else MATERIAL[chess.PAWN]
        return stand_pat + gain + DELTA_MARGIN < alpha

    @staticmethod
    def _has_pieces(board):
        """False in king-and-pawn endings, where passing can be the wrong idea."""
        occupied = board.occupied_co[board.turn]
        return bool((board.knights | board.bishops | board.rooks | board.queens) & occupied)

    @staticmethod
    def _capture_rank(board, move):
        """Most valuable victim first, least valuable attacker as tie-break."""
        victim = board.piece_type_at(move.to_square)
        attacker = board.piece_type_at(move.from_square)
        gain = MATERIAL[victim] if victim is not None else MATERIAL[chess.PAWN]
        return gain * 10 - MATERIAL[attacker]

    def _ordered_moves(self, board, tt_move, ply):
        killers = self.killers[ply] if ply < len(self.killers) else (None, None)
        history = self.history_scores

        def rank(move):
            if move == tt_move:
                return 10_000_000
            if move.promotion == chess.QUEEN:
                return 9_000_000
            if board.is_capture(move):
                return 5_000_000 + self._capture_rank(board, move)
            if move == killers[0]:
                return 4_000_000
            if move == killers[1]:
                return 3_900_000
            return history.get((move.from_square, move.to_square), 0)

        return sorted(board.legal_moves, key=rank, reverse=True)

    def _record_cutoff(self, move, depth, ply):
        if ply < len(self.killers):
            killers = self.killers[ply]
            if move != killers[0]:
                killers[1] = killers[0]
                killers[0] = move
        key = (move.from_square, move.to_square)
        self.history_scores[key] = self.history_scores.get(key, 0) + depth * depth

    @staticmethod
    def _to_tt(score, ply):
        """Mate scores count from the root; store them relative to this node."""
        if score >= MATE_THRESHOLD:
            return score + ply
        if score <= -MATE_THRESHOLD:
            return score - ply
        return score

    @staticmethod
    def _from_tt(score, ply):
        if score >= MATE_THRESHOLD:
            return score - ply
        if score <= -MATE_THRESHOLD:
            return score + ply
        return score
