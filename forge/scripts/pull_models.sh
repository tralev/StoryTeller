#!/usr/bin/env bash
# pull_models.sh — Download GGUF models for the StoryTeller Forge.
#
# Usage:
#   bash forge/scripts/pull_models.sh
#   bash forge/scripts/pull_models.sh --with-images
#
# Downloads to ai_models/ at the project root.
# Set STORYTELLER_MODELS_DIR env var to override.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MODELS_DIR="${STORYTELLER_MODELS_DIR:-$PROJECT_ROOT/ai_models}"

mkdir -p "$MODELS_DIR"

echo "=== StoryTeller Forge — GGUF Model Download ==="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Models dir:   $MODELS_DIR"
echo ""

# ── Helper: download with wget, resume support ───────────────────────
download_gguf() {
    local url="$1"
    local dest="$2"
    local name="$3"

    if [ -f "$dest" ]; then
        echo "  ✓ $name already exists at $dest"
        ls -lh "$dest"
        return 0
    fi

    echo "  Downloading $name..."
    echo "  URL: $url"
    echo "  Destination: $dest"
    echo ""

    if command -v wget &>/dev/null; then
        wget -c -O "$dest" "$url" --show-progress
    elif command -v curl &>/dev/null; then
        curl -C - -L -o "$dest" "$url"
    else
        echo "ERROR: Neither wget nor curl found. Install one and retry."
        exit 1
    fi

    echo ""
    echo "  ✓ $name downloaded."
    ls -lh "$dest"
}

# ── Step 1: Qwen2.5-7B-Instruct Q4_K_M ──────────────────────────────
QWEN_FILE="Qwen2.5-7B-Instruct-Q4_K_M.gguf"
QWEN_PATH="$MODELS_DIR/$QWEN_FILE"
QWEN_URL="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"

echo "Step 1: Text generation model"
echo "  Model:  Qwen2.5-7B-Instruct Q4_K_M"
echo "  Size:   ~4.7 GB"
echo "  Used for: World Bible, Story, Graph, Music ABC notation"
echo ""

download_gguf "$QWEN_URL" "$QWEN_PATH" "Qwen2.5-7B-Instruct"

echo ""

# ── Step 2: SDXL-Turbo Q8_0 ─────────────────────────────────────────
SDXL_FILE="sd_xl_turbo_1.0.q8_0.gguf"
SDXL_PATH="$MODELS_DIR/$SDXL_FILE"
SDXL_URL="https://huggingface.co/OlegSkutte/sdxl-turbo-GGUF/resolve/main/sd_xl_turbo_1.0.q8_0.gguf"

echo "Step 2: Image generation model (optional)"
echo "  Model:  SDXL-Turbo Q8_0"
echo "  Size:   ~5.0 GB"
echo "  Used for: 512×512 scene illustrations"
echo ""

if [ -f "$SDXL_PATH" ]; then
    echo "  ✓ SDXL-Turbo already exists at $SDXL_PATH"
    ls -lh "$SDXL_PATH"
else
    echo "  SDXL-Turbo download is optional. The pipeline will fall back to"
    echo "  deterministic placeholder images (colored PNGs) if not found."
    echo ""
    echo "  To download SDXL-Turbo, run:"
    echo "    bash forge/scripts/pull_models.sh --with-images"
    echo ""
    if [ "${1:-}" = "--with-images" ] || [ "${1:-}" = "--all" ]; then
        download_gguf "$SDXL_URL" "$SDXL_PATH" "SDXL-Turbo"
    else
        echo "  (Skipping — re-run with --with-images to download)"
    fi
fi

echo ""
echo "=== Done ==="
echo ""
echo "Models ready:"
echo "  Text:   $QWEN_PATH ($(ls -lh "$QWEN_PATH" | awk '{print $5}'))"
if [ -f "$SDXL_PATH" ]; then
    echo "  Image:  $SDXL_PATH ($(ls -lh "$SDXL_PATH" | awk '{print $5}'))"
else
    echo "  Image:  (placeholder mode — re-run with --with-images to download)"
fi
echo ""
echo "To start the overnight test:"
echo "  python forge/scripts/run_overnight.py --seed 7 --tone heroic_fantasy --title 'The Crystal Accord'"
echo ""

# ── Docker instructions ──────────────────────────────────────────────
echo "Or run in Docker:"
echo "  bash forge/scripts/run_docker.sh"
echo ""
