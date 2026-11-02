"""Static evaluation: how good a position looks without searching further.

Scores are centipawns from the point of view of the side to move.
"""

import chess

MATERIAL = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Piece-square tables, written as you would look at the board from White's
# side: the first row is rank 8, the last row is rank 1.
_PAWN = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]
_PAWN_END = [
     0,  0,  0,  0,  0,  0,  0,  0,
    80, 80, 80, 80, 80, 80, 80, 80,
    50, 50, 50, 50, 50, 50, 50, 50,
    30, 30, 30, 30, 30, 30, 30, 30,
    20, 20, 20, 20, 20, 20, 20, 20,
    10, 10, 10, 10, 10, 10, 10, 10,
    10, 10, 10, 10, 10, 10, 10, 10,
     0,  0,  0,  0,  0,  0,  0,  0,
]
_KNIGHT = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
_BISHOP = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
_ROOK = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]
_QUEEN = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
_KING = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]
_KING_END = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]

_MIDDLEGAME = {
    chess.PAWN: _PAWN, chess.KNIGHT: _KNIGHT, chess.BISHOP: _BISHOP,
    chess.ROOK: _ROOK, chess.QUEEN: _QUEEN, chess.KING: _KING,
}
_ENDGAME = {**_MIDDLEGAME, chess.PAWN: _PAWN_END, chess.KING: _KING_END}

PHASE_WEIGHT = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}
MAX_PHASE = 24

PASSED_BONUS = [0, 5, 10, 20, 40, 70, 120, 0]  # by ranks advanced
DOUBLED_PENALTY = 12
ISOLATED_PENALTY = 15
BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10
PAWN_SHIELD_BONUS = 10
TEMPO_BONUS = 10


def _table(source, piece_type, color):
    """Material plus position, indexed by square, for one piece and colour."""
    values = [0] * 64
    for square in chess.SQUARES:
        index = square ^ 56 if color == chess.WHITE else square
        values[square] = MATERIAL[piece_type] + source[piece_type][index]
    return values


_MG = {c: {p: _table(_MIDDLEGAME, p, c) for p in chess.PIECE_TYPES} for c in chess.COLORS}
_EG = {c: {p: _table(_ENDGAME, p, c) for p in chess.PIECE_TYPES} for c in chess.COLORS}

_FILES = [int(chess.BB_FILES[f]) for f in range(8)]
_ADJACENT_FILES = [
    (_FILES[f - 1] if f > 0 else 0) | (_FILES[f + 1] if f < 7 else 0) for f in range(8)
]


def _passed_mask(square, color):
    """Squares that must hold no enemy pawn for a pawn on `square` to be passed."""
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    ranks = range(rank_index + 1, 8) if color == chess.WHITE else range(0, rank_index)
    span = 0
    for rank in ranks:
        span |= int(chess.BB_RANKS[rank])
    return span & (_FILES[file_index] | _ADJACENT_FILES[file_index])


_PASSED = {c: [_passed_mask(s, c) for s in chess.SQUARES] for c in chess.COLORS}


def _pawn_structure(own_pawns, enemy_pawns, color):
    """Score for one side's pawns, split into (middlegame, endgame)."""
    mg = eg = 0
    for file_index in range(8):
        on_file = own_pawns & _FILES[file_index]
        if not on_file:
            continue
        count = chess.popcount(on_file)
        if count > 1:
            mg -= DOUBLED_PENALTY * (count - 1)
            eg -= DOUBLED_PENALTY * (count - 1)
        if not own_pawns & _ADJACENT_FILES[file_index]:
            mg -= ISOLATED_PENALTY * count
            eg -= ISOLATED_PENALTY * count
    for square in chess.scan_forward(own_pawns):
        if not enemy_pawns & _PASSED[color][square]:
            rank = chess.square_rank(square)
            advanced = rank if color == chess.WHITE else 7 - rank
            mg += PASSED_BONUS[advanced] // 2
            eg += PASSED_BONUS[advanced]
    return mg, eg


def _king_shield(board, color, own_pawns):
    """Count own pawns on the three squares directly in front of the king."""
    king = board.king(color)
    if king is None:
        return 0
    rank = chess.square_rank(king) + (1 if color == chess.WHITE else -1)
    if not 0 <= rank <= 7:
        return 0
    file_index = chess.square_file(king)
    zone = int(chess.BB_RANKS[rank]) & (_FILES[file_index] | _ADJACENT_FILES[file_index])
    return chess.popcount(own_pawns & zone) * PAWN_SHIELD_BONUS


def evaluate(board):
    if chess.popcount(board.occupied) <= 4 and board.is_insufficient_material():
        return 0

    mg = eg = phase = 0
    white_pawns = board.pawns & board.occupied_co[chess.WHITE]
    black_pawns = board.pawns & board.occupied_co[chess.BLACK]
    all_pawns = board.pawns

    for color, sign in ((chess.WHITE, 1), (chess.BLACK, -1)):
        occupied = board.occupied_co[color]
        mg_table = _MG[color]
        eg_table = _EG[color]
        own_pawns = white_pawns if color == chess.WHITE else black_pawns
        enemy_pawns = black_pawns if color == chess.WHITE else white_pawns

        side_mg = side_eg = 0
        for piece_type, mask in (
            (chess.PAWN, board.pawns),
            (chess.KNIGHT, board.knights),
            (chess.BISHOP, board.bishops),
            (chess.ROOK, board.rooks),
            (chess.QUEEN, board.queens),
            (chess.KING, board.kings),
        ):
            pieces = mask & occupied
            if not pieces:
                continue
            mg_values = mg_table[piece_type]
            eg_values = eg_table[piece_type]
            for square in chess.scan_forward(pieces):
                side_mg += mg_values[square]
                side_eg += eg_values[square]
            if piece_type in PHASE_WEIGHT:
                phase += PHASE_WEIGHT[piece_type] * chess.popcount(pieces)

        if chess.popcount(board.bishops & occupied) >= 2:
            side_mg += BISHOP_PAIR_BONUS
            side_eg += BISHOP_PAIR_BONUS

        for square in chess.scan_forward(board.rooks & occupied):
            file_mask = _FILES[chess.square_file(square)]
            if not all_pawns & file_mask:
                side_mg += ROOK_OPEN_FILE_BONUS
            elif not own_pawns & file_mask:
                side_mg += ROOK_SEMI_OPEN_FILE_BONUS

        pawn_mg, pawn_eg = _pawn_structure(own_pawns, enemy_pawns, color)
        side_mg += pawn_mg + _king_shield(board, color, own_pawns)
        side_eg += pawn_eg

        mg += sign * side_mg
        eg += sign * side_eg

    phase = min(phase, MAX_PHASE)
    score = (mg * phase + eg * (MAX_PHASE - phase)) // MAX_PHASE
    return (score if board.turn == chess.WHITE else -score) + TEMPO_BONUS
