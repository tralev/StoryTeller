#!/usr/bin/env bash
# run_docker.sh — Build and run the StoryTeller Forge overnight test in Docker.
#
# Usage:
#   bash scripts/run_docker.sh
#   bash scripts/run_docker.sh --seed 42 --tone dark_fantasy --title "The Ashen Marches"
#
# Prerequisites:
#   1. Docker installed (docker compose available)
#   2. Models downloaded: bash scripts/pull_models.sh --with-images
#   3. tmp/ directory exists (created automatically)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== StoryTeller Forge — Docker Overnight Test ==="
echo ""
echo "Project: $PROJECT_ROOT"
echo ""

# ── Check prerequisites ──────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not found. Install Docker first."
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi

# ── Ensure directories exist ─────────────────────────────────────────
mkdir -p "$PROJECT_ROOT/tmp/output"
mkdir -p "$PROJECT_ROOT/ai_models"

# ── Check models exist ───────────────────────────────────────────────
QWEN="$PROJECT_ROOT/ai_models/qwen2.5-7b-instruct-q4_k_m.gguf"
if [ ! -f "$QWEN" ]; then
    echo "WARNING: Qwen2.5 GGUF not found at ai_models/"
    echo "  Download first: bash scripts/pull_models.sh"
    echo ""
    echo "Continue anyway? (pipeline will fail at model load)"
    read -p "  [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

SDXL="$PROJECT_ROOT/ai_models/sdxl-turbo-q8_0.gguf"
if [ ! -f "$SDXL" ]; then
    echo "NOTE: SDXL-Turbo not found — images will use placeholders."
    echo "  Download: bash scripts/pull_models.sh --with-images"
    echo ""
fi

# ── Build image ──────────────────────────────────────────────────────
echo "Building Docker image..."
cd "$PROJECT_ROOT"
docker compose build forge

echo ""
echo "=== Starting Overnight Test ==="
echo ""
echo "Parameters: ${*:---seed 7 --tone heroic_fantasy --title \"The Crystal Accord\"}"
echo ""
echo "Monitor progress:"
echo "  tail -f tmp/output/pipeline_events.jsonl"
echo "  tail -f tmp/output/ram_samples.jsonl"
echo ""
echo "To stop: Ctrl+C (checkpoint saved automatically)"
echo "To resume: bash scripts/run_docker.sh --resume"
echo ""

# ── Run ──────────────────────────────────────────────────────────────
docker compose run --rm forge "$@"

echo ""
echo "=== Test Complete ==="
echo ""
echo "Results:"
echo "  tmp/output/summary.json"
echo "  tmp/output/pipeline_events.jsonl"
echo "  tmp/output/The_Crystal_Accord_*.story"
echo ""
