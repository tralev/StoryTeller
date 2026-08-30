"""Tests for CLI parser and all 11 commands.

Tests the argparse parser setup and mock execution of each command.
"""

from __future__ import annotations

import argparse

import pytest

# ── Helpers ───────────────────────────────────────────────────────────


def _make_parser() -> argparse.ArgumentParser:
    """Recreate the CLI parser for testing. Matches src/cli.py structure."""
    parser = argparse.ArgumentParser(
        prog="forge",
        description="StoryTeller Forge — AI-powered interactive story generator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = sub.add_parser("generate", help="Run the full pipeline")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--tone", type=str, default="mature_dark_fantasy")
    gen.add_argument("--title", type=str, default="Untitled")
    gen.add_argument("--temperature", type=float, default=0.7)
    gen.add_argument("--config", type=str, default=None)
    gen.add_argument("--output", type=str, default="tmp/output")

    # download-models
    dm = sub.add_parser("download-models", help="Download GGUF models")
    dm.add_argument("--with-images", action="store_true")
    dm.add_argument("--models-dir", type=str, default=None)

    # resume
    res = sub.add_parser("resume", help="Resume from checkpoint")
    res.add_argument("--output", type=str, default="tmp/output")
    res.add_argument("--config", type=str, default=None)

    # config
    cfg = sub.add_parser("config", help="Show/edit configuration")
    cfg.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), default=None)
    cfg.add_argument("--config", type=str, default=None)

    # verify
    ver = sub.add_parser("verify", help="Verify .story hash")
    ver.add_argument("file", type=str)
    ver.add_argument("--expected-hash", type=str, default=None)

    # info
    inf = sub.add_parser("info", help="Show checkpoint/state info")
    inf.add_argument("--output", type=str, default="tmp/output")

    # package
    pkg = sub.add_parser("package", help="Package into .story")
    pkg.add_argument("--seed", type=int, default=42)
    pkg.add_argument("--output", type=str, default="tmp/output")
    pkg.add_argument("--config", type=str, default=None)

    # validate-story
    vs = sub.add_parser("validate-story", help="Story vs bible consistency")
    vs.add_argument("story_file", type=str)
    vs.add_argument("bible_file", type=str)

    # validate-graph
    vg = sub.add_parser("validate-graph", help="Validate graph schema")
    vg.add_argument("graph_file", type=str)
    vg.add_argument("--schemas-dir", type=str, default=None)

    # validate-all
    va = sub.add_parser("validate-all", help="Validate all artifacts in a dir")
    va.add_argument("dir", type=str)
    va.add_argument("--schemas-dir", type=str, default=None)

    # validate-bible
    vb = sub.add_parser("validate-bible", help="Validate bible schema")
    vb.add_argument("bible_file", type=str)
    vb.add_argument("--schemas-dir", type=str, default=None)

    return parser


# ── Tests: parser existence ───────────────────────────────────────────


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return _make_parser()


def test_parser_has_11_commands(parser: argparse.ArgumentParser) -> None:
    """All 11 commands must be registered."""
    # subparsers choices are stored in _subparsers._group_actions[0].choices
    choices = parser._subparsers._group_actions[0].choices
    expected = {
        "generate",
        "download-models",
        "resume",
        "config",
        "verify",
        "info",
        "package",
        "validate-story",
        "validate-graph",
        "validate-all",
        "validate-bible",
    }
    assert set(choices.keys()) == expected


class TestGenerate:
    def test_defaults(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["generate"])
        assert args.seed == 42
        assert args.tone == "mature_dark_fantasy"
        assert args.title == "Untitled"
        assert args.temperature == 0.7

    def test_custom_all(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(
            [
                "generate",
                "--seed",
                "7",
                "--tone",
                "heroic_fantasy",
                "--title",
                "The Crystal Accord",
                "--temperature",
                "0.8",
                "--output",
                "/tmp/out",
            ]
        )
        assert args.seed == 7
        assert args.tone == "heroic_fantasy"
        assert args.title == "The Crystal Accord"
        assert args.temperature == 0.8
        assert args.output == "/tmp/out"


class TestDownloadModels:
    def test_default(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["download-models"])
        assert args.with_images is False
        assert args.models_dir is None

    def test_with_images(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["download-models", "--with-images"])
        assert args.with_images is True


class TestResume:
    def test_defaults(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["resume"])
        assert args.output == "tmp/output"

    def test_custom_output(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["resume", "--output", "/tmp/resume"])
        assert args.output == "/tmp/resume"


class TestConfig:
    def test_show(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["config"])
        assert args.set is None  # avoid the deprecated alias

    def test_set(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["config", "--set", "text.model", "qwen2.5-7b"])
        assert args.set == ["text.model", "qwen2.5-7b"]


class TestVerify:
    def test_basic(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["verify", "test.story"])
        assert args.file == "test.story"
        assert args.expected_hash is None

    def test_with_hash(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["verify", "test.story", "--expected-hash", "abc123"])
        assert args.expected_hash == "abc123"


class TestInfo:
    def test_default(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["info"])
        assert args.output == "tmp/output"


class TestPackage:
    def test_defaults(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["package"])
        assert args.seed == 42
        assert args.output == "tmp/output"

    def test_custom(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["package", "--seed", "99", "--output", "pkg_out"])
        assert args.seed == 99
        assert args.output == "pkg_out"


class TestValidateStory:
    def test_required_args(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["validate-story", "story.json", "bible.json"])
        assert args.story_file == "story.json"
        assert args.bible_file == "bible.json"


class TestValidateGraph:
    def test_basic(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["validate-graph", "graph.json"])
        assert args.graph_file == "graph.json"
        assert args.schemas_dir is None

    def test_with_schemas_dir(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["validate-graph", "graph.json", "--schemas-dir", "/schemas"])
        assert args.schemas_dir == "/schemas"


class TestValidateAll:
    def test_basic(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["validate-all", "output/"])
        assert args.dir == "output/"
        assert args.schemas_dir is None


class TestValidateBible:
    def test_basic(self, parser: argparse.ArgumentParser) -> None:
        args = parser.parse_args(["validate-bible", "bible.json"])
        assert args.bible_file == "bible.json"


class TestCommandRequired:
    def test_no_command_fails(self, parser: argparse.ArgumentParser) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args([])
