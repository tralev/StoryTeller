"""Ollama LLM backend — calls local Ollama REST API (http://localhost:11434).

Implements TextGenerator protocol. No model files needed —
Ollama manages model downloads and inference.

Usage:
    backend = OllamaTextGenerator(model_name="qwen2.5:7b")
    await backend.load()  # verifies Ollama is reachable
    result = await backend.generate(prompt="...", temperature=0.7, seed=42)
    await backend.unload()
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
import urllib.error
from typing import Any, AsyncIterator


class OllamaTextGenerator:
    """Text generation via local Ollama server.

    Implements the TextGenerator protocol:
      - generate(prompt, temperature, seed, max_tokens) → dict
      - generate_stream(prompt) → AsyncIterator[str]
      - load() / unload()
    """

    provider: str = "ollama"
    model_name: str
    quantization: str = ""

    def __init__(self, model_name: str = "qwen2.5:7b") -> None:
        self.model_name = model_name
        self._base_url = "http://localhost:11434"
        self._loaded = False
        self._total_calls = 0
        self._total_tokens = 0

    # ── public interface ──────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate structured JSON output from a prompt.

        Uses Ollama's JSON mode (format="json") to enforce valid JSON output.
        Falls back to extracting JSON from the response if Ollama wraps it.
        """
        self._total_calls += 1
        raw = await self._call_ollama(
            prompt=prompt,
            temperature=temperature,
            seed=seed or 0,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return self._parse_json(raw, f"ollama://{self.model_name}/call_{self._total_calls}")

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama."""
        # Ollama supports streaming natively — for now, do a single chunk
        result = await self._call_ollama(
            prompt=prompt,
            temperature=temperature,
            seed=seed or 0,
            max_tokens=4096,
            json_mode=False,
        )
        yield result

    async def load(self) -> None:
        """Verify Ollama is reachable and the model exists."""
        try:
            await self._call_ollama(prompt="ping", temperature=0, seed=0, max_tokens=1)
            self._loaded = True
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Is 'ollama serve' running? Error: {e}"
            ) from e

    async def unload(self) -> None:
        """Ollama manages its own memory — nothing to do."""
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        """Estimate: Ollama server + Qwen 7B ≈ 5-6 GB."""
        return 5500

    def assert_implements(self, interface: type) -> None:
        pass

    # ── HTTP helpers ──────────────────────────────────────────────────

    async def _call_ollama(
        self,
        prompt: str,
        temperature: float,
        seed: int,
        max_tokens: int,
        json_mode: bool = True,
    ) -> str:
        """Call the Ollama /api/generate endpoint synchronously in a thread."""

        def _sync() -> str:
            url = f"{self._base_url}/api/generate"
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "seed": seed,
                    "num_predict": max_tokens,
                },
            }
            if json_mode:
                payload["format"] = "json"

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:  # 10 min timeout
                    body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                response_text: str = body.get("response", "")
                # Track token usage if available
                if "eval_count" in body:
                    self._total_tokens += body.get("eval_count", 0)
                return response_text
            except urllib.error.URLError as e:
                raise ConnectionError(
                    f"Cannot reach Ollama at {self._base_url}. "
                    f"Is 'ollama serve' running? ({e})"
                ) from e
            except ConnectionRefusedError:
                raise ConnectionError(
                    f"Ollama connection refused at {self._base_url}. "
                    "Run 'ollama serve' first."
                )

        return await asyncio.to_thread(_sync)

    @staticmethod
    def _parse_json(raw: str, source: str) -> dict[str, Any]:
        """Parse LLM output as JSON, with fallbacks for common issues."""
        # Try direct parse first
        try:
            result: dict[str, Any] = json.loads(raw)
            return result
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code fences
        import re
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                return result
            except json.JSONDecodeError:
                pass

        # Try finding a JSON object in the text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                return result
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"LLM response was not valid JSON.\n"
            f"Source: {source}\n"
            f"Raw response (first 500 chars): {raw[:500]}...\n"
        )
