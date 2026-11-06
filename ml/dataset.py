"""Monta o dataset de lances para o modelo de "chance de errar".

Uma linha = um lance do usuário. Rótulo `y` = o lance foi erro grave (erro ou blunder).

Regra de ouro: as features só podem usar o que se sabe ANTES de o lance ser jogado.
Nada de `cp_loss`, `eval_after`, `best_move`, `severity`, `accuracy` ou `win_drop`: isso seria
vazamento de dados (o modelo aprenderia a "ler a resposta" e pareceria ótimo sem servir para nada).

A única exceção consciente é `time_spent` (quanto tempo você gastou NESTE lance): ele faz parte
da decisão, não do resultado, e responde a uma pergunta útil ("eu erro mais quando jogo rápido?").
Para um modelo estritamente preditivo, remova-o com `--no-behavior` no train.py.

Uso:
    python -m ml.dataset SEU_NICK            # gera ml/data/dataset_SEU_NICK.csv
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path

import chess
import pandas as pd

from analysis import CP_CAP, ensure_schema, winning_chances

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "chesscoach.db"
DATA_DIR = Path(__file__).resolve().parent / "data"

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PHASES = ("opening", "middlegame", "endgame")
TIME_CLASSES = ("bullet", "blitz", "rapid", "daily")

# Colunas que NUNCA podem virar feature (usadas pelo teste anti-vazamento).
LEAKY_COLUMNS = {"cp_loss", "eval_after", "best_uci", "best_san", "severity", "accuracy", "win_drop", "san", "uci"}
META_COLUMNS = ["game_id", "ply", "played_at", "y"]


def parse_time_control(tc: str | None) -> tuple[float | None, float]:
    """'180+2' -> (180, 2). Partidas diárias ('1/86400') -> (None, 0)."""
    if not tc or "/" in tc:
        return None, 0.0
    base, _, inc = tc.partition("+")
    try:
        return float(base), float(inc or 0)
    except ValueError:
        return None, 0.0


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALUES[p] * len(board.pieces(p, color)) for p in VALUES)


def hanging(board: chess.Board, color: chess.Color) -> tuple[int, int]:
    """(quantidade, valor total) das peças de `color` atacadas e sem defensor."""
    count = value = 0
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        if board.is_attacked_by(not color, square) and not board.is_attacked_by(color, square):
            count += 1
            value += VALUES[piece.piece_type]
    return count, value


def attacked_by_lower(board: chess.Board, color: chess.Color) -> int:
    """Peças de `color` atacadas por uma peça adversária de valor menor (ameaça real)."""
    n = 0
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        mine = VALUES[piece.piece_type]
        if any(VALUES[board.piece_at(a).piece_type] < mine for a in board.attackers(not color, square)):
            n += 1
    return n


def board_features(fen: str) -> dict:
    board = chess.Board(fen)
    me = board.turn
    my_hang, my_hang_val = hanging(board, me)
    opp_hang, opp_hang_val = hanging(board, not me)
    my_mat, opp_mat = material(board, me), material(board, not me)
    return {
        "legal_moves": board.legal_moves.count(),
        "in_check": int(board.is_check()),
        "material_diff": my_mat - opp_mat,
        "total_material": my_mat + opp_mat,
        "my_hanging": my_hang,
        "my_hanging_value": my_hang_val,
        "opp_hanging": opp_hang,
        "opp_hanging_value": opp_hang_val,
        "my_attacked_by_lower": attacked_by_lower(board, me),
        "captures_available": sum(1 for m in board.legal_moves if board.is_capture(m)),
    }


def build_dataset(conn: sqlite3.Connection, username: str) -> pd.DataFrame:
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    games = {
        r["id"]: dict(r)
        for r in conn.execute(
            """
            SELECT g.id, g.color, g.time_control, g.time_class, g.my_rating, g.opp_rating, g.played_at
            FROM games g JOIN game_analysis a ON a.game_id = g.id
            WHERE lower(g.username) = lower(?)
            """,
            (username,),
        )
    }
    if not games:
        return pd.DataFrame()

    rows: list[dict] = []
    marks = ",".join("?" * len(games))
    moves = conn.execute(
        f"SELECT * FROM move_analysis WHERE game_id IN ({marks}) ORDER BY game_id, ply", list(games)
    ).fetchall()

    prev_by_game: dict[str, list[sqlite3.Row]] = {}
    for m in moves:
        history = prev_by_game.setdefault(m["game_id"], [])
        if m["is_user"]:
            rows.append(_row_features(m, history, games[m["game_id"]]))
        history.append(m)
    return pd.DataFrame(rows)


def _row_features(m: sqlite3.Row, history: list[sqlite3.Row], game: dict) -> dict:
    sign = 1 if m["color"] == "white" else -1
    eval_me = 0 if m["eval_before"] is None else max(-CP_CAP, min(CP_CAP, sign * m["eval_before"]))
    mate_me = None if m["mate_before"] is None else sign * m["mate_before"]

    base, inc = parse_time_control(game["time_control"])
    my_prev = next((h for h in reversed(history) if h["is_user"]), None)
    opp_prev = history[-1] if history and not history[-1]["is_user"] else None

    # Relógio no INÍCIO do lance = seu relógio depois do seu lance anterior (ou o tempo inicial).
    clock_before = my_prev["clock_seconds"] if my_prev and my_prev["clock_seconds"] is not None else base
    clock_after = m["clock_seconds"]
    time_spent = None
    if clock_before is not None and clock_after is not None:
        time_spent = max(0.0, clock_before + inc - clock_after)

    opp_last_capture = 0
    if opp_prev is not None:
        prev_board = chess.Board(opp_prev["fen_before"])
        opp_last_capture = int(prev_board.is_capture(chess.Move.from_uci(opp_prev["uci"])))

    rating_diff = (
        game["opp_rating"] - game["my_rating"] if game["opp_rating"] and game["my_rating"] else 0
    )

    row = {
        "game_id": m["game_id"],
        "ply": m["ply"],
        "played_at": game["played_at"],
        "y": int(m["severity"] in ("mistake", "blunder")),
        # --- avaliação da posição (antes do lance)
        "eval_me": eval_me,
        "abs_eval": abs(eval_me),
        "win_chance_me": winning_chances(eval_me),
        "i_have_mate": int(mate_me is not None and mate_me > 0),
        "i_am_mated": int(mate_me is not None and mate_me < 0),
        # --- contexto da partida
        "move_number": m["move_number"],
        "is_white": int(m["color"] == "white"),
        "rating_diff": rating_diff,
        "opp_last_capture": opp_last_capture,
        # --- relógio
        "clock_before": clock_before if clock_before is not None else math.nan,
        "clock_frac": (clock_before / base) if (clock_before is not None and base) else math.nan,
        "time_pressure": int(m["time_pressure"]),
        "time_spent": time_spent if time_spent is not None else math.nan,
        "time_spent_frac": (time_spent / base) if (time_spent is not None and base) else math.nan,
    }
    for phase in PHASES:
        row[f"phase_{phase}"] = int(m["phase"] == phase)
    for tc in TIME_CLASSES:
        row[f"tc_{tc}"] = int(game["time_class"] == tc)
    row.update(board_features(m["fen_before"]))
    return row


def feature_columns(df: pd.DataFrame, behavior: bool = True) -> list[str]:
    cols = [c for c in df.columns if c not in META_COLUMNS]
    if not behavior:
        cols = [c for c in cols if c not in ("time_spent", "time_spent_frac")]
    return cols


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o dataset de lances de um jogador.")
    parser.add_argument("username")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args(argv)

    with sqlite3.connect(args.db) as conn:
        df = build_dataset(conn, args.username)
    if df.empty:
        print("Nenhuma partida analisada desse jogador. Rode o analyze_all.py antes.")
        return 1
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"dataset_{args.username.lower()}.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} lances de {df['game_id'].nunique()} partidas, {df['y'].mean():.1%} erros graves -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
