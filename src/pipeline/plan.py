"""Declarative Pipeline Plan — StepSpec + PipelinePlan.

Phase 5.6H: Replaces hard-coded step ordering in GenerateStory.execute()
with a validated, introspectable plan that drives execution, resume,
progress reporting, and documentation.

Key design decisions:
- StepSpec is a frozen dataclass (immutable, hashable).
- PipelinePlan is an ordered sequence of StepSpec instances.
- Plan validation happens BEFORE any models are loaded.
- The same plan is used for execution, resume, and progress reporting.
- Model lifecycle (load/unload) is derived from model_role transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class StepSpec:
    """Declarative specification of one pipeline step.

    Immutable — once a plan is built, it cannot be mutated.
    """

    id: str
    """Unique step identifier (e.g., 'world_builder', 'image_generator')."""

    output_key: str
    """Canonical artifact key placed in ctx.outputs (e.g., 'bible', 'graph')."""

    requires: tuple[str, ...] = ()
    """Artifact keys this step needs as input (must be produced by prior steps)."""

    model_role: str | None = None
    """Which model type this step needs: 'text', 'image', 'music', or None."""

    validation: str | None = None
    """JSON schema name for deterministic validation (e.g., 'bible', 'graph')."""

    failure_policy: str = "abort"
    """What happens on failure: 'abort' (stop pipeline) or 'quarantine' (skip item)."""

    checkpoint: bool = True
    """Whether to save a checkpoint after this step completes."""

    parallel_per_node: bool = False
    """If True, this step processes graph nodes in parallel (image, music)."""

    description: str = ""
    """Human-readable description for progress reporting and docs."""

    def __post_init__(self) -> None:
        """Validate self-consistency on construction."""
        if not self.id:
            raise ValueError("StepSpec.id must not be empty")
        if not self.output_key:
            raise ValueError("StepSpec.output_key must not be empty")
        if self.model_role is not None and self.model_role not in ("text", "image", "music"):
            raise ValueError(
                f"StepSpec.model_role must be 'text', 'image', 'music', or None, "
                f"got {self.model_role!r}"
            )
        if self.failure_policy not in ("abort", "quarantine"):
            raise ValueError(
                f"StepSpec.failure_policy must be 'abort' or 'quarantine', "
                f"got {self.failure_policy!r}"
            )


# ── Error types ────────────────────────────────────────────────────────


class PlanValidationError(ValueError):
    """Raised when a PipelinePlan fails validation.

    Terminal — the pipeline cannot run with an invalid plan.
    """


# ── PipelinePlan ───────────────────────────────────────────────────────


@dataclass
class PipelinePlan:
    """Ordered, validated sequence of StepSpec instances.

    The single source of truth for pipeline structure.
    Used by GenerateStory, PipelineRunner, progress reporting, and docs.

    Usage:
        plan = PipelinePlan.production_v2()
        plan.validate()  # raises PlanValidationError on first issue

        for spec in plan:
            print(f"{spec.id} → {spec.output_key} [{spec.model_role}]")

        # Iterate by model role (for model lifecycle):
        for role, steps in plan.group_by_model_role():
            print(f"Load {role}, run {len(steps)} steps, unload")
    """

    steps: list[StepSpec] = field(default_factory=list)

    # ── factories ──────────────────────────────────────────────────

    @classmethod
    def production_v2(cls) -> PipelinePlan:
        """Authoritative procedural-first production plan.

        Standalone diagnostic commands may invoke individual services, but all
        product entry points execute this exact dependency chain.
        """
        return cls(steps=[
            StepSpec("physical_world", "world_physical", description="Generate and validate physical world"),
            StepSpec("simulate_world", "world", requires=("world_physical",),
                     description="Simulate civilizations and complete history"),
            StepSpec("world_builder_v2", "bible", requires=("world",), model_role="text",
                     description="Project authoritative world facts into Bible v2"),
            StepSpec("reconcile_world", "reconciliation", requires=("world", "bible"), model_role="text",
                     description="Require strict Bible/world reconciliation"),
            StepSpec("art_direction_v2", "style_bible",
                     requires=("world", "bible", "reconciliation"), model_role="text",
                     description="Derive authoritative art constraints and safely refine descriptions"),
            StepSpec("story_v2", "story",
                     requires=("world", "bible", "reconciliation"), model_role="text",
                     description="Generate and safely enrich the source-linked v2 story"),
            StepSpec("graph_v2", "narrative_project",
                     requires=("world", "bible", "reconciliation", "story"), model_role="text",
                     description="Generate validated graph topology and safely enrich node prose"),
            StepSpec("media_intents_v2", "media_intents", requires=("narrative_project",),
                     model_role="text", description="Safely refine per-node image and music intent"),
            StepSpec("image_media_v2", "images",
                     requires=("narrative_project", "media_intents", "style_bible"),
                     model_role="image",
                     description="Generate and verify mandatory images and thumbnails"),
            StepSpec("local_maps_v2", "local_maps", requires=("world", "narrative_project"),
                     description="Generate and validate every-site local maps"),
            StepSpec("music_media_v2", "midi", requires=("narrative_project", "media_intents"),
                     description="Generate and verify structured scores and MIDI"),
            StepSpec("accept_media_v2", "media", requires=("narrative_project", "images", "midi"),
                     description="Accept only complete matching image and music sets"),
            StepSpec("gm_index_v2", "gm_index",
                     requires=("world", "bible", "narrative_project", "local_maps", "media"),
                     description="Build complete source-covered GM index"),
            StepSpec("package_v2", "package_candidate",
                     requires=("world", "bible", "reconciliation", "style_bible", "narrative_project",
                               "media_intents", "images", "local_maps", "midi", "media", "gm_index"),
                     description="Construct an unpublished frozen story v2 archive"),
            StepSpec("accept_package_v2", "package_acceptance", requires=("package_candidate",),
                     description="Reopen and accept the staged archive as a consumer"),
            StepSpec("packager", "packager", requires=("package_candidate", "package_acceptance"),
                     description="Atomically publish only the accepted archive"),
        ])

    # ── iteration ──────────────────────────────────────────────────

    def __iter__(self) -> Iterator[StepSpec]:
        return iter(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    def __getitem__(self, index: int) -> StepSpec:
        return self.steps[index]

    def step_ids(self) -> list[str]:
        """Return ordered list of step IDs."""
        return [s.id for s in self.steps]

    def output_keys(self) -> list[str]:
        """Return ordered list of output keys."""
        return [s.output_key for s in self.steps]

    def model_roles(self) -> list[str | None]:
        """Return ordered list of model roles (for lifecycle transitions)."""
        return [s.model_role for s in self.steps]

    def group_by_model_role(self) -> list[tuple[str | None, list[StepSpec]]]:
        """Group steps by contiguous model_role segments.

        Used to determine model load/unload boundaries.
        Consecutive steps with the same model_role share one resource_scope.

        Returns:
            List of (model_role, steps) tuples.
        """
        if not self.steps:
            return []

        groups: list[tuple[str | None, list[StepSpec]]] = []
        current_role = self.steps[0].model_role
        current_group: list[StepSpec] = []

        for spec in self.steps:
            if spec.model_role == current_role:
                current_group.append(spec)
            else:
                groups.append((current_role, current_group))
                current_role = spec.model_role
                current_group = [spec]

        groups.append((current_role, current_group))
        return groups

    # ── lookup ─────────────────────────────────────────────────────

    def get(self, step_id: str) -> StepSpec:
        """Look up a step spec by ID.

        Raises:
            KeyError: if step_id not found.
        """
        for spec in self.steps:
            if spec.id == step_id:
                return spec
        raise KeyError(step_id)

    def get_by_output(self, output_key: str) -> StepSpec:
        """Look up a step spec by output key.

        Raises:
            KeyError: if output_key not found.
        """
        for spec in self.steps:
            if spec.output_key == output_key:
                return spec
        raise KeyError(output_key)

    def index_of(self, step_id: str) -> int:
        """Return the 0-based index of a step in the plan.

        Raises:
            KeyError: if step_id not found.
        """
        for i, spec in enumerate(self.steps):
            if spec.id == step_id:
                return i
        raise KeyError(step_id)

    # ── validation ─────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the plan for correctness.

        Checks:
          1. No duplicate step IDs.
          2. No duplicate output keys.
          3. Every 'requires' key is produced by a prior step.
          4. Dependency graph is acyclic (implicit from ordered list).
          5. Every step has a non-empty id and output_key (enforced by StepSpec).

        Raises:
            PlanValidationError: on the first violation found.
        """
        # 1. No duplicate step IDs
        seen_ids: set[str] = set()
        for spec in self.steps:
            if spec.id in seen_ids:
                raise PlanValidationError(
                    f"Duplicate step ID: {spec.id!r}"
                )
            seen_ids.add(spec.id)

        # 2. No duplicate output keys
        seen_outputs: set[str] = set()
        for spec in self.steps:
            if spec.output_key in seen_outputs:
                raise PlanValidationError(
                    f"Duplicate output key: {spec.output_key!r} "
                    f"(steps must produce unique artifacts)"
                )
            seen_outputs.add(spec.output_key)

        # 3. No step requires its own output (self-loop) — check BEFORE
        #    dependency resolution, since a self-loop would also show
        #    as a missing dependency.
        for spec in self.steps:
            if spec.output_key in spec.requires:
                raise PlanValidationError(
                    f"Step {spec.id!r} requires its own output "
                    f"{spec.output_key!r} (self-loop)"
                )

        # 4. Every required key is produced by a prior step
        available: set[str] = set()
        for spec in self.steps:
            for req in spec.requires:
                if req not in available:
                    raise PlanValidationError(
                        f"Step {spec.id!r} requires {req!r}, but no prior "
                        f"step produces it. Available: {sorted(available)}"
                    )
            available.add(spec.output_key)

        # 5. A model role may occupy only one contiguous resource segment.
        # Re-entering a role would force avoidable unload/reload churn and makes
        # RAM planning ambiguous.
        closed_roles: set[str] = set()
        previous_role: str | None = None
        for spec in self.steps:
            role = spec.model_role
            if role != previous_role:
                if previous_role is not None:
                    closed_roles.add(previous_role)
                if role is not None and role in closed_roles:
                    raise PlanValidationError(
                        f"Model role {role!r} appears in multiple segments"
                    )
                previous_role = role

        # 6. Quarantine is valid only for independent item batches. Storage,
        # dependency and whole-step failures are always terminal.
        for spec in self.steps:
            if spec.failure_policy == "quarantine" and not spec.parallel_per_node:
                raise PlanValidationError(
                    f"Step {spec.id!r} uses quarantine but is not an item batch"
                )

        # 7. A dependency producer must be checkpointed when its consumer is;
        # otherwise resume can restore a consumer without its input.
        by_output = {spec.output_key: spec for spec in self.steps}
        for spec in self.steps:
            if not spec.checkpoint:
                continue
            for requirement in spec.requires:
                producer = by_output[requirement]
                if not producer.checkpoint:
                    raise PlanValidationError(
                        f"Checkpointed step {spec.id!r} depends on "
                        f"non-checkpointed producer {producer.id!r}"
                    )

    # ── introspection ──────────────────────────────────────────────

    def phase_number(self, step_id: str) -> int:
        """Return the 1-based phase number for a step.

        Phases are 1-indexed (matching the roadmap).
        """
        return self.index_of(step_id) + 1

    def summary(self) -> str:
        """Return a human-readable summary of the plan."""
        lines: list[str] = [
            f"PipelinePlan: {len(self.steps)} steps",
            "",
        ]
        for i, spec in enumerate(self.steps):
            phase = i + 1
            deps = ", ".join(spec.requires) if spec.requires else "none"
            role = spec.model_role or "none"
            lines.append(
                f"  {phase}. [{role:5s}] {spec.id:20s} → {spec.output_key:15s} "
                f"(requires: {deps})"
            )
        return "\n".join(lines)
