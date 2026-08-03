"""Checkpoint system — SQLite-based save/resume for long-running generation pipelines.

Allows a 24-hour pipeline run to be interrupted and resumed without losing progress.
Each generation step records its output and seed, enabling deterministic replay.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


@dataclass
class CheckpointEntry:
    """A single checkpoint record."""

    step_name: str
    phase: int  # Pipeline phase number
    seed: int
    output_json: str  # JSON-serialized output
    completed_at: float  # Unix timestamp
    artifact_id: str = ""
    attempt_count: int = 1


class CheckpointStore:
    """SQLite-backed checkpoint store for resumable generation.

    Usage:
        store = CheckpointStore("output/checkpoint.db")
        store.save("world_builder", 1, seed=42, output={"bible": ...})
        ...
        entry = store.load("world_builder")
        if entry:
            print(f"Resuming from {entry.step_name}")
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the checkpoints table if it doesn't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    step_name TEXT PRIMARY KEY,
                    phase INTEGER NOT NULL,
                    seed INTEGER NOT NULL,
                    output_json TEXT NOT NULL,
                    completed_at REAL NOT NULL,
                    artifact_id TEXT DEFAULT '',
                    attempt_count INTEGER DEFAULT 1
                )
            """)
            conn.commit()

    def save(
        self,
        step_name: str,
        phase: int,
        seed: int,
        output: Dict[str, Any],
        artifact_id: str = "",
        attempt_count: int = 1,
    ) -> None:
        """Save a checkpoint for a pipeline step.

        Uses INSERT OR REPLACE — overwrites previous checkpoint for the same step.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (step_name, phase, seed, output_json, completed_at, artifact_id, attempt_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    step_name,
                    phase,
                    seed,
                    json.dumps(output, sort_keys=True),
                    time.time(),
                    artifact_id,
                    attempt_count,
                ),
            )
            conn.commit()

    def load(self, step_name: str) -> Optional[CheckpointEntry]:
        """Load a checkpoint by step name.

        Returns None if no checkpoint exists for this step.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT step_name, phase, seed, output_json, completed_at, artifact_id, attempt_count "
                "FROM checkpoints WHERE step_name = ?",
                (step_name,),
            ).fetchone()

        if row is None:
            return None

        return CheckpointEntry(
            step_name=row[0],
            phase=row[1],
            seed=row[2],
            output_json=row[3],
            completed_at=row[4],
            artifact_id=row[5],
            attempt_count=row[6],
        )

    def load_all(self) -> List[CheckpointEntry]:
        """Load all checkpoints, ordered by phase."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT step_name, phase, seed, output_json, completed_at, artifact_id, attempt_count "
                "FROM checkpoints ORDER BY phase ASC"
            ).fetchall()

        return [
            CheckpointEntry(
                step_name=r[0], phase=r[1], seed=r[2], output_json=r[3],
                completed_at=r[4], artifact_id=r[5], attempt_count=r[6],
            )
            for r in rows
        ]

    def get_completed_phases(self) -> List[int]:
        """Return sorted list of completed phase numbers."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT DISTINCT phase FROM checkpoints ORDER BY phase ASC"
            ).fetchall()
        return [r[0] for r in rows]

    def get_highest_completed_phase(self) -> int:
        """Return the highest phase number that has a checkpoint."""
        phases = self.get_completed_phases()
        return max(phases) if phases else 0

    def delete(self, step_name: str) -> None:
        """Delete a checkpoint."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM checkpoints WHERE step_name = ?", (step_name,))
            conn.commit()

    def clear(self) -> None:
        """Delete all checkpoints (start fresh)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM checkpoints")
            conn.commit()

    def output_for_step(self, step_name: str) -> Optional[Dict[str, Any]]:
        """Load just the output JSON for a step, parsed as a dict."""
        entry = self.load(step_name)
        if entry is None:
            return None
        return cast(Dict[str, Any], json.loads(entry.output_json))
