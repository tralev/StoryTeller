"""Packager — produces deterministic .story ZIP archives.

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

    Usage:
        packager = Packager(output_dir="output")
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["manifest"] = {...}
        context.outputs["bible"] = {...}
        context.outputs["story"] = {...}
        context.outputs["graph"] = {...}
        context.outputs["gm_index"] = {...}
        context.outputs["style_bible"] = {...}
        context.outputs["images"] = {...}
        context.outputs["midi"] = {...}
        output = await packager.run(context)
        # output.data["package_path"] = "output/story_*.story"
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

        # Collect all artifacts
        artifacts: dict[str, bytes] = {}
        self._collect_json_artifact(artifacts, "content/bible.json", context, "bible")
        self._collect_json_artifact(artifacts, "content/story.json", context, "story")
        self._collect_json_artifact(artifacts, "content/graph.json", context, "graph")
        self._collect_json_artifact(artifacts, "content/gm_index.json", context, "gm_index")
        self._collect_json_artifact(artifacts, "content/style_bible.json", context, "style_bible")

        # Compute content hash BEFORE writing manifest
        content_hash = self._compute_hash(artifacts)

        # Set hash and stats in manifest
        manifest["content_hash"] = content_hash
        manifest.setdefault("stats", {})
        manifest["stats"]["generation_time_seconds"] = time.time() - context.state.get(
            "start_time", time.time()
        )

        # Write manifest
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        artifacts["manifest.json"] = manifest_bytes

        # Build deterministic ZIP
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write entries in sorted order for determinism
            for name in sorted(artifacts.keys()):
                zf.writestr(name, artifacts[name])
            # Empty save/ directory marker
            zf.writestr("save/.gitkeep", "")

        zip_bytes = buf.getvalue()
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        digest = hashlib.sha256(zip_bytes).hexdigest()[:8]
        return StepOutput(
            data={
                "package_path": str(zip_path),
                "package_size": len(zip_bytes),
                "content_hash": content_hash,
            },
            step_name="packager",
            artifact_id=f"package_{digest}",
        )

    @staticmethod
    def _collect_json_artifact(
        artifacts: dict[str, bytes],
        path: str,
        context: PipelineContext,
        key: str,
    ) -> None:
        data = context.outputs.get(key)
        if data is not None:
            artifacts[path] = json.dumps(data, sort_keys=True).encode()

    @staticmethod
    def _compute_hash(artifacts: dict[str, bytes]) -> str:
        hasher = hashlib.sha256()
        for name in sorted(artifacts.keys()):
            hasher.update(name.encode())
            hasher.update(artifacts[name])
        return hasher.hexdigest()
