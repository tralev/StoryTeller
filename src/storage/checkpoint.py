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
from typing import Any, cast

from ..pipeline.artifacts import ArtifactKey


@dataclass
class CheckpointEntry:
    """A single checkpoint record."""

    step_name: str
    output_key: str  # Canonical artifact key (e.g., "bible", not "world_builder")
    phase: int  # Pipeline phase number
    seed: int
    output_json: str  # JSON-serialized output
    completed_at: float  # Unix timestamp (operational, not part of artifact ID)
    artifact_id: str = ""  # Content-derived, never includes timestamps
    attempt_count: int = 1
    run_fingerprint: str = ""  # Config + model hash — identifies run identity


@dataclass
class NodeCheckpointRecord:
    """A node-level checkpoint with reconciliation metadata (Phase 5.6 O3/O4).

    Carries the canonical artifact path and the SHA-256 content hash of the
    media file on disk at save time. On resume, the scheduler compares the
    stored hash against the actual file to detect deletion or corruption
    (O4) and regenerates on mismatch. ``run_seed`` identifies the generating
    run so assets from a different seed are never reused (P5).
    """

    node_id: str
    output: dict[str, Any]
    content_hash: str = ""  # SHA-256 hex of the artifact file at save time
    artifact_path: str = ""  # Canonical path of the artifact on disk
    run_seed: int | None = None  # Base run seed that produced this asset


