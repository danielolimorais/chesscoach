"""Análise lance a lance de uma partida.

Para cada lance calcula: perda em centipeões, queda nas chances de vitória,
precisão (fórmula usada pelo Lichess), gravidade, fase da partida e pressão de tempo.
O resultado fica salvo nas tabelas `move_analysis` e `game_analysis`, então cada
partida só passa pelo Stockfish uma vez.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

import chess

from evaluator import DEFAULT_DEPTH, MATE_CP, white_cp

CP_CAP = 1000  # limita a avaliação a ±10 peões para o cálculo de perdas

# Queda nas "chances de vitória" (escala de -1 a 1), os mesmos limites do Lichess.
INACCURACY_DROP = 0.10
MISTAKE_DROP = 0.20
BLUNDER_DROP = 0.30

SCHEMA = """
CREATE TABLE IF NOT EXISTS game_analysis (
    game_id      TEXT PRIMARY KEY,
    depth        INTEGER NOT NULL,
    analyzed_at  TEXT NOT NULL,
    user_moves   INTEGER NOT NULL,
    accuracy     REAL,
    acpl         REAL,
    blunders     INTEGER NOT NULL,
    mistakes     INTEGER NOT NULL,
    inaccuracies INTEGER NOT NULL,
    max_eval     INTEGER,  -- melhor avaliação que o usuário teve na partida (ponto de vista dele)
    min_eval     INTEGER   -- pior avaliação que o usuário teve na partida
);

CREATE TABLE IF NOT EXISTS move_analysis (
    game_id       TEXT NOT NULL,
    ply           INTEGER NOT NULL,
    move_number   INTEGER NOT NULL,
    color         TEXT NOT NULL,
    is_user       INTEGER NOT NULL,
    san           TEXT NOT NULL,
    uci           TEXT NOT NULL,
    best_san      TEXT,
    best_uci      TEXT,
    fen_before    TEXT NOT NULL,
    eval_before   INTEGER,  -- ponto de vista das brancas, limitado a ±CP_CAP
    eval_after    INTEGER,
    mate_before   INTEGER,  -- mate em N (positivo = brancas dão mate)
    cp_loss       INTEGER NOT NULL,
    win_drop      REAL NOT NULL,  -- queda na % de vitória de quem jogou
    accuracy      REAL NOT NULL,
    severity      TEXT NOT NULL,  -- best | good | inaccuracy | mistake | blunder
    phase         TEXT NOT NULL,  -- opening | middlegame | endgame
    clock_seconds REAL,
    time_pressure INTEGER NOT NULL,
    PRIMARY KEY (game_id, ply)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


# ---------------------------------------------------------------- matemática

def clamp_cp(cp: int | None) -> int | None:
    return None if cp is None else max(-CP_CAP, min(CP_CAP, cp))


def winning_chances(cp: int) -> float:
    """Converte centipeões em chances de vitória na escala de -1 a 1 (curva do Lichess)."""
    return 2 / (1 + math.exp(-0.00368208 * cp)) - 1


def win_percent(cp: int) -> float:
    return 50 * (1 + winning_chances(cp))


def move_accuracy(win_before: float, win_after: float) -> float:
    """Precisão do lance (0 a 100) a partir da queda na % de vitória (fórmula do Lichess)."""
    drop = max(0.0, win_before - win_after)
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * drop) - 3.166924740191411
    return max(0.0, min(100.0, raw + 1))


def classify(drop: float) -> str:
    if drop >= BLUNDER_DROP:
        return "blunder"
    if drop >= MISTAKE_DROP:
        return "mistake"
    if drop >= INACCURACY_DROP:
        return "inaccuracy"
    return "good"


_PIECE_VALUES = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def game_phase(board: chess.Board, move_number: int) -> str:
    """Fase pela quantidade de material (sem peões e reis) e pelo número do lance."""
    material = sum(
        value * len(board.pieces(piece, color))
        for piece, value in _PIECE_VALUES.items()
        for color in (chess.WHITE, chess.BLACK)
    )
    no_queens = not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK)
    if material <= 20 or (no_queens and material <= 26):
        return "endgame"
    if move_number <= 12:
        return "opening"
    return "middlegame"


def pressure_threshold(time_control: str | None) -> float | None:
    """Segundos abaixo dos quais o jogador está 'sem tempo'. None para partidas diárias."""
    if not time_control or "/" in time_control:
        return None
    try:
        base = int(time_control.split("+")[0])
    except ValueError:
        return None
    return max(10.0, 0.10 * base)


# ---------------------------------------------------------------- análise

def _eval_text(cp: int | None, mate: int | None) -> str:
    if mate:
        return f"M{mate}" if mate > 0 else f"-M{-mate}"
    if cp is None:
        return "?"
    if abs(cp) >= MATE_CP:
        return "#"
    return f"{cp / 100:+.1f}"


def _row_to_move(r: sqlite3.Row) -> dict:
    return {
        "ply": r["ply"],
        "move_number": r["move_number"],
        "color": r["color"],
        "is_user": bool(r["is_user"]),
        "played_move": r["san"],
        "played_uci": r["uci"],
        "best_move": r["best_san"],
        "best_uci": r["best_uci"],
        "fen_before": r["fen_before"],
        "eval_before": r["eval_before"],
        "eval_after": r["eval_after"],
        "eval_text": _eval_text(r["eval_before"], r["mate_before"]),
        "cp_loss": r["cp_loss"],
        "win_drop": round(r["win_drop"], 1),
        "accuracy": round(r["accuracy"], 1),
        "severity": r["severity"],
        "phase": r["phase"],
        "clock_seconds": r["clock_seconds"],
        "time_pressure": bool(r["time_pressure"]),
    }


