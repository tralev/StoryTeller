"""Versioned operational checkpoint database for the frozen v2 pipeline."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..domain.artifacts import ArtifactRef
from .artifact_repository import ArtifactRepository

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Attempt:
    number: int
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class WorkCheckpoint:
    scope: str
    work_id: str
    status: str
    artifact: ArtifactRef | None
    dependencies: tuple[str, ...]
    producer_fingerprint: str
    attempts: tuple[Attempt, ...]


class V2CheckpointStore:
    """Run/phase/sub-step/node records with transactional schema upgrades."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError("CHECKPOINT_UNSUPPORTED_VERSION")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs(
                  run_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS work(
                  run_id TEXT NOT NULL, scope TEXT NOT NULL, work_id TEXT NOT NULL,
                  status TEXT NOT NULL, artifact_json TEXT, dependencies_json TEXT NOT NULL,
                  producer_fingerprint TEXT NOT NULL, updated_at REAL NOT NULL,
                  PRIMARY KEY(run_id, scope, work_id),
                  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS attempts(
                  run_id TEXT NOT NULL, scope TEXT NOT NULL, work_id TEXT NOT NULL,
                  number INTEGER NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
                  retryable INTEGER NOT NULL, occurred_at REAL NOT NULL,
                  PRIMARY KEY(run_id, scope, work_id, number));
            """)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def begin_run(self, run_id: str, fingerprint: str) -> None:
        with self._connect() as connection:
            existing = connection.execute("SELECT fingerprint FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if existing and existing[0] != fingerprint:
                raise ValueError("CHECKPOINT_RUN_FINGERPRINT_MISMATCH")
            connection.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?)", (run_id, fingerprint, time.time()))

    def save(self, run_id: str, scope: str, work_id: str, status: str, *,
             artifact: ArtifactRef | None, dependencies: Iterable[str],
             producer_fingerprint: str) -> None:
        if scope not in {"phase", "substep", "node"}:
            raise ValueError("CHECKPOINT_INVALID_SCOPE")
        artifact_json = json.dumps(artifact.__dict__, sort_keys=True) if artifact else None
        deps = json.dumps(sorted(set(dependencies)))
        with self._connect() as connection:
            connection.execute("""INSERT OR REPLACE INTO work
              VALUES(?,?,?,?,?,?,?,?)""", (run_id, scope, work_id, status, artifact_json,
                                             deps, producer_fingerprint, time.time()))

    def record_attempt(self, run_id: str, scope: str, work_id: str, attempt: Attempt) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO attempts VALUES(?,?,?,?,?,?,?,?)",
                               (run_id, scope, work_id, attempt.number, attempt.code,
                                attempt.message, int(attempt.retryable), time.time()))

    def load(self, run_id: str, scope: str, work_id: str) -> WorkCheckpoint | None:
        with self._connect() as connection:
            row = connection.execute("""SELECT status,artifact_json,dependencies_json,
              producer_fingerprint FROM work WHERE run_id=? AND scope=? AND work_id=?""",
                                     (run_id, scope, work_id)).fetchone()
            attempts = connection.execute("""SELECT number,code,message,retryable FROM attempts
              WHERE run_id=? AND scope=? AND work_id=? ORDER BY number""",
                                          (run_id, scope, work_id)).fetchall()
        if row is None: return None
        raw = json.loads(row[1]) if row[1] else None
        if raw:
            raw["depends_on"] = tuple(raw.get("depends_on", ()))
        artifact = ArtifactRef(**raw) if raw else None
        return WorkCheckpoint(scope, work_id, row[0], artifact, tuple(json.loads(row[2])), row[3],
                              tuple(Attempt(item[0], item[1], item[2], bool(item[3])) for item in attempts))


def reusable(checkpoint: WorkCheckpoint, repository: ArtifactRepository,
             dependencies: Iterable[str], producer_fingerprint: str) -> bool:
    """Reuse only verified bytes with the exact dependency and producer set."""
    return (checkpoint.status == "complete" and checkpoint.artifact is not None
            and checkpoint.dependencies == tuple(sorted(set(dependencies)))
            and checkpoint.producer_fingerprint == producer_fingerprint
            and checkpoint.artifact.depends_on == checkpoint.dependencies
            and checkpoint.artifact.producer_fingerprint == producer_fingerprint
            and repository.exists_verified(checkpoint.artifact))


def invalidation_closure(records: Iterable[WorkCheckpoint], changed_ids: set[str]) -> set[str]:
    invalid = set(changed_ids)
    pending = list(records)
    while True:
        expanded = invalid | {record.artifact.artifact_id for record in pending
                              if record.artifact is not None
                              and any(dependency in invalid for dependency in record.dependencies)}
        if expanded == invalid: return invalid
        invalid = expanded
