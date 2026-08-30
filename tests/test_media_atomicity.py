import json

import pytest

from src.narrative.models import GraphV2
from src.narrative.pipeline import MediaProducer, _generate_media, _graph_from_dict


@pytest.mark.asyncio
async def test_crash_after_publish_creates_no_checkpoint_and_safe_resume(tmp_path, phase5_project):
    _, _, phase5 = phase5_project
    node = _graph_from_dict(json.loads((phase5 / "graph.json").read_text())).nodes[0]

    def crash(node_id, kind):
        if kind == "image":
            raise RuntimeError("crash window")

    with pytest.raises(RuntimeError):
        await MediaProducer(tmp_path, after_publish=crash).produce(node)
    assert not (tmp_path / "checkpoints" / "media" / f"{node.node_id}.json").exists()
    media = await MediaProducer(tmp_path).produce(node)
    assert (tmp_path / media.image.path).is_file() and (tmp_path / media.midi.path).is_file()
    assert media.image.sha256 in media.thumbnail.dependency_ids
    assert media.score.sha256 in media.midi.dependency_ids


@pytest.mark.asyncio
async def test_corrupt_resumed_file_is_regenerated(tmp_path, phase5_project):
    _, _, phase5 = phase5_project
    node = _graph_from_dict(json.loads((phase5 / "graph.json").read_text())).nodes[0]
    producer = MediaProducer(tmp_path)
    media = await producer.produce(node)
    checkpoint = tmp_path / "checkpoints" / "media" / f"{node.node_id}.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps(__import__("dataclasses").asdict(media)))
    (tmp_path / media.image.path).write_bytes(b"corrupt")
    repaired = await producer.produce(node)
    assert repaired.image.sha256 == media.image.sha256


@pytest.mark.asyncio
async def test_worker_count_does_not_change_canonical_media(tmp_path, phase5_project):
    _, _, phase5 = phase5_project
    full = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    graph = GraphV2(full.schema_version, full.starting_node, full.flags, full.nodes[:2])
    one = await _generate_media(tmp_path / "one", graph, workers=1)
    many = await _generate_media(tmp_path / "many", graph, workers=4)
    assert {
        key: (value.image.sha256, value.thumbnail.sha256, value.score.sha256, value.midi.sha256)
        for key, value in one.items()
    } == {
        key: (value.image.sha256, value.thumbnail.sha256, value.score.sha256, value.midi.sha256)
        for key, value in many.items()
    }
