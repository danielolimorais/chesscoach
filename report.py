"""Relatório agregado das últimas N partidas de um jogador.

Tudo é calculado a partir das tabelas `game_analysis` e `move_analysis`; o Stockfish
não é chamado aqui. Partidas ainda não analisadas entram só nas estatísticas de resultado.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

import chess

from analysis import ensure_schema
from heuristics import CATEGORY_LABELS, MistakeContext, classify_mistake

PHASES = ("opening", "middlegame", "endgame")
PHASE_LABELS = {"opening": "abertura", "middlegame": "meio-jogo", "endgame": "final"}
_OPENING_KEYWORDS = {"Opening", "Defense", "Defence", "Attack", "Gambit", "System", "Game"}


def opening_family(name: str | None) -> str:
    """'Queens Pawn Opening Zukertort Variation' -> 'Queens Pawn Opening'."""
    if not name:
        return "Desconhecida"
    name = name.split(":")[0].strip()
    words = name.split()
    for i, word in enumerate(words):
        if word in _OPENING_KEYWORDS:
            return " ".join(words[: i + 1])
    return " ".join(words[:3])


def _pct(part: float, total: float) -> float:
    return round(100 * part / total, 1) if total else 0.0


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _results(games: list[dict]) -> dict:
    n = len(games)
    w = sum(g["result"] == "win" for g in games)
    d = sum(g["result"] == "draw" for g in games)
    l = sum(g["result"] == "loss" for g in games)
    return {"games": n, "wins": w, "draws": d, "losses": l, "score_pct": _pct(w + 0.5 * d, n)}


def _error_rate(moves: list[dict]) -> float:
    """Erros graves (erros + blunders) a cada 100 lances."""
    return _pct(sum(m["severity"] in ("mistake", "blunder") for m in moves), len(moves))


def categorize_mistakes(rows: list[dict]) -> dict[tuple[str, int], str]:
    """Aplica as heurísticas (heuristics.py) a cada erro/blunder do usuário.

    `rows` são as linhas de move_analysis ordenadas por partida e lance. A linha seguinte de
    cada lance traz a melhor resposta do adversário e a avaliação de mate depois do lance.
    """
    result: dict[tuple[str, int], str] = {}
    for i, m in enumerate(rows):
        if not m["is_user"] or m["severity"] not in ("mistake", "blunder"):
            continue
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1]["game_id"] == m["game_id"] else None
        sign = 1 if m["color"] == "white" else -1

        def mine(value):  # converte do ponto de vista das brancas para o de quem jogou
            return None if value is None else sign * value

        board = chess.Board(m["fen_before"])
        try:
            ctx = MistakeContext(
                board=board,
                played=chess.Move.from_uci(m["uci"]),
                best=chess.Move.from_uci(m["best_uci"]) if m["best_uci"] else None,
                reply=chess.Move.from_uci(nxt["best_uci"]) if nxt and nxt["best_uci"] else None,
                eval_before=mine(m["eval_before"]),
                eval_after=mine(m["eval_after"]),
                mate_before=mine(m["mate_before"]),
                mate_after=mine(nxt["mate_before"]) if nxt else None,
                phase=m["phase"],
                time_pressure=bool(m["time_pressure"]),
            )
            result[(m["game_id"], m["ply"])] = classify_mistake(ctx)
        except Exception as exc:  # uma heurística com bug não pode derrubar o relatório
            print(f"[heurísticas] erro ao classificar {m['game_id']} lance {m['ply']}: {exc!r}", flush=True)
            result[(m["game_id"], m["ply"])] = "other"
    return result


def build_report(conn: sqlite3.Connection, username: str, limit: int = 30) -> dict:
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    games = [
        dict(r)
        for r in conn.execute(
            """
            SELECT g.id, g.played_at, g.color, g.result, g.opp_name, g.opp_rating, g.my_rating,
                   g.time_class, g.time_control, g.opening_name, g.url,
                   a.accuracy, a.acpl, a.blunders, a.mistakes, a.inaccuracies,
                   a.max_eval, a.min_eval, a.user_moves,
                   a.game_id IS NOT NULL AS analyzed
            FROM games g LEFT JOIN game_analysis a ON a.game_id = g.id
            WHERE lower(g.username) = lower(?)
            ORDER BY g.played_at DESC
            LIMIT ?
            """,
            (username, limit),
        )
    ]
    analyzed = [g for g in games if g["analyzed"]]
    by_id = {g["id"]: g for g in games}

    all_moves: list[dict] = []
    if analyzed:
        marks = ",".join("?" * len(analyzed))
        all_moves = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM move_analysis WHERE game_id IN ({marks}) ORDER BY game_id, ply",
                [g["id"] for g in analyzed],
            )
        ]
    categories = categorize_mistakes(all_moves)
    moves = [m for m in all_moves if m["is_user"]]

    # ---------------- resultados (todas as partidas)
    results = {
        "overall": _results(games),
        "white": _results([g for g in games if g["color"] == "white"]),
        "black": _results([g for g in games if g["color"] == "black"]),
        "by_time_class": {
            tc: _results([g for g in games if g["time_class"] == tc])
            for tc, _ in Counter(g["time_class"] for g in games).most_common()
            if tc
        },
    }

    # ---------------- qualidade de jogo (partidas analisadas)
    errors = {
        "blunders": sum(m["severity"] == "blunder" for m in moves),
        "mistakes": sum(m["severity"] == "mistake" for m in moves),
        "inaccuracies": sum(m["severity"] == "inaccuracy" for m in moves),
    }
    n_an = len(analyzed)
    quality = {
        "accuracy": _mean(g["accuracy"] for g in analyzed),
        "acpl": _mean(m["cp_loss"] for m in moves),
        "accuracy_white": _mean(g["accuracy"] for g in analyzed if g["color"] == "white"),
        "accuracy_black": _mean(g["accuracy"] for g in analyzed if g["color"] == "black"),
        "acpl_white": _mean(m["cp_loss"] for m in moves if m["color"] == "white"),
        "acpl_black": _mean(m["cp_loss"] for m in moves if m["color"] == "black"),
        "blunders_per_game": round(errors["blunders"] / n_an, 2) if n_an else None,
        "mistakes_per_game": round(errors["mistakes"] / n_an, 2) if n_an else None,
        **errors,
    }

    # ---------------- fases
    phases = []
    for ph in PHASES:
        pm = [m for m in moves if m["phase"] == ph]
        phases.append(
            {
                "phase": ph,
                "moves": len(pm),
                "acpl": _mean(m["cp_loss"] for m in pm),
                "accuracy": _mean(m["accuracy"] for m in pm),
                "blunders": sum(m["severity"] == "blunder" for m in pm),
                "mistakes": sum(m["severity"] == "mistake" for m in pm),
                "inaccuracies": sum(m["severity"] == "inaccuracy" for m in pm),
                "error_rate": _error_rate(pm),
            }
        )

    # ---------------- pressão de tempo
    pressured = [m for m in moves if m["time_pressure"]]
    calm = [m for m in moves if not m["time_pressure"]]
    serious = [m for m in moves if m["severity"] in ("mistake", "blunder")]
    time_pressure = {
        "moves": len(pressured),
        "share_of_moves": _pct(len(pressured), len(moves)),
        "error_rate_pressure": _error_rate(pressured),
        "error_rate_normal": _error_rate(calm),
        "share_of_serious_errors": _pct(sum(m["time_pressure"] for m in serious), len(serious)),
    }

    # ---------------- aberturas
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for g in games:
        groups[(opening_family(g["opening_name"]), g["color"])].append(g)
    openings = sorted(
        (
            {
                "name": name,
                "color": color,
                **_results(gs),
                "accuracy": _mean(g["accuracy"] for g in gs if g["analyzed"]),
            }
            for (name, color), gs in groups.items()
        ),
        key=lambda o: (-o["games"], o["name"]),
    )[:10]

    # ---------------- vantagens
    wasted = [g for g in analyzed if (g["max_eval"] or 0) >= 300 and g["result"] != "win"]
    saved = [g for g in analyzed if (g["min_eval"] or 0) <= -300 and g["result"] != "loss"]

    # ---------------- rating (ritmo mais jogado)
    main_tc = next(iter(results["by_time_class"]), None)
    rating_history = [
        {"date": g["played_at"], "rating": g["my_rating"]}
        for g in sorted(games, key=lambda g: g["played_at"] or "")
        if g["time_class"] == main_tc and g["my_rating"]
    ]

    # ---------------- maiores erros
    top = sorted(serious, key=lambda m: m["win_drop"], reverse=True)[:8]
    top_mistakes = [
        {
            "game_id": m["game_id"],
            "ply": m["ply"],
            "move_number": m["move_number"],
            "color": m["color"],
            "fen_before": m["fen_before"],
            "played_move": m["san"],
            "played_uci": m["uci"],
            "best_move": m["best_san"],
            "best_uci": m["best_uci"],
            "win_drop": round(m["win_drop"], 1),
            "cp_loss": m["cp_loss"],
            "severity": m["severity"],
            "phase": m["phase"],
            "time_pressure": bool(m["time_pressure"]),
            "category": categories.get((m["game_id"], m["ply"]), "other"),
            "category_label": CATEGORY_LABELS[categories.get((m["game_id"], m["ply"]), "other")],
            "opp_name": by_id[m["game_id"]]["opp_name"],
            "played_at": by_id[m["game_id"]]["played_at"],
        }
        for m in top
    ]

    counts = Counter(categories.values())
    error_types = [
        {"key": key, "label": CATEGORY_LABELS[key], "count": n, "share": _pct(n, len(categories))}
        for key, n in sorted(counts.items(), key=lambda kv: (kv[0] == "other", -kv[1]))
    ]

    report = {
        "username": username,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limit": limit,
        "total_games": len(games),
        "analyzed_games": n_an,
        "complete": n_an == len(games) and len(games) > 0,
        "results": results,
        "quality": quality,
        "phases": phases,
        "error_types": error_types,
        "time_pressure": time_pressure,
        "openings": openings,
        "advantage": {
            "wasted": len(wasted),
            "saved": len(saved),
            "wasted_games": [g["id"] for g in wasted],
        },
        "rating": {"time_class": main_tc, "history": rating_history},
        "top_mistakes": top_mistakes,
        "games": [
            {k: g[k] for k in ("id", "played_at", "color", "result", "opp_name", "opp_rating", "my_rating",
                               "time_class", "opening_name", "accuracy", "blunders", "mistakes", "analyzed")}
            for g in games
        ],
    }
    report["insights"] = build_insights(report)
    return report


def _n(x: float, digits: int = 1) -> str:
    """Número no formato brasileiro: 13.8 -> '13,8'."""
    return f"{x:.{digits}f}".replace(".", ",")


def build_insights(r: dict) -> list[str]:
    """Frases curtas, em português, com o que mais chama atenção nos números."""
    insights: list[str] = []
    if r["analyzed_games"] == 0:
        return insights

    phases = [p for p in r["phases"] if p["moves"] >= 20]
    if len(phases) >= 2:
        def where(p: dict) -> str:
            return "na abertura" if p["phase"] == "opening" else f"no {PHASE_LABELS[p['phase']]}"

        worst = max(phases, key=lambda p: p["error_rate"])
        others = [p for p in phases if p is not worst]
        if worst["error_rate"] > 0:
            comp = " e ".join(f"{_n(p['error_rate'])} {where(p)}" for p in others)
            insights.append(
                f"Você erra mais {where(worst)}: {_n(worst['error_rate'])} erros graves a cada 100 lances, "
                f"contra {comp}."
            )

    tp = r["time_pressure"]
    if tp["moves"] >= 15 and tp["error_rate_pressure"] >= 1.5 * max(tp["error_rate_normal"], 0.1):
        insights.append(
            f"Com pouco tempo no relógio sua taxa de erros graves sobe de {_n(tp['error_rate_normal'])} "
            f"para {_n(tp['error_rate_pressure'])} a cada 100 lances; "
            f"{tp['share_of_serious_errors']:.0f}% dos seus erros graves aconteceram em apuros de tempo."
        )

    q = r["quality"]
    if q["accuracy_white"] is not None and q["accuracy_black"] is not None:
        diff = q["accuracy_white"] - q["accuracy_black"]
        if abs(diff) >= 3:
            better, worse = ("brancas", "pretas") if diff > 0 else ("pretas", "brancas")
            hi, lo = max(q["accuracy_white"], q["accuracy_black"]), min(q["accuracy_white"], q["accuracy_black"])
            insights.append(f"Você joga com mais precisão de {better} ({_n(hi)}%) do que de {worse} ({_n(lo)}%).")

    adv = r["advantage"]
    if adv["wasted"] >= 2:
        insights.append(
            f"Em {adv['wasted']} partidas você chegou a ter vantagem decisiva (+3 ou mais) e não venceu. "
            "Converter vantagens é um ótimo foco de treino."
        )
    elif adv["saved"] >= 2:
        insights.append(f"Você salvou {adv['saved']} partidas em que esteve claramente perdido: boa resiliência.")

    candidates = [o for o in r["openings"] if o["games"] >= 3]
    if candidates:
        worst_op = min(candidates, key=lambda o: o["score_pct"])
        cor = "brancas" if worst_op["color"] == "white" else "pretas"
        if worst_op["score_pct"] < 40:
            insights.append(
                f"Na {worst_op['name']}, jogando de {cor}, você fez só {worst_op['score_pct']:.0f}% dos pontos "
                f"em {worst_op['games']} partidas: vale revisar essa linha."
            )
        best_op = max(candidates, key=lambda o: o["score_pct"])
        if best_op["score_pct"] >= 65:
            cor = "brancas" if best_op["color"] == "white" else "pretas"
            insights.append(
                f"Seu melhor desempenho é na {best_op['name']}, jogando de {cor}: "
                f"{best_op['score_pct']:.0f}% dos pontos em {best_op['games']} partidas."
            )

    return insights