class CheckpointStore:
    """SQLite-backed checkpoint store for resumable generation.

    Usage:
        store = CheckpointStore("tmp/output/checkpoint.db")
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

    # Canonical artifact key for each step — downstream steps expect
    # "bible", not "world_builder", etc.
    _STEP_KEY_MAP: dict[str, ArtifactKey] = {
        "world_builder": "bible",
        "art_director": "style_bible",
        "story_writer": "story",
        "game_designer": "graph",
        "image_generator": "images",
        "music_generator": "midi",
        "indexer": "gm_index",
    }

    @staticmethod
    def canonical_key(step_name: str) -> str:
        """Return the canonical artifact key for a step name."""
        return CheckpointStore._STEP_KEY_MAP.get(step_name, step_name)

    def _init_db(self) -> None:
        """Create the checkpoints table if it doesn't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    step_name TEXT PRIMARY KEY,
                    output_key TEXT NOT NULL DEFAULT '',
                    phase INTEGER NOT NULL,
                    seed INTEGER NOT NULL,
                    output_json TEXT NOT NULL,
                    completed_at REAL NOT NULL,
                    artifact_id TEXT DEFAULT '',
                    attempt_count INTEGER DEFAULT 1,
                    run_fingerprint TEXT DEFAULT ''
                )
            """)
            # Phase 5.5H: Node-level checkpoint table for batch resume
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_checkpoints (
                    step_name TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    completed_at REAL NOT NULL,
                    seed INTEGER NOT NULL,
                    attempt_count INTEGER DEFAULT 1,
                    content_hash TEXT DEFAULT '',
                    artifact_path TEXT DEFAULT '',
                    run_seed INTEGER,
                    PRIMARY KEY (step_name, node_id)
                )
            """)
            # Add output_key column to existing tables (migration)
            try:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN output_key TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN run_fingerprint TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            # Phase 5.6 O3/P5: content hash, canonical path, run seed for
            # node reconciliation + fingerprint-mismatch detection
            for _col, _ddl in (
                ("content_hash", "TEXT DEFAULT ''"),
                ("artifact_path", "TEXT DEFAULT ''"),
                ("run_seed", "INTEGER"),
            ):
                try:
                    conn.execute(
                        f"ALTER TABLE node_checkpoints ADD COLUMN {_col} {_ddl}"
                    )
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def save(
        self,
        step_name: str,
        phase: int,
        seed: int,
        output: dict[str, Any],
        output_key: str | None = None,
        artifact_id: str = "",
        attempt_count: int = 1,
        run_fingerprint: str = "",
    ) -> None:
        """Save a checkpoint for a pipeline step.

        Uses INSERT OR REPLACE — overwrites previous checkpoint for the same step.

        Args:
            step_name: Internal step ID (e.g., "world_builder").
            phase: Pipeline phase number.
            seed: Generation seed.
            output: The generated artifact dict.
            output_key: Canonical artifact key (e.g., "bible"). Auto-derived if None.
            artifact_id: Content-derived artifact identifier (no timestamps).
            attempt_count: Number of attempts taken.
            run_fingerprint: Config + model hash identifying this run.
        """
        if output_key is None:
            output_key = CheckpointStore.canonical_key(step_name)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (step_name, output_key, phase, seed, output_json, completed_at,
                    artifact_id, attempt_count, run_fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    step_name,
                    output_key,
                    phase,
                    seed,
                    json.dumps(output, sort_keys=True),
                    time.time(),
                    artifact_id,
                    attempt_count,
                    run_fingerprint,
                ),
            )
            conn.commit()

    def load(self, step_name: str) -> CheckpointEntry | None:
        """Load a checkpoint by step name.

        Returns None if no checkpoint exists for this step.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT step_name, output_key, phase, seed, output_json, completed_at, "
                "artifact_id, attempt_count, run_fingerprint "
                "FROM checkpoints WHERE step_name = ?",
                (step_name,),
            ).fetchone()

        if row is None:
            return None

        return CheckpointEntry(
            step_name=row[0],
            output_key=row[1] or CheckpointStore.canonical_key(row[0]),
            phase=row[2],
            seed=row[3],
            output_json=row[4],
            completed_at=row[5],
            artifact_id=row[6] or "",
            attempt_count=row[7] or 1,
            run_fingerprint=row[8] or "",
        )

    def load_all(self) -> list[CheckpointEntry]:
        """Load all checkpoints, ordered by phase."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT step_name, output_key, phase, seed, output_json, completed_at, "
                "artifact_id, attempt_count, run_fingerprint "
                "FROM checkpoints ORDER BY phase ASC"
            ).fetchall()

        return [
            CheckpointEntry(
                step_name=r[0],
                output_key=r[1] or CheckpointStore.canonical_key(r[0]),
                phase=r[2], seed=r[3], output_json=r[4],
                completed_at=r[5], artifact_id=r[6] or "", attempt_count=r[7] or 1,
                run_fingerprint=r[8] or "",
            )
            for r in rows
        ]

    def get_completed_phases(self) -> list[int]:
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

    def get_run_fingerprint(self) -> str | None:
        """Return the run fingerprint stored in the checkpoints.

        Reads from any checkpoint entry (all entries in a single run
        share the same fingerprint). Returns None if the DB is empty
        or if entries have no fingerprint (legacy DB).

        Phase 5.6C: Used to verify that a resume operation uses the
        same config+models as the original run.
        """
        entries = self.load_all()
        if not entries:
            return None
        # All entries should have the same fingerprint — take the first non-empty
        for entry in entries:
            if entry.run_fingerprint:
                return entry.run_fingerprint
        return None  # Legacy — no fingerprint stored

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

    def output_for_step(self, step_name: str) -> dict[str, Any] | None:
        """Load just the output JSON for a step, parsed as a dict."""
        entry = self.load(step_name)
        if entry is None:
            return None
        return cast(dict[str, Any], json.loads(entry.output_json))

    # ── node-level checkpoints (Phase 5.5H) ────────────────────────────

    def save_node(
        self,
        step_name: str,
        node_id: str,
        output: dict[str, Any],
        seed: int,
        attempt_count: int = 1,
        content_hash: str = "",
        artifact_path: str = "",
        run_seed: int | None = None,
    ) -> None:
        """Save a node-level checkpoint for batch resume.

        Each node in a batch step (image, music) gets its own checkpoint.
        On resume, completed nodes are skipped.

        Args:
            step_name: e.g. "image_generator" or "music_generator".
            node_id: The node identifier (e.g., "node_01").
            output: The generated artifact for this node.
            seed: Seed used (for determinism verification).
            attempt_count: Number of attempts taken.
            content_hash: SHA-256 hex of the artifact file on disk (O3).
            artifact_path: Canonical path of the artifact file (O3).
            run_seed: Base run seed that produced this asset — used to
                reject assets from a different seed on resume (P5).
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO node_checkpoints
                   (step_name, node_id, output_json, completed_at, seed, attempt_count,
                    content_hash, artifact_path, run_seed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    step_name,
                    node_id,
                    json.dumps(output, sort_keys=True),
                    time.time(),
                    seed,
                    attempt_count,
                    content_hash,
                    artifact_path,
                    run_seed,
                ),
            )
            conn.commit()

    def load_node(
        self, step_name: str, node_id: str,
    ) -> dict[str, Any] | None:
        """Load a node-level checkpoint.

        Returns None if no checkpoint exists for this step+node.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT output_json FROM node_checkpoints "
                "WHERE step_name = ? AND node_id = ?",
                (step_name, node_id),
            ).fetchone()

        if row is None:
            return None
        return cast(dict[str, Any], json.loads(row[0]))

    def load_all_nodes(self, step_name: str) -> dict[str, dict[str, Any]]:
        """Load all node checkpoints for a step.

        Returns:
            {node_id: output_dict} for all completed nodes.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT node_id, output_json FROM node_checkpoints "
                "WHERE step_name = ?",
                (step_name,),
            ).fetchall()

        return {r[0]: cast(dict[str, Any], json.loads(r[1])) for r in rows}

    def load_all_node_records(
        self, step_name: str,
    ) -> dict[str, NodeCheckpointRecord]:
        """Load all node checkpoints with reconciliation metadata (Phase 5.6 O3).

        Unlike ``load_all_nodes`` (output dicts only), this returns records
        carrying the stored content hash, canonical artifact path, and run
        seed so the scheduler can reconcile checkpoints against the actual
        files on disk and against the current run identity (P5).

        Returns:
            {node_id: NodeCheckpointRecord} for all completed nodes.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT node_id, output_json, content_hash, artifact_path, run_seed "
                "FROM node_checkpoints WHERE step_name = ?",
                (step_name,),
            ).fetchall()

        return {
            r[0]: NodeCheckpointRecord(
                node_id=r[0],
                output=cast(dict[str, Any], json.loads(r[1])),
                content_hash=r[2] or "",
                artifact_path=r[3] or "",
                run_seed=r[4],
            )
            for r in rows
        }

    def delete_node(self, step_name: str, node_id: str) -> None:
        """Delete a node-level checkpoint."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "DELETE FROM node_checkpoints WHERE step_name = ? AND node_id = ?",
                (step_name, node_id),
            )
            conn.commit()

    def clear_nodes(self, step_name: str) -> None:
        """Delete all node checkpoints for a step."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "DELETE FROM node_checkpoints WHERE step_name = ?",
                (step_name,),
            )
            conn.commit()

    # ── sub-step checkpoints (Phase 5.6L) ──────────────────────────────

    def save_sub(
        self,
        step_name: str,
        sub_id: str,
        output: dict[str, Any],
        seed: int,
        dependency_hash: str = "",
    ) -> None:
        """Save a sub-step checkpoint for long text operations.

        StoryWriter saves: outline, chapter_1, chapter_2, chapter_3.
        GameDesigner saves: decision_points, skeleton, node_01..node_15.

        Each sub-checkpoint carries a dependency_hash of the upstream
        artifact (bible for StoryWriter, story for GameDesigner).
        If the dependency changes, the sub-checkpoint is invalidated.

        Uses node_checkpoints table with sub_id stored as node_id
        and dependency_hash stored in a new column (migrated on demand).
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            # Migration: add dep_hash column if not present
            try:
                conn.execute(
                    "ALTER TABLE node_checkpoints ADD COLUMN dep_hash TEXT DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass
            conn.execute(
                """INSERT OR REPLACE INTO node_checkpoints
                   (step_name, node_id, output_json, completed_at, seed, dep_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    step_name,
                    sub_id,
                    json.dumps(output, sort_keys=True),
                    time.time(),
                    seed,
                    dependency_hash,
                ),
            )
            conn.commit()

    def load_sub(
        self,
        step_name: str,
        sub_id: str,
        dependency_hash: str = "",
    ) -> dict[str, Any] | None:
        """Load a sub-step checkpoint.

        Returns None if:
          - No checkpoint exists for this step+sub_id
          - The stored dependency_hash doesn't match (upstream changed)
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            # Migration
            try:
                conn.execute(
                    "ALTER TABLE node_checkpoints ADD COLUMN dep_hash TEXT DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass
            row = conn.execute(
                "SELECT output_json, dep_hash FROM node_checkpoints "
                "WHERE step_name = ? AND node_id = ?",
                (step_name, sub_id),
            ).fetchone()

        if row is None:
            return None
        output_json, stored_dep = row
        if dependency_hash and stored_dep and stored_dep != dependency_hash:
            return None  # Dependency changed — invalidate
        return cast(dict[str, Any], json.loads(output_json))

    def clear_subs(self, step_name: str) -> None:
        """Delete all sub-step checkpoints for a step."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "DELETE FROM node_checkpoints WHERE step_name = ?",
                (step_name,),
            )
            conn.commit()
