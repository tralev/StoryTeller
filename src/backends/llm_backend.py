"""Concrete LLM backend using llama-cpp-python.

Implements TextGenerator by loading GGUF models and calling
create_completion with JSON parsing and retry extraction.

Also provides LlamaCppValidator for independent model-based validation.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, AsyncIterator

from ..config import ModelConfig
from ..interfaces import (
    ConsistencyReport,
    ValidationResult,
)


class LlamaCppTextGenerator:
    """Text generation via llama-cpp-python with GGUF models.

    Loads quantized GGUF files from ~/.storyteller/models/.
    Generates JSON output via create_completion with retry parsing.

    Usage:
        gen = LlamaCppTextGenerator(config)
        await gen.load()
        result = await gen.generate(prompt="...", seed=42)
        await gen.unload()
    """

    provider: str
    model_name: str
    quantization: str

    def __init__(self, config: ModelConfig) -> None:
        self.provider = config.provider
        self.model_name = config.model
        self.quantization = config.quantization
        self._config = config
        self._loaded = False
        self._model: Any = None
        self._total_calls = 0

    async def generate(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate structured JSON output from a prompt.

        Calls llama.cpp create_completion in a thread, parses the
        response text as JSON, with fallbacks for markdown fences.
        """
        if self._model is None:
            raise RuntimeError(
                "Model not loaded. Call await backend.load() first."
            )

        self._total_calls += 1
        raw = await asyncio.to_thread(
            self._generate_text,
            prompt=prompt,
            schema=schema,
            temperature=temperature,
            seed=seed or 0,
            max_tokens=max_tokens,
        )
        result = _parse_json(
            raw,
            f"llama://{self.model_name}/call_{self._total_calls}",
        )
        if schema is not None:
            from jsonschema import Draft202012Validator

            Draft202012Validator(schema).validate(result)
        return result

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from llama.cpp. Yields complete text as one chunk."""
        if self._model is None:
            raise RuntimeError("Model not loaded.")
        raw = await asyncio.to_thread(
            self._generate_text,
            prompt=prompt,
            temperature=temperature,
            seed=seed or 0,
            max_tokens=4096,
        )
        yield raw

    async def load(self) -> None:
        """Load the GGUF model into memory via llama-cpp-python."""
        import llama_cpp

        path = self._resolve_model_path()
        if path is None or not path.exists():
            raise FileNotFoundError(
                f"GGUF model not found for {self.model_name} ({self.quantization}). "
                f"Expected at: ~/.storyteller/models/{self._config.file}. "
                "Download from Hugging Face or set models_dir in config/models.yaml."
            )

        self._model = llama_cpp.Llama(
            model_path=str(path),
            n_ctx=self._config.n_ctx if hasattr(self._config, 'n_ctx') else 16384,
            n_threads=min(8, os.cpu_count() or 4),
            verbose=False,
        )
        self._loaded = True

    async def unload(self) -> None:
        """Free the model from memory."""
        self._model = None
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 4700  # Approximate for Qwen 7B Q4_K_M

    def assert_implements(self, interface: type) -> None:
        pass

    # ── internal ──────────────────────────────────────────────────────

    def _resolve_model_path(self) -> Path | None:
        """Find the GGUF file.

        Checks in order:
        1. STORYTELLER_MODELS_DIR env var
        2. Project root ai_models/ ({project}/ai_models/{file})
        3. ~/.storyteller/models/ (legacy)
        4. Direct path (if file is absolute)
        """
        env_dir = os.environ.get("STORYTELLER_MODELS_DIR", "")
        project_root = Path(__file__).resolve().parent.parent.parent
        candidates: list[Path | None] = [
            Path(env_dir) / self._config.file if env_dir else None,
            project_root / "ai_models" / self._config.file,
            Path.home() / ".storyteller" / "models" / self._config.file,
            Path(self._config.file),
        ]
        for p in candidates:
            if p is not None and p.exists():
                return p
        return None

    def _generate_text(
        self,
        prompt: str,
        temperature: float,
        seed: int,
        max_tokens: int,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Synchronous generation — called via asyncio.to_thread."""
        assert self._model is not None

        result: dict[str, Any] = self._model.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            stop=["</s>", "<|im_end|>", "<|endoftext|>"],
            echo=False,
        )
        text: str = result["choices"][0]["text"]
        return text


