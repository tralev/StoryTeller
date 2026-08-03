#!/usr/bin/env bash
# pull_models.sh — Download models for the StoryTeller Forge overnight test.
#
# Usage:
#   chmod +x forge/scripts/pull_models.sh
#   ./forge/scripts/pull_models.sh
#
# Pulls:
#   1. Qwen2.5 7B Instruct (~4.7 GB) — via Ollama
#   2. (Optional) SDXL-Turbo GGUF (~2.5 GB) — via wget to ~/.storyteller/models/
#
# After running, start Ollama:
#   ollama serve
#
# Verify models are available:
#   ollama list

set -euo pipefail

echo "=== StoryTeller Forge — Model Pull Script ==="
echo ""

# ── Step 1: Start Ollama if not running ─────────────────────────────
if ! ollama list &>/dev/null; then
    echo "Ollama server is not running."
    echo "Starting Ollama in the background..."
    ollama serve &
    OLLAMA_PID=$!
    sleep 3
    echo "Waiting for Ollama to be ready..."
    for i in {1..10}; do
        if ollama list &>/dev/null; then
            echo "Ollama is ready."
            break
        fi
        sleep 2
    done
else
    echo "Ollama server is already running."
fi

echo ""

# ── Step 2: Pull Qwen2.5 7B ────────────────────────────────────────
echo "Pulling Qwen2.5 7B Instruct (text generation)..."
echo "  This is ~4.7 GB. May take 10-30 minutes depending on connection."
ollama pull qwen2.5:7b

echo ""
echo "Verifying Qwen2.5..."
ollama list | grep qwen2.5 && echo "  ✓ Qwen2.5 7B is ready."

echo ""

# ── Step 3: Download SDXL-Turbo GGUF ────────────────────────────────
MODELS_DIR="$HOME/.storyteller/models"
mkdir -p "$MODELS_DIR"

SDXL_FILE="sdxl-turbo-q8_0.gguf"
SDXL_PATH="$MODELS_DIR/$SDXL_FILE"

if [ -f "$SDXL_PATH" ]; then
    echo "SDXL-Turbo already exists at $SDXL_PATH"
    ls -lh "$SDXL_PATH"
else
    echo "SDXL-Turbo GGUF not found."
    echo ""
    echo "You need to download it manually from Hugging Face:"
    echo "  https://huggingface.co/stabilityai/sdxl-turbo-gguf"
    echo ""
    echo "Place it at: $SDXL_PATH"
    echo ""
    echo "Expected size: ~2.5 GB"
    echo ""
    echo "Alternatively, the pipeline will fall back to placeholder images"
    echo "(solid-color PNGs generated from the seed) if SDXL is not available."
fi

echo ""
echo "=== Done ==="
echo ""
echo "Models ready:"
echo "  Text:   ollama/qwen2.5:7b"
if [ -f "$SDXL_PATH" ]; then
    echo "  Image:  $SDXL_PATH ($(ls -lh "$SDXL_PATH" | awk '{print $5}'))"
else
    echo "  Image:  (placeholder mode — SDXL not found)"
fi
echo ""
echo "To start the overnight test:"
echo "  cd forge"
echo "  python scripts/run_overnight.py --seed 42 --tone dark_fantasy --title 'The Ashen Marches'"
echo ""
echo "To monitor progress:"
echo "  tail -f output/pipeline_events.jsonl"
echo ""
