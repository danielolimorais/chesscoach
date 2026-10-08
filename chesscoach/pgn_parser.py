"""Converte texto PGN (Chess.com ou Lichess) em objetos estruturados.

O parser é independente de rede: recebe texto e devolve partidas já vistas
pela ótica do jogador (cor, resultado, rating próprio/do oponente, etc.).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field

import chess
import chess.pgn

STANDARD_VARIANTS = {"", "standard", "from position"}


@dataclass
class ParsedMove:
    ply: int
    san: str
    uci: str
    fen_before: str
    clock_seconds: float | None


@dataclass
class ParsedGame:
    id: str  # "<plataforma>:<id da partida>"
    platform: str
    username: str
    url: str | None
    played_at: str | None  # ISO 8601 (UTC) ou só a data
    color: str  # "white" | "black"
    result: str  # "win" | "loss" | "draw"
    termination: str | None
    time_control: str | None
    time_class: str | None  # bullet | blitz | rapid | classical | daily
    opening_eco: str | None
    opening_name: str | None
    my_rating: int | None
    opp_rating: int | None
    opp_name: str | None
    num_plies: int
    pgn: str
    moves: list[ParsedMove] = field(default_factory=list)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in ("", "?", "??", "-", "????.??.??") else value


def _to_int(value: str | None) -> int | None:
    value = _clean(value)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def time_class_from_control(time_control: str | None) -> str | None:
    """Classifica o ritmo como o Lichess: base + 40 * incremento (em segundos)."""
    tc = _clean(time_control)
    if tc is None:
        return None
    if "/" in tc:  # partidas por correspondência/diárias, ex.: "1/86400"
        return "daily"
    try:
        base, _, inc = tc.partition("+")
        total = int(base) + 40 * int(inc or 0)
    except ValueError:
        return None
    if total < 180:
        return "bullet"
    if total < 480:
        return "blitz"
    if total < 1500:
        return "rapid"
    return "classical"


def _opening_from_url(url: str | None) -> str | None:
    """O Chess.com não manda o nome da abertura, só o slug do ECOUrl."""
    url = _clean(url)
    if not url:
        return None
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    words = []
    for part in slug.split("-"):
        if re.match(r"^\d+\.", part):  # chegou na sequência de lances
            break
        words.append(part)
    return " ".join(words) or None


def _played_at(headers: chess.pgn.Headers) -> str | None:
    date = _clean(headers.get("UTCDate")) or _clean(headers.get("Date"))
    if not date:
        return None
    date = date.replace(".", "-")
    time = _clean(headers.get("UTCTime")) or _clean(headers.get("StartTime"))
    return f"{date}T{time}" if time else date


def _raw_game_id(headers: chess.pgn.Headers, pgn_text: str) -> str:
    # Chess.com: [Link ".../game/live/123"]; Lichess: [Site "https://lichess.org/abcd1234"]
    for key in ("Link", "Site"):
        value = _clean(headers.get(key))
        if value and value.startswith("http"):
            return value.rstrip("/").rsplit("/", 1)[-1]
    return hashlib.sha1(pgn_text.encode("utf-8")).hexdigest()[:16]


def _game_url(headers: chess.pgn.Headers) -> str | None:
    for key in ("Link", "Site"):
        value = _clean(headers.get(key))
        if value and value.startswith("http"):
            return value
    return None


def _result_for_player(result_header: str, color: str) -> str | None:
    if result_header == "1/2-1/2":
        return "draw"
    if result_header == "1-0":
        return "win" if color == "white" else "loss"
    if result_header == "0-1":
        return "win" if color == "black" else "loss"
    return None  # "*" = partida em andamento / sem resultado


def parse_pgn_text(
    pgn_text: str, username: str, platform: str
) -> tuple[list[ParsedGame], int]:
    """Lê um texto com uma ou várias partidas.

    Retorna (partidas_validas, qtd_ignoradas). São ignoradas: variantes,
    partidas em andamento e partidas em que o usuário não jogou.
    """
    stream = io.StringIO(pgn_text)
    games: list[ParsedGame] = []
    skipped = 0
    wanted = username.strip().lower()

    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        h = game.headers

        variant = (h.get("Variant") or "").strip().lower()
        if variant not in STANDARD_VARIANTS:
            skipped += 1
            continue

        white = (h.get("White") or "").strip()
        black = (h.get("Black") or "").strip()
        if white.lower() == wanted:
            color = "white"
        elif black.lower() == wanted:
            color = "black"
        else:
            skipped += 1
            continue

        result = _result_for_player(h.get("Result", "*"), color)
        if result is None:
            skipped += 1
            continue

        board = game.board()
        moves: list[ParsedMove] = []
        for ply, node in enumerate(game.mainline(), start=1):
            move = node.move
            moves.append(
                ParsedMove(
                    ply=ply,
                    san=board.san(move),
                    uci=move.uci(),
                    fen_before=board.fen(),
                    clock_seconds=node.clock(),
                )
            )
            board.push(move)

        if not moves:
            skipped += 1
            continue

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        pgn_out = game.accept(exporter)

        white_elo, black_elo = _to_int(h.get("WhiteElo")), _to_int(h.get("BlackElo"))
        my_rating, opp_rating = (
            (white_elo, black_elo) if color == "white" else (black_elo, white_elo)
        )
        time_control = _clean(h.get("TimeControl"))

        games.append(
            ParsedGame(
                id=f"{platform}:{_raw_game_id(h, pgn_out)}",
                platform=platform,
                username=username,
                url=_game_url(h),
                played_at=_played_at(h),
                color=color,
                result=result,
                termination=_clean(h.get("Termination")),
                time_control=time_control,
                time_class=time_class_from_control(time_control),
                opening_eco=_clean(h.get("ECO")),
                opening_name=_clean(h.get("Opening")) or _opening_from_url(h.get("ECOUrl")),
                my_rating=my_rating,
                opp_rating=opp_rating,
                opp_name=black if color == "white" else white,
                num_plies=len(moves),
                pgn=pgn_out,
                moves=moves,
            )
        )

    return games, skipped
