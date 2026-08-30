"""Production-v2 interruption, resume, and transitive invalidation matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.generate_story import GenerateStory
from src.job_queue import PipelineContext
from src.pipeline.plan import PipelinePlan
from src.storage.checkpoint import CheckpointStore
from src.storage.provenance import artifact_id


def _seed_checkpoints(
    root: Path, completed: int
) -> tuple[CheckpointStore, dict[str, dict[str, object]]]:
    plan = PipelinePlan.production_v2()
    store = CheckpointStore(root / "checkpoint.db")
    outputs: dict[str, dict[str, object]] = {}
    for phase, spec in enumerate(plan, start=1):
        if phase > completed:
            break
        artifact = root / "artifacts" / f"{phase:02d}-{spec.id}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f'{{"phase":{phase},"step":"{spec.id}"}}')
        output: dict[str, object] = {
            "path": str(artifact),
            "step": spec.id,
            "phase": phase,
        }
        dependencies = {
            key: artifact_id(key, outputs[key]) for key in spec.requires if key in outputs
        }
        store.save(
            spec.id,
            phase=phase,
            seed=17,
            output=output,
            output_key=spec.output_key,
            artifact_id=artifact_id(spec.output_key, output),
            run_fingerprint="matrix-run",
            depends_on=dependencies,
            file_hashes=GenerateStory._checkpoint_file_hashes(output),
            producer_fingerprint=GenerateStory._checkpoint_producer_fingerprint(
                spec.id,
                "matrix-run",
            ),
        )
        outputs[spec.output_key] = output
    return store, outputs


@pytest.mark.parametrize("completed", range(17))
def test_resume_after_every_production_stage_reuses_prefix_once(
    tmp_path: Path,
    completed: int,
) -> None:
    """A stop at each boundary reuses the prefix and schedules the suffix once."""
    plan = PipelinePlan.production_v2()
    store, expected = _seed_checkpoints(tmp_path, completed)
    context = PipelineContext(run_id="matrix", seed=17)

    GenerateStory._restore_checkpoints(context, store)
    highest = store.get_highest_completed_phase()
    scheduled = [
        spec.id
        for spec in plan
        if spec.id == "packager" or not GenerateStory._should_skip(spec.id, highest, store)
    ]

    assert {key: context.outputs[key] for key in context.outputs} == expected
    expected_schedule = plan.step_ids()[completed:] if completed < len(plan) else ["packager"]
    assert scheduled == expected_schedule
    assert len(scheduled) == len(set(scheduled))


def _dependent_steps(plan: PipelinePlan, changed_output: str) -> set[str]:
    invalid_outputs = {changed_output}
    invalid_steps: set[str] = set()
    changed = True
    while changed:
        changed = False
        for spec in plan:
            if spec.id in invalid_steps or not invalid_outputs.intersection(spec.requires):
                continue
            invalid_steps.add(spec.id)
            invalid_outputs.add(spec.output_key)
            changed = True
    return invalid_steps


@pytest.mark.parametrize("tampered_phase", range(1, 17))
def test_tampering_each_stage_invalidates_exact_dependency_closure(
    tmp_path: Path,
    tampered_phase: int,
) -> None:
    plan = PipelinePlan.production_v2()
    store, outputs = _seed_checkpoints(tmp_path, len(plan))
    tampered_spec = plan[tampered_phase - 1]
    Path(str(outputs[tampered_spec.output_key]["path"])).write_text("tampered")
    context = PipelineContext(run_id="matrix", seed=17)

    GenerateStory._restore_checkpoints(context, store)

    invalid = {tampered_spec.id} | _dependent_steps(plan, tampered_spec.output_key)
    actual_invalid = {spec.id for spec in plan if store.load(spec.id) is None}
    assert actual_invalid == invalid
    assert tampered_spec.output_key not in context.outputs
