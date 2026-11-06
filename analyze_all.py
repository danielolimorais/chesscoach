"""Analisa com o Stockfish, em lote, todas as partidas importadas de um jogador.

Uso (na pasta do projeto, com a .venv ativa):
    python -m chesscoach import chesscom SEU_NICK --max 500   # 1) importa as partidas
    python analyze_all.py SEU_NICK                            # 2) analisa as que faltam

Opções:
    --limit N     analisa no máximo N partidas (as mais recentes primeiro)
    --depth D     profundidade do Stockfish (padrão: 12, a mesma do app)

Pode interromper com Ctrl+C a qualquer momento: cada partida é salva assim que termina,
e rodar de novo continua de onde parou. O backend (uvicorn) pode continuar ligado.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time

from analysis import analyze_game, ensure_schema
from evaluator import DEFAULT_DB, DEFAULT_DEPTH, StockfishEvaluator


def pending_games(db_path: str, username: str, limit: int | None) -> list[str]:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        ensure_schema(conn)
        sql = """
            SELECT g.id FROM games g
            LEFT JOIN game_analysis a ON a.game_id = g.id
            WHERE lower(g.username) = lower(?) AND a.game_id IS NULL
            ORDER BY g.played_at DESC
        """
        params: list = [username]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [row[0] for row in conn.execute(sql, params)]
    finally:
        conn.close()


def count_games(db_path: str, username: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM games WHERE lower(username) = lower(?)", (username,)
        ).fetchone()[0]
        done = conn.execute(
            "SELECT COUNT(*) FROM games g JOIN game_analysis a ON a.game_id = g.id "
            "WHERE lower(g.username) = lower(?)",
            (username,),
        ).fetchone()[0]
        return total, done
    finally:
        conn.close()


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}min {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}min"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # acentos no terminal do Windows
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username", help="nick do jogador, como foi importado")
    parser.add_argument("--limit", type=int, default=None, help="máximo de partidas nesta execução")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help=f"profundidade (padrão {DEFAULT_DEPTH})")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="arquivo do banco (padrão: chesscoach.db)")
    args = parser.parse_args(argv)

    total, done = count_games(args.db, args.username)
    if total == 0:
        print(f"Nenhuma partida de '{args.username}' no banco. Importe antes:")
        print(f"  python -m chesscoach import chesscom {args.username} --max 500")
        return 1

    todo = pending_games(args.db, args.username, args.limit)
    print(f"{args.username}: {total} partidas no banco, {done} já analisadas, {len(todo)} para analisar agora.")
    if not todo:
        print("Nada a fazer.")
        return 0

    evaluator = StockfishEvaluator(db_path=args.db)
    start = time.perf_counter()
    analyzed = failed = 0
    try:
        for i, game_id in enumerate(todo, start=1):
            try:
                analyze_game(evaluator, game_id, depth=args.depth)
                analyzed += 1
            except Exception as exc:  # uma partida com problema não interrompe o lote
                failed += 1
                print(f"\n  falhou: {game_id} ({exc!r})")
            elapsed = time.perf_counter() - start
            eta = elapsed / i * (len(todo) - i)
            print(
                f"\r  [{i}/{len(todo)}] {100 * i / len(todo):5.1f}%  "
                f"decorrido {fmt_duration(elapsed)}  restante ~{fmt_duration(eta)}   ",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi analisado está salvo; rode de novo para continuar.")
    finally:
        evaluator.close()

    print(f"\nPronto: {analyzed} analisadas, {failed} com erro, em {fmt_duration(time.perf_counter() - start)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
