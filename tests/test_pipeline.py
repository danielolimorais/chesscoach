from pathlib import Path

import pytest

from chesscoach import db, stats
from chesscoach.importer import import_pgn_text
from chesscoach.pgn_parser import parse_pgn_text, time_class_from_control

DATA = Path(__file__).parent / "data"


def read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def test_parse_chesscom_sample():
    games, skipped = parse_pgn_text(read("chesscom_sample.pgn"), "meu_user", "chesscom")

    assert skipped == 1  # a partida Chess960 é ignorada
    assert len(games) == 2

    win, draw = games
    assert win.id == "chesscom:111"
    assert (win.color, win.result) == ("white", "win")
    assert (win.my_rating, win.opp_rating) == (1950, 1900)
    assert win.opening_eco == "C20"
    assert win.opening_name == "Kings Pawn Opening Wayward Queen Attack"
    assert win.time_class == "rapid"
    assert win.num_plies == 7
    assert win.moves[0].san == "e4" and win.moves[0].clock_seconds == pytest.approx(598.9)
    assert win.moves[-1].san == "Qxf7#"

    # usuário com caixa diferente no PGN ("Meu_User") ainda é reconhecido
    assert (draw.color, draw.result) == ("black", "draw")
    assert (draw.my_rating, draw.opp_rating) == (1960, 2010)
    assert draw.time_class == "blitz"


def test_parse_lichess_sample():
    games, skipped = parse_pgn_text(read("lichess_sample.pgn"), "meu_user", "lichess")

    assert skipped == 2  # variante Atomic + partida sem o usuário
    assert [g.id for g in games] == ["lichess:AbCd1234", "lichess:EfGh5678"]

    loss, win = games
    assert (loss.color, loss.result) == ("black", "loss")
    assert loss.opening_name == "Ruy Lopez: Morphy Defense"
    assert loss.time_class == "blitz"
    assert (win.color, win.result) == ("white", "win")


def test_fen_before_is_position_before_the_move():
    games, _ = parse_pgn_text(read("lichess_sample.pgn"), "meu_user", "lichess")
    first, second = games[0].moves[0], games[0].moves[1]
    assert first.fen_before.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w")
    assert second.fen_before.startswith("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b")


def test_import_is_idempotent_and_stats_work():
    conn = db.connect(":memory:")
    pgn = read("chesscom_sample.pgn")

    first = import_pgn_text(conn, pgn, "chesscom", "meu_user")
    assert (first.parsed, first.inserted, first.duplicates, first.skipped) == (2, 2, 0, 1)

    again = import_pgn_text(conn, pgn, "chesscom", "meu_user")
    assert (again.inserted, again.duplicates) == (0, 2)

    assert conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0] == 7 + 6

    ov = stats.overall(conn, "meu_user")
    assert ov["total"] == 2
    assert ov["win_pct"] == 50.0 and ov["draw_pct"] == 50.0
    assert ov["by_color"]["white"]["win_pct"] == 100.0

    ops = stats.openings(conn, "meu_user", min_games=1)
    assert {o["games"] for o in ops} == {1}
    assert len(ops) == 2


@pytest.mark.parametrize(
    "tc,expected",
    [("60", "bullet"), ("180+2", "blitz"), ("600", "rapid"), ("1800", "classical"),
     ("1/86400", "daily"), (None, None), ("-", None)],
)
def test_time_class(tc, expected):
    assert time_class_from_control(tc) == expected
