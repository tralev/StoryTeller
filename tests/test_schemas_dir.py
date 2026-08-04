"""Tests for _resolve_schemas_dir — PyInstaller bundle (sys._MEIPASS) resolution.

Covers both implementations:
  - src.cli._resolve_schemas_dir(schemas_dir)   (CLI validate-* commands)
  - GenerateStory._resolve_schemas_dir()        (application service)

The _MEIPASS branch matters for standalone (frozen) binaries: schemas are
extracted to sys._MEIPASS/schemas, which is not CWD-relative.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from src.cli import _resolve_schemas_dir as cli_resolve_schemas_dir
from src.application.generate_story import GenerateStory


@pytest.fixture
def no_schemas_cwd(tmp_path: Path, monkeypatch: Any) -> Path:
    """Chdir into a directory that has no schemas/ so CWD fallback can't hit."""
    cwd = tmp_path / "empty_cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)
    return cwd


def mock_meipass(tmp_path: Path, monkeypatch: Any) -> Path:
    """Simulate a PyInstaller bundle: sys._MEIPASS points at a dir with schemas/."""
    meipass = tmp_path / "_MEIPASS"
    (meipass / "schemas").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    return meipass


class TestCliResolveSchemasDir:
    """src.cli._resolve_schemas_dir — bundled resolution."""

    def test_meipass_bundle_wins(
        self, tmp_path: Path, monkeypatch: Any, no_schemas_cwd: Path
    ) -> None:
        meipass = mock_meipass(tmp_path, monkeypatch)
        result = cli_resolve_schemas_dir("nonexistent/schemas")
        assert result == meipass / "schemas"

    def test_explicit_dir_wins_over_meipass(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        explicit = tmp_path / "explicit_schemas"
        explicit.mkdir(parents=True, exist_ok=True)
        mock_meipass(tmp_path, monkeypatch)
        result = cli_resolve_schemas_dir(str(explicit))
        assert result == explicit

    def test_cwd_schemas_wins_over_meipass(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        cwd_with_schemas = tmp_path / "cwd_with_schemas"
        (cwd_with_schemas / "schemas").mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(cwd_with_schemas)
        mock_meipass(tmp_path, monkeypatch)
        result = cli_resolve_schemas_dir("nonexistent/schemas")
        # CWD branch returns the relative "schemas" path
        assert result == Path("schemas")
        assert result.resolve() == cwd_with_schemas / "schemas"

    def test_meipass_without_schemas_falls_back_to_project_root(
        self, tmp_path: Path, monkeypatch: Any, no_schemas_cwd: Path
    ) -> None:
        # Bundle exists but has no schemas/ → fall through to project root
        meipass = tmp_path / "_MEIPASS"
        meipass.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
        result = cli_resolve_schemas_dir("nonexistent/schemas")
        expected = Path(__file__).resolve().parent.parent / "schemas"
        assert result == expected

    def test_exits_when_nowhere_has_schemas(
        self, tmp_path: Path, monkeypatch: Any, no_schemas_cwd: Path
    ) -> None:
        # No explicit dir, no CWD schemas, no _MEIPASS, and a bogus __file__
        # so the project-root fallback also misses → sys.exit(1).
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(
            "src.cli.__file__",
            str(tmp_path / "fake_cli.py"),
        )
        with pytest.raises(SystemExit) as exc_info:
            cli_resolve_schemas_dir("nonexistent/schemas")
        assert exc_info.value.code == 1


class TestGenerateStoryResolveSchemasDir:
    """GenerateStory._resolve_schemas_dir — bundled resolution."""

    def test_env_var_wins(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        env_dir = tmp_path / "env_schemas"
        env_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", str(env_dir))
        result = GenerateStory._resolve_schemas_dir()
        assert result == str(env_dir)

    def test_meipass_bundle_used(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("STORYTELLER_SCHEMAS_DIR", raising=False)
        meipass = mock_meipass(tmp_path, monkeypatch)
        result = GenerateStory._resolve_schemas_dir()
        assert result == str(meipass / "schemas")

    def test_project_root_fallback(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("STORYTELLER_SCHEMAS_DIR", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        result = GenerateStory._resolve_schemas_dir()
        # tests/ → project root is parent.parent of this file
        expected = str(Path(__file__).resolve().parent.parent / "schemas")
        assert result == expected
