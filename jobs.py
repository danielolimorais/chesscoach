"""Análise em segundo plano: o front-end acompanha o progresso consultando o status."""

from __future__ import annotations

import sqlite3
import threading
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from analysis import analyze_game, is_analyzed


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AnalysisJob:
    username: str
    game_ids: list[str]
    status: str = "running"  # running | done | error
    done: int = 0
    failed: int = 0
    current: str | None = None
    error: str | None = None
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None

    @property
    def total(self) -> int:
        return len(self.game_ids)

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("game_ids")
        data["total"] = self.total
        return data


class JobManager:
    def __init__(self, get_evaluator, db_path: str):
        self._get_evaluator = get_evaluator  # função: devolve o StockfishEvaluator (ou levanta erro)
        self._db_path = db_path
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = threading.Lock()

    def start(self, username: str, game_ids: list[str]) -> AnalysisJob:
        key = username.lower()
        with self._lock:
            job = self._jobs.get(key)
            if job and job.status == "running":
                return job
            job = AnalysisJob(username=username, game_ids=list(game_ids))
            self._jobs[key] = job
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"analysis-{key}").start()
        return job

    def get(self, username: str) -> AnalysisJob | None:
        return self._jobs.get(username.lower())

    def _run(self, job: AnalysisJob) -> None:
        try:
            evaluator = self._get_evaluator()
            conn = sqlite3.connect(self._db_path, timeout=30)
            try:
                pending = [gid for gid in job.game_ids if not is_analyzed(conn, gid)]
            finally:
                conn.close()
            job.done = job.total - len(pending)

            for gid in pending:
                job.current = gid
                try:
                    analyze_game(evaluator, gid)
                except Exception:  # uma partida com problema não derruba as outras
                    job.failed += 1
                    traceback.print_exc()
                job.done += 1
            job.status = "done"
        except Exception as exc:
            job.status, job.error = "error", str(exc)
            traceback.print_exc()
        finally:
            job.current = None
            job.finished_at = _now()
