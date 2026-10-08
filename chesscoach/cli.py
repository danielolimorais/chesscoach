"""Interface de linha de comando.

Exemplos:
    python -m chesscoach import chesscom SEU_USUARIO --max 200
    python -m chesscoach import lichess SEU_USUARIO --max 200
    python -m chesscoach import-file minhas_partidas.pgn --platform chesscom --user SEU_USUARIO
    python -m chesscoach stats SEU_USUARIO --time-class blitz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from . import db, stats
from .clients import ClientError
from .importer import PLATFORMS, import_from_platform, import_pgn_text


def _print_import(result) -> None:
    print(
        f"Partidas lidas: {result.parsed} | novas: {result.inserted} | "
        f"já existiam: {result.duplicates} | ignoradas: {result.skipped}"
    )


def cmd_import(args) -> int:
    conn = db.connect(args.db)
    print(f"Buscando até {args.max} partidas de {args.username} em {args.platform}...")
    try:
        result = import_from_platform(conn, args.platform, args.username, args.max)
    except ClientError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Erro de rede ao acessar {args.platform}: {exc}", file=sys.stderr)
        return 1
    _print_import(result)
    return 0


def cmd_import_file(args) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Arquivo não encontrado: {path}", file=sys.stderr)
        return 1
    conn = db.connect(args.db)
    text = path.read_text(encoding="utf-8", errors="replace")
    _print_import(import_pgn_text(conn, text, args.platform, args.user))
    return 0


def cmd_stats(args) -> int:
    conn = db.connect(args.db)
    ov = stats.overall(conn, args.username, args.platform, args.time_class)
    if ov["total"] == 0:
        print("Nenhuma partida encontrada. Rode o comando 'import' primeiro.")
        return 1

    print(f"\n=== {args.username} — {ov['total']} partidas ===")
    print(
        f"Vitórias {ov['win_pct']}% | Empates {ov['draw_pct']}% | "
        f"Derrotas {ov['loss_pct']}% | média {ov['avg_moves']} lances"
    )
    for color, label in (("white", "Brancas"), ("black", "Pretas")):
        c = ov["by_color"][color]
        print(
            f"  {label}: {c['games']} partidas — "
            f"V {c['win_pct']}% / E {c['draw_pct']}% / D {c['loss_pct']}%"
        )

    ops = stats.openings(conn, args.username, args.platform, args.time_class,
                         min_games=args.min_games, limit=args.top)
    print(f"\nAberturas mais jogadas (mín. {args.min_games} partidas):")
    if not ops:
        print("  (poucas partidas para agrupar por abertura)")
    for o in ops:
        cor = "B" if o["color"] == "white" else "P"
        print(
            f"  [{cor}] {o['opening'][:45]:<45} {o['games']:>3} jogos  "
            f"V {o['win_pct']:>5}%  E {o['draw_pct']:>5}%  D {o['loss_pct']:>5}%"
        )

    history = stats.rating_history(conn, args.username, args.platform, args.time_class)
    if history:
        print(f"\nRating: {history[0][1]} ({history[0][0][:10]}) -> "
              f"{history[-1][1]} ({history[-1][0][:10]})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chesscoach", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="chesscoach.db", help="arquivo SQLite (padrão: chesscoach.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="busca partidas pela API da plataforma")
    p.add_argument("platform", choices=PLATFORMS)
    p.add_argument("username")
    p.add_argument("--max", type=int, default=100, help="quantidade máxima de partidas (padrão: 100)")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("import-file", help="importa um arquivo .pgn local")
    p.add_argument("path")
    p.add_argument("--platform", choices=PLATFORMS, required=True)
    p.add_argument("--user", required=True, help="seu nome de usuário dentro do PGN")
    p.set_defaults(func=cmd_import_file)

    p = sub.add_parser("stats", help="mostra estatísticas das partidas importadas")
    p.add_argument("username")
    p.add_argument("--platform", choices=PLATFORMS)
    p.add_argument("--time-class", choices=["bullet", "blitz", "rapid", "classical", "daily"])
    p.add_argument("--min-games", type=int, default=2)
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Evita erros de acentuação no terminal do Windows (cp1252).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)
