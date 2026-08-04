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
            temperature=temperature,
            seed=seed or 0,
            max_tokens=max_tokens,
        )
        return _parse_json(
            raw,
            f"llama://{self.model_name}/call_{self._total_calls}",
        )

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
    """Validation via a separate llama-cpp-python model (Phi-3.5-mini)."""

    provider: str
    model_name: str
    quantization: str

    def __init__(self, config: ModelConfig) -> None:
        self.provider = config.provider
        self.model_name = config.model
        self.quantization = config.quantization
        self._config = config
        self._loaded = False

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        raise NotImplementedError(
            "LlamaCppValidator.validate() is not yet implemented."
        )

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> ConsistencyReport:
        raise NotImplementedError(
            "LlamaCppValidator.consistency_check() is not yet implemented."
        )

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2200

    def assert_implements(self, interface: type) -> None:
        pass


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

    # Try balanced-brace extraction (handles LLM preamble text)
    candidate = _extract_balanced_json(stripped)
    if candidate is not None:
        try:
            result = json.loads(candidate)
            return result
        except json.JSONDecodeError:
            # Try fixing trailing commas (only on already-broken JSON)
            repaired = _repair_trailing_commas(candidate)
            if repaired != candidate:
                try:
                    result = json.loads(repaired)
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


def _repair_trailing_commas(json_text: str) -> str:
    """Remove trailing commas before ] or } — a common LLM JSON mistake.

    NOTE: This regex is string-blind (doesn't track JSON string boundaries).
    A string value containing ", }" would be corrupted. Since this is only
    called on JSON that already failed to parse, the risk is acceptable.
    """
    repaired = re.sub(r',(\s*[}\]])', r'\1', json_text)
    return repaired
