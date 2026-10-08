"""API do ChessCoach.

Rodar (na pasta do projeto, com o ambiente virtual ativo):
    uvicorn api:app --reload

Fluxo usado pelo front-end:
    1. GET  /api/player/{nick}/profile   -> dados e ratings do Chess.com
    2. POST /api/player/{nick}/sync      -> baixa as últimas partidas e inicia a análise
    3. GET  /api/player/{nick}/job       -> progresso da análise (consultado a cada ~2 s)
    4. GET  /api/player/{nick}/report    -> relatório com as estatísticas
    5. GET  /api/game/{id}/analysis      -> lances de uma partida, com avaliação
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from analysis import analyze_game, ensure_schema
from chesscoach import db
from chesscoach.clients import ClientError, chesscom
from chesscoach.importer import import_pgn_text
from evaluator import DEFAULT_DB, StockfishEvaluator
from jobs import JobManager
from report import build_report

DB_PATH = str(DEFAULT_DB)
CHESSCOM_API = "https://api.chess.com/pub"

_evaluator: StockfishEvaluator | None = None
_evaluator_error: str | None = None
_evaluator_lock = threading.Lock()


def get_evaluator() -> StockfishEvaluator:
    """Abre o Stockfish na primeira vez que for necessário (e reaproveita depois)."""
    global _evaluator, _evaluator_error
    with _evaluator_lock:
        if _evaluator is None:
            try:
                _evaluator = StockfishEvaluator(db_path=DB_PATH)
                _evaluator_error = None
            except Exception as exc:  # Stockfish ausente, por exemplo
                _evaluator_error = str(exc)
                raise HTTPException(status_code=503, detail=f"Stockfish indisponível: {exc}") from exc
        return _evaluator


jobs = JobManager(get_evaluator, DB_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with db.connect(DB_PATH) as conn:  # garante que as tabelas existam
        ensure_schema(conn)
    yield
    if _evaluator is not None:
        _evaluator.close()


app = FastAPI(title="ChessCoach API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _chesscom_json(url: str) -> dict:
    start = time.perf_counter()
    try:
        # (conexão, leitura): falha rápido em vez de deixar o front-end esperando.
        resp = requests.get(url, headers=chesscom.HEADERS, timeout=(6, 15))
    except requests.RequestException as exc:
        print(f"[chess.com] {url} -> falhou após {time.perf_counter() - start:.1f}s: {exc}", flush=True)
        raise HTTPException(status_code=502, detail=f"Não foi possível acessar o Chess.com ({type(exc).__name__}).") from exc
    print(f"[chess.com] {url} -> HTTP {resp.status_code} em {time.perf_counter() - start:.1f}s", flush=True)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Jogador não encontrado no Chess.com.")
    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="O Chess.com limitou as requisições. Tente em instantes.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"O Chess.com respondeu HTTP {resp.status_code}.")
    return resp.json()


@app.get("/api/health")
def health():
    return {"ok": True, "stockfish": _evaluator is not None, "stockfish_error": _evaluator_error}


@app.get("/api/player/{username}/profile")
def player_profile(username: str):
    user = username.strip().lower()
    profile = _chesscom_json(f"{CHESSCOM_API}/player/{user}")
    stats = _chesscom_json(f"{CHESSCOM_API}/player/{user}/stats")

    ratings = {}
    for key, label in (("chess_rapid", "rapid"), ("chess_blitz", "blitz"), ("chess_bullet", "bullet")):
        if key in stats:
            record = stats[key].get("record", {})
            ratings[label] = {
                "rating": stats[key].get("last", {}).get("rating"),
                "best": stats[key].get("best", {}).get("rating"),
                "wins": record.get("win", 0),
                "losses": record.get("loss", 0),
                "draws": record.get("draw", 0),
            }

    url = profile.get("url") or ""
    display = url.rstrip("/").rsplit("/", 1)[-1] if url else profile.get("username", username)
    return {
        "username": display,
        "name": profile.get("name"),
        "title": profile.get("title"),
        "avatar": profile.get("avatar"),
        "url": url,
        "ratings": ratings,
    }


def _recent_game_ids(username: str, limit: int) -> list[str]:
    with _conn() as conn:
        return [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM games WHERE lower(username) = lower(?) ORDER BY played_at DESC LIMIT ?",
                (username, limit),
            )
        ]


@app.post("/api/player/{username}/sync")
def sync_player(username: str, limit: int = Query(30, ge=5, le=100)):
    """Baixa as últimas `limit` partidas do Chess.com e começa a analisá-las em segundo plano."""
    username = username.strip()
    start = time.perf_counter()
    try:
        pgn_text = chesscom.fetch_pgns(username, max_games=limit)
    except ClientError as exc:
        status = 404 if "não encontrado" in str(exc) else 429 if "Limite" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Não foi possível acessar o Chess.com.") from exc

    with db.connect(DB_PATH) as conn:
        imported = import_pgn_text(conn, pgn_text, "chesscom", username)
    print(
        f"[sync] {username}: {imported.parsed} partidas lidas, {imported.inserted} novas "
        f"({time.perf_counter() - start:.1f}s)",
        flush=True,
    )

    game_ids = _recent_game_ids(username, limit)
    if not game_ids:
        raise HTTPException(status_code=404, detail="Nenhuma partida de xadrez padrão encontrada para esse jogador.")

    get_evaluator()  # falha cedo (503) se o Stockfish não estiver disponível
    job = jobs.start(username, game_ids)
    return {"imported": imported.inserted, "found": imported.parsed, "total": len(game_ids), "job": job.to_dict()}


@app.get("/api/player/{username}/job")
def job_status(username: str):
    job = jobs.get(username)
    if job is None:
        return {"status": "idle", "done": 0, "total": 0}
    return job.to_dict()


@app.get("/api/player/{username}/report")
def player_report(username: str, limit: int = Query(30, ge=5, le=100)):
    with _conn() as conn:
        report = build_report(conn, username, limit)
    if report["total_games"] == 0:
        raise HTTPException(status_code=404, detail="Nenhuma partida desse jogador no banco. Rode a sincronização.")
    return report


@app.get("/api/game/{game_id}/analysis")
def game_analysis(game_id: str):
    try:
        return analyze_game(get_evaluator(), game_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Partida não encontrada no banco.") from exc
