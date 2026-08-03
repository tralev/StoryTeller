"""Concrete LLM backend using llama-cpp-python.

Implements TextGenerator by loading GGUF models and calling
create_completion with JSON parsing and retry extraction.

Also provides LlamaCppValidator for independent model-based validation.
"""

from __future__ import annotations

import asyncio
import json
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
            n_ctx=4096,
            n_threads=min(8, (asyncio.get_event_loop())._default_executor._max_workers if False else 8),
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
        """Find the GGUF file."""
        candidates = [
            Path.home() / ".storyteller" / "models" / self._config.file,
            Path(self._config.file),
        ]
        for p in candidates:
            if p.exists():
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
    3. Extract first { ... } object from text
    """
    # Try direct parse
    stripped = raw.strip()
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

    # Try finding a JSON object in the text
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
