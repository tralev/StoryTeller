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
    Used by GenerateStory, Orchestrator, progress reporting, and docs.

    Usage:
        plan = PipelinePlan.standard()
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
    def standard(cls) -> PipelinePlan:
        """Build the standard StoryTeller pipeline plan.

        Phase ordering:
          Phase 1-2 (text model):
            world_builder → bible
            art_director  → style_bible
          Phase 3 (text model):
            story_writer  → story
          Phase 4 (text model):
            game_designer → graph
          Phase 5a (text model, parallel per-node):
            music_generator → midi/{node_id}
          Phase 5b (image model, parallel per-node):
            image_generator → images/{node_id}
          Phase 6 (no model):
            indexer → gm_index
            packager → packager
        """
        return cls(steps=[
            StepSpec(
                id="world_builder",
                output_key="bible",
                model_role="text",
                validation="bible",
                failure_policy="abort",
                description="Generate World Bible from tone + title",
            ),
            StepSpec(
                id="art_director",
                output_key="style_bible",
                requires=("bible",),
                model_role="text",
                validation="style_bible",
                failure_policy="abort",
                description="Generate art style constraints from World Bible",
            ),
            StepSpec(
                id="story_writer",
                output_key="story",
                requires=("bible",),
                model_role="text",
                validation="story",
                failure_policy="abort",
                description="Generate 3-chapter linear story from Bible",
            ),
            StepSpec(
                id="game_designer",
                output_key="graph",
                requires=("bible", "story"),
                model_role="text",
                validation="graph",
                failure_policy="abort",
                description="Convert story into branching CYOA graph",
            ),
            StepSpec(
                id="music_generator",
                output_key="midi",
                requires=("graph",),
                model_role="text",
                failure_policy="quarantine",
                parallel_per_node=True,
                description="Generate MIDI tracks for each graph node",
            ),
            StepSpec(
                id="image_generator",
                output_key="images",
                requires=("graph", "style_bible"),
                model_role="image",
                failure_policy="quarantine",
                parallel_per_node=True,
                description="Generate illustrations for each graph node",
            ),
            StepSpec(
                id="indexer",
                output_key="gm_index",
                requires=("bible", "graph"),
                validation="gm_index",
                description="Build Game Master retrieval index",
            ),
            StepSpec(
                id="packager",
                output_key="packager",
                requires=("bible", "story", "graph", "images", "midi", "gm_index", "style_bible"),
                description="Package all artifacts into deterministic .story ZIP",
            ),
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
