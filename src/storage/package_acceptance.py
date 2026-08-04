"""PackageAcceptance — validates a .story ZIP as an external consumer would.

Phase 5.5D: After packaging, reopens the .story archive and validates:
  1. No unsafe or absolute ZIP paths (path traversal prevention)
  2. All required entries exist (manifest, content/*)
  3. Every JSON artifact parses
  4. Manifest inventory matches actual files
  5. Graph entry point exists
  6. Referenced images/MIDI files exist
  7. No undeclared content files

Returns an AcceptanceResult — generation is only "complete" when
acceptance passes.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class AcceptanceIssue:
    """A single package acceptance issue."""

    severity: str  # "error" or "warning"
    path: str      # Path within the ZIP
    message: str


@dataclass
class AcceptanceResult:
    """Result of package acceptance validation."""

    accepted: bool
    issues: list[AcceptanceIssue] = field(default_factory=list)

    def format_issues(self) -> str:
        """Format issues as a human-readable report."""
        if self.accepted:
            return "Package acceptance: VALID."
        lines = [f"Package acceptance: {len(self.issues)} issue(s):"]
        for i in self.issues:
            lines.append(f"  [{i.severity}] {i.path}: {i.message}")
        return "\n".join(lines)


class PackageAcceptance:
    """Validate a .story ZIP archive as an external consumer.

    Usage:
        gate = PackageAcceptance(schemas_dir="schemas")
        result = gate.validate(zip_path)
        if not result.accepted:
            print(result.format_issues())
    """

    REQUIRED_ENTRIES = [
        "manifest.json",
        "content/bible.json",
        "content/story.json",
        "content/graph.json",
        "content/gm_index.json",
    ]

    OPTIONAL_ENTRIES = [
        "content/style_bible.json",
        "save/.gitkeep",
    ]

    ALLOWED_DIRS = [
        "content/images/",
        "content/midi/",
        "content/thumbnails/",
        "save/",
    ]

    SUPPORTED_SCHEMA_VERSION = 1

    # Extensions allowed in content/ directories
    ALLOWED_CONTENT_EXTENSIONS = {".json", ".png", ".mid", ".midi"}

    def __init__(self, schemas_dir: str | None = None) -> None:
        self._schemas_dir = schemas_dir

    def validate(self, zip_path: str | Path) -> AcceptanceResult:
        """Validate a .story package.

        Args:
            zip_path: Path to the .story ZIP file.

        Returns:
            AcceptanceResult with accepted flag and list of issues.
        """
        issues: list[AcceptanceIssue] = []
        zip_path = Path(zip_path)

        if not zip_path.exists():
            return AcceptanceResult(
                accepted=False,
                issues=[AcceptanceIssue("error", str(zip_path), "File not found")],
            )

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                all_names = set(zf.namelist())

                # 1. Security: reject unsafe paths
                issues.extend(self._check_unsafe_paths(all_names))

                # 2. Required entries
                issues.extend(self._check_required_entries(all_names))

                # 3. Parse and validate manifest
                manifest = self._parse_manifest(zf, issues)
                if manifest is None:
                    return AcceptanceResult(accepted=False, issues=issues)

                # 4. Manifest inventory matches actual files
                issues.extend(self._check_file_inventory(manifest, all_names))

                # 5. Schema-validate ALL contained JSON (I1)
                issues.extend(self._validate_all_json_schemas(zf))

                # 6. Recompute and compare content hash (I2)
                issues.extend(self._check_content_hash(zf, manifest))

                # 7. Require non-empty artifact/story IDs (I3)
                issues.extend(self._check_required_ids(manifest))

                # 8. Enforce supported versions (I7)
                issues.extend(self._check_supported_versions(manifest))

                # 9. Parse all JSON artifacts (parse only, schema done above)
                issues.extend(self._parse_json_artifacts(zf))

                # 10. Graph entry point exists
                issues.extend(self._check_graph_entry_point(zf, manifest))

                # 11. Referenced media files exist
                issues.extend(self._check_media_references(zf))

                # 12. No undeclared content files (I6: error, not warning)
                issues.extend(self._check_undeclared_files(manifest, all_names))

        except zipfile.BadZipFile:
            return AcceptanceResult(
                accepted=False,
                issues=[AcceptanceIssue("error", str(zip_path), "Not a valid ZIP file")],
            )
        except Exception as e:
            return AcceptanceResult(
                accepted=False,
                issues=[AcceptanceIssue("error", str(zip_path), f"Error reading ZIP: {e}")],
            )

        errors = [i for i in issues if i.severity == "error"]
        return AcceptanceResult(accepted=len(errors) == 0, issues=issues)

    # ── new checks (Phase 5.6I) ──────────────────────────────────────────

    def _validate_all_json_schemas(
        self, zf: zipfile.ZipFile,
    ) -> list[AcceptanceIssue]:
        """I1: Schema-validate all contained JSON artifacts."""
        issues: list[AcceptanceIssue] = []
        if not self._schemas_dir:
            return issues

        try:
            from ..validators.schema_validator import SchemaValidator
            sv = SchemaValidator(self._schemas_dir)
        except Exception:
            return issues

        schema_map = {
            "content/bible.json": "bible",
            "content/story.json": "story",
            "content/graph.json": "graph",
            "content/gm_index.json": "gm_index",
            "content/style_bible.json": "style_bible",
        }

        for zip_path, schema_name in schema_map.items():
            if zip_path not in zf.namelist():
                continue
            try:
                data = json.loads(zf.read(zip_path))
                result = sv.validate(data, schema_name)
                if not result.is_valid:
                    issues.append(
                        AcceptanceIssue(
                            "error", zip_path,
                            f"Schema validation failed: {result.format_for_retry()}",
                        )
                    )
            except json.JSONDecodeError:
                pass  # Already caught by _parse_json_artifacts
            except Exception as e:
                issues.append(
                    AcceptanceIssue("warning", zip_path,
                                    f"Schema check unavailable: {e}")
                )

        return issues

    @staticmethod
    def _check_content_hash(
        zf: zipfile.ZipFile, manifest: dict[str, Any],
    ) -> list[AcceptanceIssue]:
        """I2: Recompute canonical content hash and compare to manifest."""
        issues: list[AcceptanceIssue] = []
        expected = manifest.get("content_hash", "")
        if not expected:
            issues.append(
                AcceptanceIssue("error", "manifest.json",
                                "Missing content_hash in manifest")
            )
            return issues

        # Collect all content/* entries for hash computation
        from .content_hash import compute_content_hash
        artifacts: dict[str, bytes] = {}
        for name in sorted(zf.namelist()):
            if name.startswith("content/") and not name.endswith("/"):
                artifacts[name] = zf.read(name)

        actual = compute_content_hash(artifacts)
        if actual != expected:
            issues.append(
                AcceptanceIssue(
                    "error", "manifest.json",
                    f"Content hash mismatch: manifest={expected[:16]}..., "
                    f"actual={actual[:16]}...",
                )
            )

        return issues

    @staticmethod
    def _check_required_ids(manifest: dict[str, Any]) -> list[AcceptanceIssue]:
        """I3: Require non-empty artifact_id and story_id in manifest."""
        issues: list[AcceptanceIssue] = []

        meta = manifest.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        artifact_id = meta.get("artifact_id", "")
        if not artifact_id:
            issues.append(
                AcceptanceIssue("error", "manifest.json",
                                "Missing or empty meta.artifact_id")
            )

        story_id = manifest.get("story_id", "")
        if not story_id:
            issues.append(
                AcceptanceIssue("error", "manifest.json",
                                "Missing or empty story_id")
            )

        return issues

    @staticmethod
    def _check_supported_versions(
        manifest: dict[str, Any],
    ) -> list[AcceptanceIssue]:
        """I7: Enforce supported schema/package versions."""
        issues: list[AcceptanceIssue] = []

        schema_ver = manifest.get("schema_version")
        if schema_ver is None:
            issues.append(
                AcceptanceIssue("error", "manifest.json",
                                "Missing schema_version")
            )
        elif not isinstance(schema_ver, int) or schema_ver < 1:
            issues.append(
                AcceptanceIssue("error", "manifest.json",
                                f"Unsupported schema_version: {schema_ver}")
            )

        return issues

    # ── existing checks ─────────────────────────────────────────────────

    @staticmethod
    def _check_unsafe_paths(names: set[str]) -> list[AcceptanceIssue]:
        """Reject path traversal or absolute paths."""
        issues: list[AcceptanceIssue] = []
        for name in names:
            if name.startswith("/") or ".." in name.split("/"):
                issues.append(
                    AcceptanceIssue("error", name, "Unsafe path in ZIP (path traversal)")
                )
        return issues

    @staticmethod
    def _check_required_entries(names: set[str]) -> list[AcceptanceIssue]:
        """Check all required entries exist."""
        issues: list[AcceptanceIssue] = []
        for entry in PackageAcceptance.REQUIRED_ENTRIES:
            if entry not in names:
                issues.append(
                    AcceptanceIssue("error", entry, "Required entry missing")
                )
        return issues

    def _parse_manifest(
        self, zf: zipfile.ZipFile, issues: list[AcceptanceIssue],
    ) -> dict[str, Any] | None:
        """Parse and validate manifest.json."""
        try:
            manifest = cast(dict[str, Any], json.loads(zf.read("manifest.json")))
        except json.JSONDecodeError as e:
            issues.append(
                AcceptanceIssue("error", "manifest.json", f"Invalid JSON: {e}")
            )
            return None
        except KeyError:
            issues.append(
                AcceptanceIssue("error", "manifest.json", "Not found in ZIP")
            )
            return None

        # Schema validation (best-effort)
        if self._schemas_dir:
            try:
                from ..validators.schema_validator import SchemaValidator
                sv = SchemaValidator(self._schemas_dir)
                result = sv.validate_manifest(manifest)
                if not result.is_valid:
                    issues.append(
                        AcceptanceIssue("warning", "manifest.json", result.format_for_retry())
                    )
            except Exception:
                pass

        return manifest

    @staticmethod
    def _check_file_inventory(
        manifest: dict[str, Any], actual_names: set[str],
    ) -> list[AcceptanceIssue]:
        """Verify manifest files dict matches actual ZIP contents."""
        issues: list[AcceptanceIssue] = []
        declared = manifest.get("files", {})

        for key, expected_path in declared.items():
            if expected_path.endswith("/"):
                # Directory — check at least one file exists under it
                if not any(n.startswith(expected_path) for n in actual_names):
                    issues.append(
                        AcceptanceIssue("warning", expected_path,
                                        f"Declared directory '{key}' is empty or missing")
                    )
            else:
                if expected_path not in actual_names:
                    issues.append(
                        AcceptanceIssue("error", expected_path,
                                        f"Declared file for '{key}' not found in ZIP")
                    )

        return issues

    @staticmethod
    def _parse_json_artifacts(zf: zipfile.ZipFile) -> list[AcceptanceIssue]:
        """Parse all content JSON files to ensure they're valid."""
        issues: list[AcceptanceIssue] = []
        for entry in PackageAcceptance.REQUIRED_ENTRIES + PackageAcceptance.OPTIONAL_ENTRIES:
            if entry not in zf.namelist():
                continue
            if not entry.endswith(".json"):
                continue
            try:
                json.loads(zf.read(entry))
            except json.JSONDecodeError as e:
                issues.append(
                    AcceptanceIssue("error", entry, f"Invalid JSON: {e}")
                )
        return issues

    @staticmethod
    def _check_graph_entry_point(
        zf: zipfile.ZipFile, manifest: dict[str, Any],
    ) -> list[AcceptanceIssue]:
        """Verify the graph entry_point node exists."""
        issues: list[AcceptanceIssue] = []
        entry = manifest.get("entry_point", "")
        if not entry:
            return issues

        try:
            graph = json.loads(zf.read("content/graph.json"))
        except Exception:
            return issues  # Already caught by _parse_json_artifacts

        node_ids = {n.get("node_id", "") for n in graph.get("nodes", [])}
        if entry not in node_ids:
            issues.append(
                AcceptanceIssue("error", f"content/graph.json",
                                f"Entry point '{entry}' does not exist in graph nodes")
            )

        return issues

    @staticmethod
    def _check_media_references(zf: zipfile.ZipFile) -> list[AcceptanceIssue]:
        """Verify graph-referenced image/MIDI files exist."""
        issues: list[AcceptanceIssue] = []
        try:
            graph = json.loads(zf.read("content/graph.json"))
        except Exception:
            return issues

        all_names = set(zf.namelist())

        for node in graph.get("nodes", []):
            nid = node.get("node_id", "?")
            img_prompt = node.get("image_prompt", "").strip()
            if img_prompt:
                # Check if an image exists for this node
                img_path = f"content/images/{nid}.png"
                if img_path not in all_names:
                    issues.append(
                        AcceptanceIssue("warning", img_path,
                                        f"Node '{nid}' has image_prompt but no image file")
                    )

            music_tone = node.get("music_tone", "").strip()
            if music_tone:
                midi_path = f"content/midi/{nid}.mid"
                if midi_path not in all_names:
                    issues.append(
                        AcceptanceIssue("warning", midi_path,
                                        f"Node '{nid}' has music_tone but no MIDI file")
                    )

        return issues

    @staticmethod
    def _check_undeclared_files(
        manifest: dict[str, Any], actual_names: set[str],
    ) -> list[AcceptanceIssue]:
        """I6: Check for content files not in manifest — error for unknown extensions."""
        issues: list[AcceptanceIssue] = []
        declared = set(manifest.get("files", {}).values())

        for name in actual_names:
            # Skip manifest, save/, and anything explicitly declared
            if name == "manifest.json" or name.startswith("save/"):
                continue
            if name in declared:
                continue
            # Check if it's under a declared directory
            is_under_declared = any(
                name.startswith(d) for d in declared if d.endswith("/")
            )
            if is_under_declared:
                continue

            # Phase 5.6I: Unknown extensions are errors
            ext = Path(name).suffix.lower()
            if ext not in PackageAcceptance.ALLOWED_CONTENT_EXTENSIONS:
                issues.append(
                    AcceptanceIssue("error", name,
                                    f"Undeclared file with unknown extension '{ext}'")
                )
            else:
                issues.append(
                    AcceptanceIssue("warning", name,
                                    "File not declared in manifest inventory")
                )

        return issues
