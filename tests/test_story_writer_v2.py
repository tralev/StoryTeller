import json


def test_story_uses_world_bible_and_reconciliation_dependencies(phase5_project):
    _, phase4, phase5 = phase5_project
    story = json.loads((phase5 / "story.json").read_text())
    assert story["schema_version"] == "2-pre1"
    assert story["world_artifact_ids"]
    assert all(scene["authoritative_refs"] and scene["opportunity_id"] for scene in story["scenes"])
    assert story["bible_hash"] and story["reconciliation_hash"]
    outline = json.loads((phase5 / "checkpoints" / "story" / "outline.json").read_text())
    assert set(outline["scene_ids"]) == {scene["scene_id"] for scene in story["scenes"]}
    assert outline["dependency_ids"] == story["world_artifact_ids"]
    assert (phase4 / "reconciliation.json").is_file()
