from src.storage.artifact_repository import ArtifactRepository
from src.storage.checkpoint_v2 import V2CheckpointStore, reusable


def test_resume_verifies_bytes_dependencies_and_producer(tmp_path) -> None:
    repo = ArtifactRepository(tmp_path / "artifacts")
    ref = repo.put_bytes(
        "story",
        "narrative/story.json",
        b"{}",
        depends_on=("world_a",),
        producer_fingerprint="producer",
    )
    store = V2CheckpointStore(tmp_path / "checkpoints.db")
    store.begin_run("run", "fingerprint")
    store.save(
        "run",
        "phase",
        "story",
        "complete",
        artifact=ref,
        dependencies=("world_a",),
        producer_fingerprint="producer",
    )
    checkpoint = store.load("run", "phase", "story")
    assert checkpoint is not None and reusable(checkpoint, repo, ("world_a",), "producer")
    (tmp_path / "artifacts/narrative/story.json").write_bytes(b"tampered")
    assert not reusable(checkpoint, repo, ("world_a",), "producer")
