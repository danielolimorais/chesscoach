"""Orquestra: buscar PGN -> parsear -> gravar no banco."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .clients import chesscom, lichess
from .db import insert_game
from .pgn_parser import parse_pgn_text

PLATFORMS = ("chesscom", "lichess")


@dataclass
class ImportResult:
    parsed: int = 0      # partidas válidas lidas
    inserted: int = 0    # partidas novas gravadas
    duplicates: int = 0  # já estavam no banco
    skipped: int = 0     # variantes, em andamento ou sem o usuário


def import_pgn_text(
    conn: sqlite3.Connection, pgn_text: str, platform: str, username: str
) -> ImportResult:
    games, skipped = parse_pgn_text(pgn_text, username, platform)
    result = ImportResult(parsed=len(games), skipped=skipped)
    with conn:  # uma transação para o lote todo
        for game in games:
            if insert_game(conn, game):
                result.inserted += 1
            else:
                result.duplicates += 1
    return result


def import_from_platform(
    conn: sqlite3.Connection, platform: str, username: str, max_games: int = 100
) -> ImportResult:
    if platform == "chesscom":
        pgn_text = chesscom.fetch_pgns(username, max_games)
    elif platform == "lichess":
        pgn_text = lichess.fetch_pgns(username, max_games)
    else:
        raise ValueError(f"Plataforma desconhecida: {platform!r} (use {PLATFORMS})")
    return import_pgn_text(conn, pgn_text, platform, username)
