"""Fix content_hashes and artifact_ids in .story test fixtures.

The Phase 5.6I PackageAcceptance now validates these fields.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from io import BytesIO
from pathlib import Path


def compute_content_hash(artifacts: dict[str, bytes]) -> str:
    """Canonical SHA256 of sorted content/* entries — mirrors storage.content_hash."""
    hasher = hashlib.sha256()
    for name in sorted(artifacts):
        hasher.update(name.encode())
        hasher.update(b"\x00")
        hasher.update(artifacts[name])
    return hasher.hexdigest()


def fix_story_fixture(story_path: Path) -> None:
    """Update a .story fixture with correct content_hash and artifact_id."""
    # Read the ZIP into memory
    with open(story_path, "rb") as f:
        raw = f.read()

    with zipfile.ZipFile(BytesIO(raw), "r") as zf_in:
        # Read manifest
        manifest = json.loads(zf_in.read("manifest.json"))

        # Collect content/* entries for hash
        artifacts: dict[str, bytes] = {}
        for name in sorted(zf_in.namelist()):
            if name.startswith("content/") and not name.endswith("/"):
                artifacts[name] = zf_in.read(name)

        # Compute correct content_hash
        content_hash = compute_content_hash(artifacts)

        # Set artifact_id from content_hash
        manifest["content_hash"] = content_hash
        manifest.setdefault("meta", {})
        manifest["meta"]["artifact_id"] = f"package_{content_hash[:8]}"

        # Ensure story_id exists
        if "story_id" not in manifest:
            manifest["story_id"] = f"story_{content_hash[:12]}"

        # Rebuild ZIP with updated manifest
        new_buf = BytesIO()
        with zipfile.ZipFile(new_buf, "w", zipfile.ZIP_DEFLATED) as zf_out:
            # Write updated manifest first
            info = zipfile.ZipInfo("manifest.json", (1980, 1, 1, 0, 0, 0))
            zf_out.writestr(info, json.dumps(manifest, sort_keys=True).encode())

            # Copy all other entries
            for name in sorted(zf_in.namelist()):
                if name == "manifest.json":
                    continue
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                zf_out.writestr(info, zf_in.read(name))

        new_bytes = new_buf.getvalue()

    # Atomic write
    tmp = Path(str(story_path) + ".tmp")
    with open(tmp, "wb") as f:
        f.write(new_bytes)
    os.replace(tmp, story_path)

    print(f"  Fixed: {story_path.name}")
    print(f"    content_hash: {content_hash[:16]}...")
    print(f"    artifact_id:  package_{content_hash[:8]}")


def main() -> None:
    fixture_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    for name in ["minimal_valid_1_node.story", "complete_15_nodes.story"]:
        path = fixture_dir / name
        if path.exists():
            fix_story_fixture(path)
        else:
            print(f"  SKIP: {name} not found")


if __name__ == "__main__":
    main()
