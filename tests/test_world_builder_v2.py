import json
import shutil
from dataclasses import replace

import pytest

from src.world.builder import WorldBuilderV2, deterministic_candidate
from src.world.views import WorldView


def test_builder_retries_only_candidate_and_keeps_world_immutable(tmp_path, phase4_world):
    view = WorldView(phase4_world)
    before = view.file_hashes
    feedback_seen = []

    def factory(world, title, feedback, attempt):
        feedback_seen.append(feedback)
        candidate = deterministic_candidate(world, title, feedback, attempt)
        return replace(candidate, present_year=-1) if attempt == 1 else candidate

    bible, report = WorldBuilderV2(candidate_factory=factory).build(phase4_world, "Ash", tmp_path)
    assert report.accepted and bible.present_year == 20
    assert "WORLD-PRESENT-YEAR" in feedback_seen[1]
    assert WorldView(phase4_world).file_hashes == before
    assert (tmp_path / "checkpoints" / "bible_candidate_01.json").is_file()
    assert json.loads((tmp_path / "reconciliation.json").read_text())["accepted"] is True


def test_optional_critic_failure_does_not_block_valid_candidate(tmp_path, phase4_world):
    class BrokenCritic:
        def critique(self, bible, projections):
            raise RuntimeError("offline")

    _, report = WorldBuilderV2(critic=BrokenCritic()).build(phase4_world, "Ash", tmp_path)
    assert report.accepted and report.critic_status == "failed_optional"


def test_builder_rejects_injected_authoritative_artifact(tmp_path, phase4_world):
    copied_world = tmp_path / "world"
    shutil.copytree(phase4_world, copied_world)

    def injecting_factory(world, title, feedback, attempt):
        (copied_world / "artifacts" / "injected.json").write_text("{}")
        return deterministic_candidate(world, title, feedback, attempt)

    with pytest.raises(ValueError, match="WORLD-MUTATED: authoritative artifact inventory"):
        WorldBuilderV2(candidate_factory=injecting_factory).build(
            copied_world,
            "Ash",
            tmp_path / "output",
        )
