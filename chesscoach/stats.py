"""Estatísticas básicas sobre as partidas já importadas."""

from __future__ import annotations

import sqlite3


def _where(username: str, platform: str | None, time_class: str | None) -> tuple[str, list]:
    clauses, params = ["lower(username) = lower(?)"], [username]
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    if time_class:
        clauses.append("time_class = ?")
        params.append(time_class)
    return " AND ".join(clauses), params


def _pct(part: int, total: int) -> float:
    return round(100 * part / total, 1) if total else 0.0


def overall(
    conn: sqlite3.Connection,
    username: str,
    platform: str | None = None,
    time_class: str | None = None,
) -> dict:
    where, params = _where(username, platform, time_class)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               SUM(result = 'win')  AS wins,
               SUM(result = 'draw') AS draws,
               SUM(result = 'loss') AS losses,
               AVG(num_plies)       AS avg_plies
        FROM games WHERE {where}
        """,
        params,
    ).fetchone()
    total = row["total"] or 0
    wins, draws, losses = (row["wins"] or 0), (row["draws"] or 0), (row["losses"] or 0)

    by_color = {}
    for color in ("white", "black"):
        c = conn.execute(
            f"""
            SELECT COUNT(*) AS n, SUM(result = 'win') AS w,
                   SUM(result = 'draw') AS d, SUM(result = 'loss') AS l
            FROM games WHERE {where} AND color = ?
            """,
            params + [color],
        ).fetchone()
        n = c["n"] or 0
        by_color[color] = {
            "games": n,
            "win_pct": _pct(c["w"] or 0, n),
            "draw_pct": _pct(c["d"] or 0, n),
            "loss_pct": _pct(c["l"] or 0, n),
        }

    return {
        "total": total,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_pct": _pct(wins, total),
        "draw_pct": _pct(draws, total),
        "loss_pct": _pct(losses, total),
        "avg_moves": round((row["avg_plies"] or 0) / 2, 1),
        "by_color": by_color,
    }


def openings(
    conn: sqlite3.Connection,
    username: str,
    platform: str | None = None,
    time_class: str | None = None,
    color: str | None = None,
    min_games: int = 2,
    limit: int = 10,
) -> list[dict]:
    where, params = _where(username, platform, time_class)
    if color:
        where += " AND color = ?"
        params = params + [color]
    rows = conn.execute(
        f"""
        SELECT COALESCE(opening_name, opening_eco, 'Desconhecida') AS opening,
               color,
               COUNT(*) AS games,
               SUM(result = 'win')  AS wins,
               SUM(result = 'draw') AS draws,
               SUM(result = 'loss') AS losses
        FROM games WHERE {where}
        GROUP BY opening, color
        HAVING COUNT(*) >= ?
        ORDER BY games DESC, opening
        LIMIT ?
        """,
        params + [min_games, limit],
    ).fetchall()
    return [
        {
            "opening": r["opening"],
            "color": r["color"],
            "games": r["games"],
            "win_pct": _pct(r["wins"], r["games"]),
            "draw_pct": _pct(r["draws"], r["games"]),
            "loss_pct": _pct(r["losses"], r["games"]),
        }
        for r in rows
    ]


def rating_history(
    conn: sqlite3.Connection,
    username: str,
    platform: str | None = None,
    time_class: str | None = None,
) -> list[tuple[str, int]]:
    where, params = _where(username, platform, time_class)
    rows = conn.execute(
        f"""
        SELECT played_at, my_rating FROM games
        WHERE {where} AND my_rating IS NOT NULL AND played_at IS NOT NULL
        ORDER BY played_at
        """,
        params,
    ).fetchall()
    return [(r["played_at"], r["my_rating"]) for r in rows]
