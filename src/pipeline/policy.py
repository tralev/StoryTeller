"""ExecutionPolicy — immutable config-driven policy for pipeline behavior.

Phase 5.6G: Replaces scattered hardcoded constants (MAX_RETRIES=3,
FailurePolicy=ABORT) with a single immutable dataclass sourced from
PipelineConfig. Passed to PipelineStep, BatchScheduler, and Orchestrator
so all components share the same policy definition.

Usage:
    from src.config import AppConfig
    from src.pipeline.policy import ExecutionPolicy

    config = AppConfig.from_yaml("config/models.yaml")
    policy = ExecutionPolicy.from_config(config.pipeline)
    step = WorldBuilder(generator, policy=policy, ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..job_queue import FailurePolicy


@dataclass(frozen=True)
class ExecutionPolicy:
    """Immutable policy governing retries, checkpoints, and failure behavior.

    All fields are frozen — policy is computed once from config and never
    mutated at runtime. This ensures every component sees the same policy.

    Attributes:
        max_retries: Number of retry attempts after first failure (default 3).
        checkpoint_interval: Save checkpoint every N phases (default 1 = every phase).
        failure_policy: ABORT (stop on failure) or QUARANTINE (skip failed item).
        model_unload_threshold: Fraction of RAM budget that triggers auto-unload (0.9 = 90%).
    """

    max_retries: int = 3
    checkpoint_interval: int = 1
    failure_policy: FailurePolicy = FailurePolicy.QUARANTINE
    model_unload_threshold: float = 0.9

    @classmethod
    def from_config(cls, pipeline_config: Any) -> ExecutionPolicy:
        """Build ExecutionPolicy from PipelineConfig.

        Args:
            pipeline_config: PipelineConfig dataclass from AppConfig.

        Returns:
            Immutable ExecutionPolicy with validated fields.
        """
        fp_str = getattr(pipeline_config, "failure_policy", "quarantine")
        fp = _parse_failure_policy(fp_str)

        return cls(
            max_retries=max(0, getattr(pipeline_config, "max_retries", 3)),
            checkpoint_interval=max(1, getattr(pipeline_config, "checkpoint_interval", 1)),
            failure_policy=fp,
            model_unload_threshold=float(
                getattr(pipeline_config, "model_unload_threshold", 0.9)
            ),
        )

    @classmethod
    def default(cls) -> ExecutionPolicy:
        """Return the default policy (used when no config is available)."""
        return cls()

    def total_attempts(self) -> int:
        """Total number of attempts including the first try."""
        return self.max_retries + 1


def _parse_failure_policy(value: str) -> FailurePolicy:
    """Parse failure_policy string to FailurePolicy enum."""
    value = value.strip().upper()
    if value == "ABORT":
        return FailurePolicy.ABORT
    if value == "QUARANTINE":
        return FailurePolicy.QUARANTINE
    # Default
    return FailurePolicy.QUARANTINE
