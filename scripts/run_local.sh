#!/bin/bash
# Run overnight test locally (not in Docker)
# Usage: bash scripts/run_local.sh

set -e
cd "$(dirname "$0")/.."

export STORYTELLER_MODELS_DIR="$(pwd)/../ai_models"
export PYTHONPATH="$(pwd)/src"

exec .venv/bin/python scripts/run_overnight.py \
  --seed 7 \
  --tone heroic_fantasy \
  --title "The Crystal Accord" \
  --output "$(pwd)/tmp/output" \
  --config config/models.yaml \
  "$@"
