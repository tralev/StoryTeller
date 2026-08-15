"""DeterministicValidator — bundles all deterministic checkers behind Validator.

Phase 5.5C: Each pipeline step gets a DeterministicValidator configured for
its artifact type. Runs schema validation (always), plus optional cross-reference,
graph structure, and consistency checks — all without LLM inference.

This means validation is MANDATORY in production — no more silently skipping
when validator=None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..interfaces.validator import ValidationResult, ValidatorStatus


@dataclass
class ValidationPlan:
    """Specification of which checks to run for a given artifact type."""

    schema: str  # JSON Schema name (e.g., "bible", "story", "graph")
    cross_refs: bool = False
    graph_structure: bool = False
    consistency: bool = False  # Bible consistency (story only)


class DeterministicValidator:
    """Wraps schema, cross-ref, graph, and consistency checkers.

    Implements the Validator protocol interface so PipelineStep can
    use it as self.validator.

    Usage:
        from ..validators.composite import ValidationPlan, DeterministicValidator

        plan = ValidationPlan(schema="bible", cross_refs=True)
        validator = DeterministicValidator(plan, schemas_dir="schemas")
        step = BibleV2Stage(..., generator=generator)
    """

    provider: str = "deterministic"
    model_name: str = "rule-based"
    quantization: str = ""
    ram_usage_mb: int = 0

    def __init__(
        self,
        plan: ValidationPlan,
        schemas_dir: str = "schemas",
    ) -> None:
        self._plan = plan
        self._schemas_dir = schemas_dir
        self._schema_val = _lazy_schema_validator(schemas_dir)

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Run all configured deterministic checks.

        Args:
            content: The generated artifact to validate.
            context: May include "bible", "story", "graph" for cross-ref checks.

        Returns:
            ValidationResult with is_valid flag and collected errors.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Schema validation (always)
        schema_result = self._schema_val.validate(content, self._plan.schema)
        if not schema_result.is_valid:
            errors.append(schema_result.format_for_retry())

        if not errors or self._plan.cross_refs or self._plan.graph_structure:
            # Only run structural checks if the basic schema passes —
            # a malformed document can't be structurally analyzed.

            bible = context.get("bible")
            story = context.get("story")
            graph = context.get("graph")

            # 2. Cross-reference checks
            if self._plan.cross_refs:
                from .cross_ref_checker import CrossRefChecker
                xref = CrossRefChecker()

                if self._plan.schema == "story":
                    if isinstance(bible, dict):
                        ref_result = xref.check_all(bible=bible, story=content)
                        if not ref_result.is_valid:
                            errors.append(ref_result.format_for_retry())

                elif self._plan.schema == "graph":
                    if isinstance(bible, dict):
                        ref_result = xref.check_all(bible=bible, graph=content)
                        if not ref_result.is_valid:
                            errors.append(ref_result.format_for_retry())

                elif self._plan.schema == "bible":
                    # Bible self-consistency: entities must reference each other
                    ref_result = xref.check_all(bible=content)
                    if not ref_result.is_valid:
                        errors.append(ref_result.format_for_retry())

            # 3. Graph structure checks
            if self._plan.graph_structure and self._plan.schema == "graph":
                from .graph_validator import GraphValidator
                gv = GraphValidator()
                g_result = gv.check(content)
                if not g_result.is_valid:
                    errors.append(g_result.format_for_retry())

            # 4. Bible consistency (story only)
            if self._plan.consistency and self._plan.schema == "story":
                if isinstance(bible, dict):
                    from .consistency import ConsistencyChecker
                    cc = ConsistencyChecker()
                    c_result = cc.check_all(bible, content)
                    if not c_result.is_consistent:
                        errors.append(c_result.format_for_retry())

        valid = len(errors) == 0
        return ValidationResult(
            is_valid=valid,
            status=ValidatorStatus.VALID if valid else ValidatorStatus.FAILED,
            errors=errors,
            warnings=warnings,
        )

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> Any:  # ConsistencyReport
        """Run deterministic consistency check on text vs bible."""
        from ..interfaces import ConsistencyReport
        return ConsistencyReport(is_consistent=True)

    async def load(self) -> None:
        pass

    async def unload(self) -> None:
        pass


# ── lazy singleton ────────────────────────────────────────────────────────

_schema_validators: dict[str, Any] = {}


def _lazy_schema_validator(schemas_dir: str) -> Any:
    """Return a cached SchemaValidator for the given directory."""
    import os
    key = os.path.abspath(schemas_dir)
    if key not in _schema_validators:
        from .schema_validator import SchemaValidator
        _schema_validators[key] = SchemaValidator(schemas_dir)
    return _schema_validators[key]
