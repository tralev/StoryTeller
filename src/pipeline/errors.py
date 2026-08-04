"""Structured error taxonomy for StoryTeller Forge.

Phase 5.5F: Distinguishes retryable generation errors from terminal
configuration/resource/persistence defects. Replaces broad except Exception
catches that silently swallowed everything.

Usage:
    raise GenerationError("world_builder", "JSON parsing failed", retryable=True)
    raise ConfigurationError("models.yaml", "Unknown provider: 'ollama'")

    if is_retryable(error):
        retry_prompt(error)
    elif is_terminal(error):
        abort_pipeline(error)
"""

from __future__ import annotations

from typing import Any


class StoryTellerError(Exception):
    """Base class for all StoryTeller errors.

    Attributes:
        code: Stable error code for programmatic handling (e.g., "GEN_001").
        retryable: Whether retrying the same operation might succeed.
        details: Optional dict with structured error context.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "ERR_000",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


# ── Terminal errors (should NOT be retried) ──────────────────────────────


class ConfigurationError(StoryTellerError):
    """Invalid or missing configuration — terminal.

    Examples: unknown model provider, missing required field, invalid YAML.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(
            f"Configuration error in {path}: {message}",
            code="CFG_001",
            retryable=False,
            details={"path": path},
        )


class DependencyError(StoryTellerError):
    """Missing artifact dependency — terminal.

    Examples: story_writer needs context.outputs['bible'] but it's not set.
    """

    def __init__(self, step: str, missing: str) -> None:
        super().__init__(
            f"Step '{step}' requires '{missing}' but it is not available. "
            f"Run the upstream step first.",
            code="DEP_001",
            retryable=False,
            details={"step": step, "missing_dependency": missing},
        )


class ResourceError(StoryTellerError):
    """Resource acquisition failure — terminal.

    Examples: out of disk space, RAM budget exceeded, port in use.
    """

    def __init__(self, resource: str, message: str) -> None:
        super().__init__(
            f"Resource error ({resource}): {message}",
            code="RES_001",
            retryable=False,
            details={"resource": resource},
        )


class PersistenceError(StoryTellerError):
    """File/database write failure — terminal.

    Examples: disk full, permission denied, SQLite corruption.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(
            f"Persistence error at {path}: {message}",
            code="PER_001",
            retryable=False,
            details={"path": path},
        )


class PackageValidationError(StoryTellerError):
    """.story package failed acceptance validation — terminal.

    Generated package is invalid and cannot be repaired by retrying.
    """

    def __init__(self, path: str, issues: list[str]) -> None:
        super().__init__(
            f"Package validation failed for {path}: {len(issues)} issue(s)",
            code="PKG_001",
            retryable=False,
            details={"path": path, "issues": issues},
        )


class FingerprintMismatchError(StoryTellerError):
    """Run fingerprint mismatch on resume — terminal.

    The config or models used for the current run differ from those
    used for the original run. Resuming would produce mixed content.
    Use resume=False to start fresh, or restore the original config.

    Phase 5.6C.
    """

    def __init__(self, stored: str, incoming: str) -> None:
        super().__init__(
            f"Run fingerprint mismatch: cannot resume with different config/models. "
            f"Stored: {stored[:16]}..., Incoming: {incoming[:16]}... "
            f"Use --no-resume to start fresh.",
            code="FP_001",
            retryable=False,
            details={
                "stored_fingerprint": stored,
                "incoming_fingerprint": incoming,
            },
        )


# ── Retryable errors (may succeed on retry) ─────────────────────────────


class GenerationError(StoryTellerError):
    """LLM generation failure — retryable.

    Examples: malformed JSON response, empty output, timeout.
    """

    def __init__(self, step_name: str, message: str) -> None:
        super().__init__(
            f"Generation error in '{step_name}': {message}",
            code="GEN_001",
            retryable=True,
            details={"step": step_name},
        )


class ValidationError(StoryTellerError):
    """Generated content failed validation — retryable.

    The LLM produced structurally invalid output. Retry with
    error feedback in the prompt should fix it.
    """

    def __init__(self, step_name: str, errors: list[str]) -> None:
        super().__init__(
            f"Validation failed for '{step_name}': {len(errors)} error(s)",
            code="VAL_001",
            retryable=True,
            details={"step": step_name, "validation_errors": errors},
        )


class ModelLoadError(StoryTellerError):
    """Failed to load a model — may be retryable.

    Examples: GGUF file temporarily locked, network issue during download.
    Operator intervention may be needed (download model, free RAM).
    """

    def __init__(self, model_name: str, message: str) -> None:
        super().__init__(
            f"Failed to load model '{model_name}': {message}",
            code="MOD_001",
            retryable=True,  # Operator may fix and retry
            details={"model": model_name},
        )


# ── Classification helpers ──────────────────────────────────────────────


def is_retryable(error: BaseException) -> bool:
    """Check if an error is retryable (generation/validation)."""
    if isinstance(error, StoryTellerError):
        return error.retryable
    # Unknown exceptions: treat as terminal (don't retry programming errors)
    return False


def is_terminal(error: BaseException) -> bool:
    """Check if an error is terminal (config/resource/persistence)."""
    return not is_retryable(error)


def error_code(error: BaseException) -> str:
    """Return the stable error code for an exception (Phase 5.6 P4).

    StoryTellerError subclasses carry a stable code (e.g. ``GEN_001``).
    Unknown exceptions get the generic ``ERR_000`` — they are programming
    errors and are never retried.

    Usage:
        code = error_code(exc)          # "GEN_001"
        record = QuarantineRecord(code=code, ...)
    """
    if isinstance(error, StoryTellerError):
        return error.code
    return "ERR_000"
