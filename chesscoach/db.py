"""Persistência em SQLite (arquivo local, sem instalar nada).

O esquema usa SQL padrão, então migrar para Postgres depois é direto.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .pgn_parser import ParsedGame

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id           TEXT PRIMARY KEY,          -- "chesscom:123" / "lichess:abcd1234"
    platform     TEXT NOT NULL,
    username     TEXT NOT NULL,
    url          TEXT,
    played_at    TEXT,
    color        TEXT NOT NULL CHECK (color IN ('white', 'black')),
    result       TEXT NOT NULL CHECK (result IN ('win', 'loss', 'draw')),
    termination  TEXT,
    time_control TEXT,
    time_class   TEXT,
    opening_eco  TEXT,
    opening_name TEXT,
    my_rating    INTEGER,
    opp_rating   INTEGER,
    opp_name     TEXT,
    num_plies    INTEGER NOT NULL,
    pgn          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moves (
    game_id       TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply           INTEGER NOT NULL,
    san           TEXT NOT NULL,
    uci           TEXT NOT NULL,
    fen_before    TEXT NOT NULL,
    clock_seconds REAL,
    PRIMARY KEY (game_id, ply)
);

CREATE INDEX IF NOT EXISTS idx_games_user ON games (platform, username, played_at);
"""


def connect(path: str | Path = "chesscoach.db") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def insert_game(conn: sqlite3.Connection, game: ParsedGame) -> bool:
    """Insere a partida (e seus lances). Retorna False se ela já existia."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO games (
            id, platform, username, url, played_at, color, result, termination,
            time_control, time_class, opening_eco, opening_name,
            my_rating, opp_rating, opp_name, num_plies, pgn
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game.id, game.platform, game.username, game.url, game.played_at,
            game.color, game.result, game.termination, game.time_control,
            game.time_class, game.opening_eco, game.opening_name,
            game.my_rating, game.opp_rating, game.opp_name, game.num_plies, game.pgn,
        ),
    )
    if cur.rowcount == 0:
        return False
    conn.executemany(
        "INSERT INTO moves (game_id, ply, san, uci, fen_before, clock_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(game.id, m.ply, m.san, m.uci, m.fen_before, m.clock_seconds) for m in game.moves],
    )
    return True
