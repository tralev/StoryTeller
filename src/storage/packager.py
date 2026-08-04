"""Packager — produces deterministic .story ZIP archives with atomic writes.

ZIP structure:
  manifest.json          (root)
  content/bible.json      (immutable)
  content/story.json
  content/graph.json
  content/gm_index.json
  content/style_bible.json
  content/images/*.png
  content/midi/*.mid
  content/thumbnails/*.png
  save/.gitkeep           (mutable, reader state)

Phase 5.5E: Atomic writes — ZIP is written to a .tmp file first,
then atomically renamed. Prevents partial/corrupt .story files
if the process crashes mid-write.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from ..job_queue import PipelineContext
from ..models.base import StepOutput


class Packager:
    """Package all artifacts into a deterministic .story ZIP.

    Reads JSON artifacts from context.outputs and media files from
    paths stored in images/midi metadata.

    Usage:
        packager = Packager(output_dir="output")
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["manifest"] = {...}
        context.outputs["bible"] = {...}
        ...
        output = await packager.run(context)
    """

    def __init__(self, output_dir: str = "output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, context: PipelineContext) -> StepOutput:
        """Build and write the .story ZIP."""
        manifest = context.outputs.get("manifest", {})
        title = manifest.get("title", "untitled")
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
        zip_path = self.output_dir / f"{safe_title}_{context.seed}.story"

        # Collect JSON artifacts
        artifacts: dict[str, bytes] = {}
        for key, zip_name in [
            ("bible", "content/bible.json"),
            ("story", "content/story.json"),
            ("graph", "content/graph.json"),
            ("gm_index", "content/gm_index.json"),
            ("style_bible", "content/style_bible.json"),
        ]:
            data = context.outputs.get(key)
            if data is not None:
                artifacts[zip_name] = json.dumps(data, sort_keys=True).encode()

        # Collect media files from disk paths
        img_count = self._collect_media(
            artifacts, context, "images", "content/images", "image_path",
        )
        thumb_count = self._collect_media(
            artifacts, context, "images", "content/thumbnails", "thumb_path",
        )
        midi_count = self._collect_media(
            artifacts, context, "midi", "content/midi", "midi_path",
        )

        # Compute content hash using canonical algorithm (Phase 5.6 A5)
        from .content_hash import compute_content_hash
        content_hash = compute_content_hash(artifacts)

        # Set hash, operational metadata, and file counts in manifest
        manifest["content_hash"] = content_hash
        manifest.setdefault("meta", {})
        manifest["meta"]["artifact_id"] = f"package_{content_hash[:8]}"
        start = context.state.get("start_time", time.time())
        manifest["meta"]["generation_time_seconds"] = round(time.time() - start, 2)
        manifest.setdefault("stats", {})
        manifest["stats"]["total_images"] = img_count
        manifest["stats"]["total_thumbnails"] = thumb_count
        manifest["stats"]["total_midi_files"] = midi_count

        # Write manifest
        artifacts["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()

        # Build deterministic ZIP to temp file, then atomic rename
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(artifacts.keys()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                zf.writestr(info, artifacts[name])
            info = zipfile.ZipInfo("save/.gitkeep", (1980, 1, 1, 0, 0, 0))
            zf.writestr(info, "")

        zip_bytes = buf.getvalue()
        tmp_path = Path(str(zip_path) + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(zip_bytes)
        os.replace(tmp_path, zip_path)  # Atomic rename

        digest = hashlib.sha256(zip_bytes).hexdigest()[:8]
        return StepOutput(
            data={
                "package_path": str(zip_path),
                "package_size": len(zip_bytes),
                "content_hash": content_hash,
                "image_count": img_count,
                "midi_count": midi_count,
            },
            step_name="packager",
            artifact_id=f"package_{digest}",
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _collect_media(
        artifacts: dict[str, bytes],
        context: PipelineContext,
        output_key: str,
        zip_dir: str,
        path_key: str,
    ) -> int:
        """Collect media files from disk and add to artifacts dict.

        Args:
            artifacts: Dict to add file bytes to (zip_path → bytes).
            context: Pipeline context with outputs.
            output_key: Key in context.outputs (e.g., "images", "midi").
            zip_dir: ZIP directory prefix (e.g., "content/images").
            path_key: Key in each node's metadata dict for the file path.

        Returns:
            Number of files collected.
        """
        data = context.outputs.get(output_key)
        if not isinstance(data, dict):
            return 0

        count = 0
        # data may have {"images": {node_id: {path_key: "...", ...}}} or
        # {"midi": {node_id: {path_key: "...", ...}}}
        items = data.get(output_key, data) if output_key in data else data
        if not isinstance(items, dict):
            return 0

        for node_id, meta in items.items():
            if not isinstance(meta, dict):
                continue
            file_path = meta.get(path_key, "")
            if not file_path:
                continue
            p = Path(file_path)
            if not p.exists():
                continue
            zip_name = f"{zip_dir}/{node_id}{p.suffix}"
            artifacts[zip_name] = p.read_bytes()
            count += 1

        return count

    # _compute_hash removed — use storage.content_hash.compute_content_hash instead (Phase 5.6 A5)
