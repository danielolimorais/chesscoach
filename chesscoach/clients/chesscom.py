"""Cliente da API pública do Chess.com (https://www.chess.com/news/view/published-data-api)."""

from __future__ import annotations

import requests

from . import ClientError

BASE_URL = "https://api.chess.com/pub"
# O Chess.com pede um User-Agent identificável; troque pelo seu contato se publicar o app.
HEADERS = {"User-Agent": "ChessCoach/0.1 (projeto)"}


def _get_json(session: requests.Session, url: str) -> dict:
    resp = session.get(url, headers=HEADERS, timeout=(6, 20))  # (conexão, leitura)
    print(f"[chess.com] {url} -> HTTP {resp.status_code}", flush=True)
    if resp.status_code == 404:
        raise ClientError("Usuário não encontrado no Chess.com.")
    if resp.status_code == 429:
        raise ClientError("Limite de requisições do Chess.com atingido. Tente de novo em instantes.")
    if resp.status_code != 200:
        raise ClientError(f"Chess.com respondeu HTTP {resp.status_code} para {url}")
    return resp.json()


def fetch_pgns(
    username: str, max_games: int = 100, session: requests.Session | None = None
) -> str:
    """Baixa as últimas `max_games` partidas de xadrez padrão, das mais novas às mais antigas.

    Retorna um único texto PGN com todas as partidas.
    """
    session = session or requests.Session()
    user = username.strip().lower()

    archives = _get_json(session, f"{BASE_URL}/player/{user}/games/archives")["archives"]

    pgns: list[str] = []
    for archive_url in reversed(archives):  # meses mais recentes primeiro
        month_games = _get_json(session, archive_url).get("games", [])
        for g in reversed(month_games):  # dentro do mês, as mais novas primeiro
            if g.get("rules") != "chess" or not g.get("pgn"):
                continue  # ignora variantes (chess960 etc.)
            pgns.append(g["pgn"])
            if len(pgns) >= max_games:
                return "\n\n".join(pgns)
    return "\n\n".join(pgns)