def _game_meta(conn: sqlite3.Connection, game_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, username, color, result, played_at, opp_name, opp_rating, my_rating, "
        "time_control, time_class, opening_name, url, termination FROM games WHERE id = ?",
        (game_id,),
    ).fetchone()
    if row is None:
        raise KeyError(game_id)
    return row


def is_analyzed(conn: sqlite3.Connection, game_id: str) -> bool:
    ensure_schema(conn)
    return conn.execute("SELECT 1 FROM game_analysis WHERE game_id = ?", (game_id,)).fetchone() is not None


def analyze_game(evaluator, game_id: str, depth: int = DEFAULT_DEPTH, force: bool = False) -> dict:
    """Analisa a partida (ou lê do banco, se já foi analisada) e devolve lances + resumo."""
    conn = sqlite3.connect(evaluator.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        meta = _game_meta(conn, game_id)
        if force or not is_analyzed(conn, game_id):
            _run_analysis(conn, evaluator, meta, depth)
        return load_analysis(conn, game_id)
    finally:
        conn.close()


def _run_analysis(conn: sqlite3.Connection, evaluator, meta: sqlite3.Row, depth: int) -> None:
    moves = conn.execute(
        "SELECT ply, san, uci, fen_before, clock_seconds FROM moves WHERE game_id = ? ORDER BY ply",
        (meta["id"],),
    ).fetchall()
    if not moves:
        raise KeyError(meta["id"])

    last_board = chess.Board(moves[-1]["fen_before"])
    last_board.push_uci(moves[-1]["uci"])
    fens = [m["fen_before"] for m in moves] + [last_board.fen()]
    evals = [evaluator.get_evaluation(fen, depth) for fen in fens]

    user_color = meta["color"]
    threshold = pressure_threshold(meta["time_control"])
    rows, user_rows = [], []

    for i, m in enumerate(moves):
        board = chess.Board(m["fen_before"])
        mover = "white" if board.turn == chess.WHITE else "black"
        sign = 1 if mover == "white" else -1
        move_number = board.fullmove_number

        before_w, after_w = white_cp(evals[i]), white_cp(evals[i + 1])
        before = clamp_cp(None if before_w is None else sign * before_w)
        after = clamp_cp(None if after_w is None else sign * after_w)

        best_uci = evals[i]["best_move"]
        best_san = None
        if best_uci:
            try:
                best_san = board.san(chess.Move.from_uci(best_uci))
            except ValueError:
                best_san = best_uci

        if before is None or after is None:
            cp_loss, drop, accuracy, severity = 0, 0.0, 100.0, "good"
        else:
            cp_loss = max(0, before - after)
            chances_drop = max(0.0, winning_chances(before) - winning_chances(after))
            win_b, win_a = win_percent(before), win_percent(after)
            drop = max(0.0, win_b - win_a)
            accuracy = move_accuracy(win_b, win_a)
            severity = classify(chances_drop)
        if best_uci and m["uci"] == best_uci:
            severity, cp_loss = "best", 0

        clock = m["clock_seconds"]
        pressure = int(threshold is not None and clock is not None and clock < threshold)
        row = (
            meta["id"], m["ply"], move_number, mover, int(mover == user_color), m["san"], m["uci"],
            best_san, best_uci, m["fen_before"],
            clamp_cp(before_w), clamp_cp(after_w), evals[i].get("mate_in"),
            cp_loss, drop, accuracy, severity, game_phase(board, move_number), clock, pressure,
        )
        rows.append(row)
        if mover == user_color:
            user_rows.append((cp_loss, accuracy, severity, before))

    n = len(user_rows)
    user_evals = [b for *_, b in user_rows if b is not None]
    summary = (
        meta["id"], DEFAULT_DEPTH if depth is None else depth,
        datetime.now(timezone.utc).isoformat(timespec="seconds"), n,
        round(sum(a for _, a, _, _ in user_rows) / n, 1) if n else None,
        round(sum(c for c, _, _, _ in user_rows) / n, 1) if n else None,
        sum(s == "blunder" for _, _, s, _ in user_rows),
        sum(s == "mistake" for _, _, s, _ in user_rows),
        sum(s == "inaccuracy" for _, _, s, _ in user_rows),
        max(user_evals) if user_evals else None,
        min(user_evals) if user_evals else None,
    )

    with conn:
        conn.execute("DELETE FROM move_analysis WHERE game_id = ?", (meta["id"],))
        conn.executemany(
            "INSERT INTO move_analysis VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
        conn.execute("INSERT OR REPLACE INTO game_analysis VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", summary)


def load_analysis(conn: sqlite3.Connection, game_id: str) -> dict:
    conn.row_factory = sqlite3.Row
    meta = _game_meta(conn, game_id)
    moves = [
        _row_to_move(r)
        for r in conn.execute("SELECT * FROM move_analysis WHERE game_id = ? ORDER BY ply", (game_id,))
    ]
    s = conn.execute("SELECT * FROM game_analysis WHERE game_id = ?", (game_id,)).fetchone()
    return {
        "game": dict(meta),
        "summary": {
            "accuracy": s["accuracy"],
            "acpl": s["acpl"],
            "blunders": s["blunders"],
            "mistakes": s["mistakes"],
            "inaccuracies": s["inaccuracies"],
            "user_moves": s["user_moves"],
        },
        "moves": moves,
    }