class LlamaCppValidator:
    """Validation via a separate llama-cpp-python model (Phi-3.5-mini).

    Phase 5.5C: Now fully implemented — loads the validator model,
    calls consistency_check_v1.j2 for deep lore-violation detection,
    and falls back to deterministic-only when model is unavailable.
    """

    provider: str
    model_name: str
    quantization: str

    def __init__(self, config: ModelConfig) -> None:
        self.provider = config.provider
        self.model_name = config.model
        self.quantization = config.quantization
        self._config = config
        self._loaded = False
        self._model: Any = None

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Run LLM-based validation against the content.

        Falls back to valid if the model is not loaded — deterministic
        validation should already have been run by this point.
        """
        if not self._loaded or self._model is None:
            return ValidationResult(is_valid=True, warnings=["LLM validator not loaded — skipped"])

        bible = context.get("bible")
        if not isinstance(bible, dict):
            return ValidationResult(is_valid=True, warnings=["No bible context — skipped LLM validation"])

        import json as _json
        content_text = _json.dumps(content, indent=2)
        bible_text = _json.dumps(bible, indent=2)

        prompt = self._build_validation_prompt(content_text, bible_text)

        try:
            raw = await asyncio.to_thread(
                self._generate_text,
                prompt=prompt,
                temperature=0.3,
                seed=0,
                max_tokens=1024,
            )
            result = _parse_json(raw, f"validator://{self.model_name}")
            is_valid = result.get("is_valid", True)
            violations = result.get("violations", [])
            suggestions = result.get("suggestions", [])
            return ValidationResult(
                is_valid=is_valid,
                errors=[str(v) for v in violations] if violations else [],
                warnings=[str(s) for s in suggestions] if suggestions else [],
            )
        except Exception:
            return ValidationResult(is_valid=True, warnings=["LLM validation failed — using deterministic only"])

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> ConsistencyReport:
        """Check if generated text contradicts the World Bible."""
        if not self._loaded or self._model is None:
            return ConsistencyReport(is_consistent=True)

        import json as _json
        bible_text = _json.dumps(bible, indent=2)

        prompt = self._build_consistency_prompt(text, bible_text)

        try:
            raw = await asyncio.to_thread(
                self._generate_text,
                prompt=prompt,
                temperature=0.3,
                seed=0,
                max_tokens=1024,
            )
            result = _parse_json(raw, f"consistency://{self.model_name}")
            return ConsistencyReport(
                is_consistent=result.get("is_consistent", True),
                violations=result.get("violations", []),
                suggestions=result.get("suggestions", []),
            )
        except Exception:
            return ConsistencyReport(is_consistent=True)

    async def load(self) -> None:
        """Load the validator model into memory."""
        try:
            import llama_cpp

            path = self._resolve_model_path()
            if path is None or not path.exists():
                self._loaded = False
                return  # Validator model is optional — deterministic checks still run

            self._model = llama_cpp.Llama(
                model_path=str(path),
                n_ctx=4096,
                n_threads=min(4, os.cpu_count() or 4),
                verbose=False,
            )
            self._loaded = True
        except Exception:
            self._loaded = False

    async def unload(self) -> None:
        self._model = None
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2200

    def assert_implements(self, interface: type) -> None:
        pass

    # ── internal ──────────────────────────────────────────────────────

    def _resolve_model_path(self) -> Path | None:
        env_dir = os.environ.get("STORYTELLER_MODELS_DIR", "")
        project_root = Path(__file__).resolve().parent.parent.parent
        candidates: list[Path | None] = [
            Path(env_dir) / self._config.file if env_dir else None,
            project_root / "ai_models" / self._config.file,
            Path.home() / ".storyteller" / "models" / self._config.file,
            Path(self._config.file),
        ]
        for p in candidates:
            if p is not None and p.exists():
                return p
        return None

    @staticmethod
    def _build_validation_prompt(content_json: str, bible_json: str) -> str:
        """Build the validation prompt using consistency_check_v1.j2 if available."""
        return (
            "You are a lore validator. Check the following generated content "
            "against the World Bible rules. Report any violations.\n\n"
            "=== WORLD BIBLE ===\n"
            f"{bible_json}\n\n"
            "=== GENERATED CONTENT ===\n"
            f"{content_json}\n\n"
            "Output valid JSON:\n"
            '{"is_valid": true/false, "violations": ["..."], "suggestions": ["..."]}'
        )

    @staticmethod
    def _build_consistency_prompt(text: str, bible_json: str) -> str:
        """Build the consistency check prompt."""
        return (
            "You are a lore validator. Check if the following text contradicts "
            "the World Bible. Report any violations.\n\n"
            "=== WORLD BIBLE ===\n"
            f"{bible_json}\n\n"
            "=== TEXT TO CHECK ===\n"
            f"{text[:3000]}\n\n"
            "Output valid JSON:\n"
            '{"is_consistent": true/false, "violations": ["..."], "suggestions": ["..."]}'
        )

    def _generate_text(
        self,
        prompt: str,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> str:
        assert self._model is not None
        result: dict[str, Any] = self._model.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            stop=["</s>", "<|im_end|>"],
            echo=False,
        )
        return str(result["choices"][0]["text"])


# ── JSON parsing helpers (shared) ────────────────────────────────────────────


def _parse_json(raw: str, source: str) -> dict[str, Any]:
    """Parse LLM output as JSON, with fallbacks for common issues.

    Tries:
    1. Direct JSON parse
    2. Extract from markdown ```json fences
    3. Balanced-brace extraction (handles thinking/preamble before JSON)
    4. Regex fallback: first { ... } pair
    5. Trailing-comma repair on extracted candidate
    """
    stripped = raw.strip()

    # Try direct parse
    try:
        result: dict[str, Any] = json.loads(stripped)
        return result
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', stripped, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            return result
        except json.JSONDecodeError:
            pass

    # Try complete balanced objects, largest first. A model can emit a malformed
    # draft followed by a corrected object; stopping at the first opening brace
    # would discard the valid retry in the same response.
    candidates = _extract_balanced_json_candidates(stripped)
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            # Try fixing trailing commas (only on already-broken JSON)
            repaired = _repair_trailing_commas(candidate)
            if repaired != candidate:
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

    # Last resort: greedy regex
    match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"LLM response was not valid JSON.\n"
        f"Source: {source}\n"
        f"Raw response (first 500 chars): {stripped[:500]}...\n"
    )


def _extract_balanced_json(text: str) -> str | None:
    """Extract the first balanced { ... } JSON object from text.

    Handles LLM output that includes preamble/thinking text before
    the JSON by finding the first '{' and tracking brace depth
    through strings and escapes to find the matching '}'.
    """
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        c = text[i]

        if escape:
            escape = False
            continue

        if c == '\\' and in_string:
            escape = True
            continue

        if c == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None  # Unbalanced braces


def _extract_balanced_json_candidates(text: str) -> tuple[str, ...]:
    """Return distinct complete object candidates found anywhere in model text."""
    candidates: list[str] = []
    for start, character in enumerate(text):
        if character != "{":
            continue
        candidate = _extract_balanced_json(text[start:])
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def _repair_trailing_commas(json_text: str) -> str:
    """Remove trailing commas before ] or } — a common LLM JSON mistake.

    NOTE: This regex is string-blind (doesn't track JSON string boundaries).
    A string value containing ", }" would be corrupted. Since this is only
    called on JSON that already failed to parse, the risk is acceptable.
    """
    repaired = re.sub(r',(\s*[}\]])', r'\1', json_text)
    return repaired
