"""Avaliação de posições com o Stockfish, com cache em SQLite.

Uso pela linha de comando:
    python evaluator.py                 # lista as últimas partidas do banco
    python evaluator.py ID_DA_PARTIDA   # mostra os erros daquela partida
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import threading
from pathlib import Path

import chess
import chess.engine

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "chesscoach.db"
DEFAULT_DEPTH = int(os.environ.get("ANALYSIS_DEPTH", "12"))
MATE_CP = 10_000  # valor usado para representar mate em centipeões


def find_stockfish() -> str:
    """Procura o executável: STOCKFISH_PATH, pasta do projeto ou PATH do sistema."""
    candidates: list[str | Path] = []
    if os.environ.get("STOCKFISH_PATH"):
        candidates.append(os.environ["STOCKFISH_PATH"])
    # "stockfish.exe.exe" acontece quando o Windows esconde a extensão e o arquivo é renomeado.
    candidates += [BASE_DIR / "stockfish.exe", BASE_DIR / "stockfish.exe.exe", BASE_DIR / "stockfish"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    found = shutil.which("stockfish")
    if found:
        return found
    raise FileNotFoundError(
        "Stockfish não encontrado. Coloque o stockfish.exe na pasta do projeto "
        "ou defina a variável de ambiente STOCKFISH_PATH."
    )


def white_cp(evaluation: dict) -> int | None:
    """Avaliação do ponto de vista das brancas, em centipeões (mate vira ±MATE_CP)."""
    if evaluation.get("score_cp") is not None:
        return int(evaluation["score_cp"])
    mate = evaluation.get("mate_in")
    if mate is None or mate == 0:
        return None
    return MATE_CP if mate > 0 else -MATE_CP


class StockfishEvaluator:
    """Um único processo do Stockfish, compartilhado com segurança entre threads."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB,
        stockfish_path: str | None = None,
        threads: int | None = None,
        hash_mb: int = 128,
    ):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stockfish_evals (
                fen TEXT PRIMARY KEY,
                score_cp INTEGER,
                mate_in INTEGER,
                best_move TEXT,
                depth INTEGER
            )
            """
        )
        self.conn.commit()

        path = stockfish_path if stockfish_path and Path(stockfish_path).is_file() else find_stockfish()
        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        options = {"Threads": threads or max(1, (os.cpu_count() or 2) - 1), "Hash": hash_mb}
        self.engine.configure({k: v for k, v in options.items() if k in self.engine.options})

    def get_evaluation(self, fen: str, depth: int = DEFAULT_DEPTH) -> dict:
        """Avaliação da posição (ponto de vista das brancas) + melhor lance em UCI."""
        with self._lock:
            row = self.conn.execute(
                "SELECT score_cp, mate_in, best_move, depth FROM stockfish_evals WHERE fen = ?", (fen,)
            ).fetchone()
            # Reaproveita qualquer avaliação razoavelmente profunda que já esteja no cache.
            if row and (row[3] or 0) >= min(depth, 10):
                return {"score_cp": row[0], "mate_in": row[1], "best_move": row[2], "cached": True}

            board = chess.Board(fen)
            if board.is_checkmate():
                # Quem está com a vez levou mate.
                score_cp, mate_in, best_move = (-MATE_CP if board.turn == chess.WHITE else MATE_CP), None, None
            elif board.is_game_over():
                score_cp, mate_in, best_move = 0, None, None  # afogamento, material insuficiente...
            else:
                info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
                score = info["score"].white()
                score_cp, mate_in = score.score(), score.mate()
                pv = info.get("pv")
                best_move = pv[0].uci() if pv else None

            self.conn.execute(
                "INSERT OR REPLACE INTO stockfish_evals (fen, score_cp, mate_in, best_move, depth) "
                "VALUES (?, ?, ?, ?, ?)",
                (fen, score_cp, mate_in, best_move, depth),
            )
            self.conn.commit()
            return {"score_cp": score_cp, "mate_in": mate_in, "best_move": best_move, "cached": False}

    def close(self) -> None:
        try:
            self.engine.quit()
        finally:
            self.conn.close()


if __name__ == "__main__":
    from analysis import analyze_game

    coach = StockfishEvaluator()
    try:
        if len(sys.argv) > 1:
            result = analyze_game(coach, sys.argv[1])
            for m in result["moves"]:
                if m["is_user"] and m["severity"] in ("mistake", "blunder"):
                    print(
                        f"[{m['severity']}] Lance {m['move_number']}: jogou {m['played_move']}, "
                        f"o melhor era {m['best_move']} (−{m['cp_loss']} cp)"
                    )
            print(f"Precisão: {result['summary']['accuracy']}% | ACPL: {result['summary']['acpl']}")
        else:
            print("Uso: python evaluator.py ID_DA_PARTIDA\nÚltimas partidas no banco:")
            for row in coach.conn.execute(
                "SELECT id, played_at, color, result FROM games ORDER BY played_at DESC LIMIT 5"
            ):
                print(f"  {row[0]} | {row[1]} | {row[2]} | {row[3]}")
    finally:
        coach.close()
