#!/bin/bash
# Launch overnight test in background, fully detached.
# Usage: bash forge/scripts/launch_test.sh

cd "$(dirname "$0")/.."

export STORYTELLER_MODELS_DIR="$(pwd)/../ai_models"

nohup .venv/bin/python -m scripts.run_overnight \
  --seed 7 \
  --tone heroic_fantasy \
  --title "The Crystal Accord" \
  --output "$(pwd)/../tmp/output" \
  --config config/models.yaml \
  > "$(pwd)/../tmp/output/console.log" 2>&1 &

PID=$!
echo "Overnight test started (PID: $PID)"
echo "Monitor: tail -f $(pwd)/../tmp/output/pipeline_events.jsonl"
echo "Console: tail -f $(pwd)/../tmp/output/console.log"
echo "Kill:   kill $PID"
