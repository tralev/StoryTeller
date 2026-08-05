from __future__ import annotations

import pytest

from src.pipeline.plan import PipelinePlan, PlanValidationError, StepSpec


def test_reentered_model_role_is_rejected() -> None:
    plan = PipelinePlan([
        StepSpec("a", "a", model_role="text"),
        StepSpec("b", "b"),
        StepSpec("c", "c", model_role="text"),
    ])
    with pytest.raises(PlanValidationError, match="multiple segments"):
        plan.validate()


def test_quarantine_requires_independent_item_batch() -> None:
    plan = PipelinePlan([StepSpec("a", "a", failure_policy="quarantine")])
    with pytest.raises(PlanValidationError, match="not an item batch"):
        plan.validate()


def test_checkpoint_dependency_must_be_checkpointed() -> None:
    plan = PipelinePlan([
        StepSpec("a", "a", checkpoint=False),
        StepSpec("b", "b", requires=("a",)),
    ])
    with pytest.raises(PlanValidationError, match="non-checkpointed"):
        plan.validate()
