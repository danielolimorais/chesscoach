"""Cliente da API do Lichess (https://lichess.org/api#tag/Games/operation/apiGamesUser)."""

from __future__ import annotations

import os

import requests

from . import ClientError

BASE_URL = "https://lichess.org/api/games/user"


def fetch_pgns(
    username: str,
    max_games: int = 100,
    token: str | None = None,
    session: requests.Session | None = None,
) -> str:
    """Baixa as últimas `max_games` partidas (mais novas primeiro) em formato PGN.

    O token é opcional (variável de ambiente LICHESS_TOKEN) e só aumenta o limite de requisições.
    """
    session = session or requests.Session()
    token = token or os.environ.get("LICHESS_TOKEN")

    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessCoach/0.1 (projeto de portfolio)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "max": max_games,
        "clocks": "true",    # inclui [%clk ...] em cada lance
        "opening": "true",   # inclui o nome da abertura
        "perfType": "ultraBullet,bullet,blitz,rapid,classical,correspondence",  # sem variantes
    }

    resp = session.get(
        f"{BASE_URL}/{username.strip()}", headers=headers, params=params, timeout=60
    )
    if resp.status_code == 404:
        raise ClientError("Usuário não encontrado no Lichess.")
    if resp.status_code == 429:
        raise ClientError("Limite de requisições do Lichess atingido. Aguarde cerca de 1 minuto.")
    if resp.status_code != 200:
        raise ClientError(f"Lichess respondeu HTTP {resp.status_code}.")

    resp.encoding = "utf-8"
    return resp.text
