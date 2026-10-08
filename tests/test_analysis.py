"""Testes da análise e do relatório sem depender do Stockfish (avaliador falso)."""

from pathlib import Path

import chess
import pytest

from analysis import (
    analyze_game,
    classify,
    game_phase,
    move_accuracy,
    pressure_threshold,
    winning_chances,
)
from chesscoach import db
from chesscoach.importer import import_pgn_text
from evaluator import MATE_CP
from report import build_report, opening_family

DATA = Path(__file__).parent / "data"


class FakeEvaluator:
    """Devolve avaliações pré-definidas por FEN e conta quantas vezes foi chamado."""

    def __init__(self, db_path, evals=None):
        self.db_path = str(db_path)
        self.evals = evals or {}
        self.calls = 0

    def get_evaluation(self, fen, depth=12):
        self.calls += 1
        board = chess.Board(fen)
        if board.is_checkmate():
            return {"score_cp": -MATE_CP if board.turn == chess.WHITE else MATE_CP, "mate_in": None, "best_move": None}
        return self.evals.get(fen, {"score_cp": 20, "mate_in": None, "best_move": None})


# ------------------------------------------------------------ matemática

def test_winning_chances_is_symmetric_and_bounded():
    assert winning_chances(0) == 0
    assert winning_chances(300) == pytest.approx(-winning_chances(-300))
    assert -1 < winning_chances(-5000) < winning_chances(5000) < 1


def test_move_accuracy():
    assert move_accuracy(50, 50) == 100
    assert move_accuracy(50, 60) == 100  # melhorar a posição não é penalizado
    assert move_accuracy(80, 20) < 15


@pytest.mark.parametrize("drop,expected", [(0.05, "good"), (0.1, "inaccuracy"), (0.25, "mistake"), (0.4, "blunder")])
def test_classify(drop, expected):
    assert classify(drop) == expected


def test_game_phase():
    assert game_phase(chess.Board(), 1) == "opening"
    assert game_phase(chess.Board(), 20) == "middlegame"
    assert game_phase(chess.Board("8/5k2/8/8/8/2R5/5K2/8 w - - 0 50"), 50) == "endgame"


def test_pressure_threshold_and_openings():
    assert pressure_threshold("180") == 18
    assert pressure_threshold("60") == 10
    assert pressure_threshold("1/86400") is None
    assert opening_family("Queens Pawn Opening Zukertort Variation") == "Queens Pawn Opening"
    assert opening_family("Ruy Lopez: Morphy Defense") == "Ruy Lopez"
    assert opening_family(None) == "Desconhecida"


# ------------------------------------------------------------ análise + relatório

@pytest.fixture()
def game_db(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    import_pgn_text(conn, (DATA / "chesscom_sample.pgn").read_text(encoding="utf-8"), "chesscom", "meu_user")
    conn.close()
    return path


def test_analyze_game_flags_opponent_blunder_and_caches(game_db):
    # Mate do pastor: 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? 4.Qxf7#
    board = chess.Board()
    fens = []
    for san in ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"]:
        fens.append(board.fen())
        board.push_san(san)
    after_nf6 = board.fen()
    evals = {after_nf6: {"score_cp": None, "mate_in": 1, "best_move": "h5f7"}}
    fen_before_qh5 = fens[4]
    evals[fen_before_qh5] = {"score_cp": 30, "mate_in": None, "best_move": "d1h5"}  # Qh5 = melhor lance

    ev = FakeEvaluator(game_db, evals)
    result = analyze_game(ev, "chesscom:111")
    moves = {m["ply"]: m for m in result["moves"]}

    assert moves[6]["played_move"] == "Nf6" and moves[6]["severity"] == "blunder"
    assert moves[6]["is_user"] is False  # quem errou foi o adversário (meu_user joga de brancas)
    assert moves[5]["severity"] == "best"
    assert moves[7]["played_move"] == "Qxf7#" and moves[7]["best_move"] == "Qxf7#"
    assert result["summary"]["blunders"] == 0 and result["summary"]["user_moves"] == 4

    calls = ev.calls
    analyze_game(ev, "chesscom:111")  # segunda vez: lido do banco, sem avaliar de novo
    assert ev.calls == calls


def test_report(game_db):
    ev = FakeEvaluator(game_db)
    analyze_game(ev, "chesscom:111")
    conn = db.connect(game_db)
    report = build_report(conn, "MEU_USER", limit=30)

    assert report["total_games"] == 2 and report["analyzed_games"] == 1 and not report["complete"]
    assert report["results"]["overall"] == {"games": 2, "wins": 1, "draws": 1, "losses": 0, "score_pct": 75.0}
    assert report["quality"]["accuracy"] is not None
    assert [p["phase"] for p in report["phases"]] == ["opening", "middlegame", "endgame"]
    assert isinstance(report["insights"], list)
