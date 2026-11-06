"""Testes do dataset de ML (sem Stockfish: usa um avaliador falso)."""

from pathlib import Path

import chess
import numpy as np
import pandas as pd
import pytest

from analysis import analyze_game
from chesscoach import db
from chesscoach.importer import import_pgn_text
from evaluator import MATE_CP
from ml.dataset import (
    LEAKY_COLUMNS,
    board_features,
    build_dataset,
    feature_columns,
    parse_time_control,
)
from ml.train import risk_table, temporal_split

DATA = Path(__file__).parent / "data"


class FakeEvaluator:
    def __init__(self, db_path):
        self.db_path = str(db_path)

    def get_evaluation(self, fen, depth=12):
        board = chess.Board(fen)
        if board.is_checkmate():
            return {"score_cp": -MATE_CP if board.turn == chess.WHITE else MATE_CP, "mate_in": None, "best_move": None}
        return {"score_cp": 20, "mate_in": None, "best_move": None}


@pytest.fixture()
def dataset(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    import_pgn_text(conn, (DATA / "chesscom_sample.pgn").read_text(encoding="utf-8"), "chesscom", "meu_user")
    conn.close()
    ev = FakeEvaluator(path)
    for gid in ("chesscom:111", "chesscom:222"):
        analyze_game(ev, gid)
    return build_dataset(db.connect(path), "MEU_USER")


def test_one_row_per_user_move(dataset):
    # partida 111: meu_user de brancas, 7 meios-lances -> 4 lances dele
    # partida 222: meu_user de pretas, 6 meios-lances -> 3 lances dele
    assert len(dataset) == 7
    assert dataset.groupby("game_id").size().to_dict() == {"chesscom:111": 4, "chesscom:222": 3}


def test_no_leaky_features(dataset):
    features = set(feature_columns(dataset))
    assert not features & LEAKY_COLUMNS
    assert not {"y", "game_id", "played_at"} & features


def test_features_are_numeric(dataset):
    X = dataset[feature_columns(dataset)]
    assert all(np.issubdtype(t, np.number) for t in X.dtypes)


def test_label_matches_severity(dataset):
    # O avaliador falso sempre diz +0,20: nenhuma queda, nenhum erro grave.
    assert dataset["y"].sum() == 0


def test_clock_and_time_spent(dataset):
    g = dataset[dataset["game_id"] == "chesscom:111"].sort_values("ply")
    # TimeControl 600, relógio depois de 1.e4 = 9:58.9 -> gastou 1,1 s; começou com 600 s
    assert g.iloc[0]["clock_before"] == 600
    assert g.iloc[0]["time_spent"] == pytest.approx(1.1, abs=0.01)
    # 2.Bc4 com 9:55.0, depois de 9:58.9 no lance anterior -> gastou 3,9 s
    assert g.iloc[1]["time_spent"] == pytest.approx(3.9, abs=0.01)


def test_behavior_flag_removes_time_spent(dataset):
    assert "time_spent" in feature_columns(dataset)
    assert "time_spent" not in feature_columns(dataset, behavior=False)


def test_parse_time_control():
    assert parse_time_control("180+2") == (180, 2)
    assert parse_time_control("600") == (600, 0)
    assert parse_time_control("1/86400") == (None, 0)
    assert parse_time_control(None) == (None, 0)


def test_board_features_hanging_piece():
    # Brancas jogam; o cavalo branco em e5 está atacado pelo peão d6 e sem defensor
    f = board_features("4k3/8/3p4/4N3/8/8/8/4K3 w - - 0 1")
    assert f["my_hanging"] == 1 and f["my_hanging_value"] == 3
    assert f["my_attacked_by_lower"] == 1
    assert f["material_diff"] == 2  # cavalo (3) contra peão (1)


def test_temporal_split_keeps_games_whole():
    df = pd.DataFrame(
        {"game_id": list("aabbccddee"), "played_at": ["2026-01-0%d" % i for i in (1, 1, 2, 2, 3, 3, 4, 4, 5, 5)]}
    )
    train, test = temporal_split(df, test_frac=0.2)
    assert set(test["game_id"]) == {"e"}
    assert not set(train["game_id"]) & set(test["game_id"])


def test_risk_table_is_ordered():
    rng = np.random.default_rng(0)
    p = rng.random(1000)
    y = (rng.random(1000) < p).astype(int)
    table = risk_table(y, p)
    assert table["erro_real"].is_monotonic_increasing
