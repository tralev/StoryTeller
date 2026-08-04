#!/usr/bin/env python3
"""Direct runner — bypasses script path issues by importing main directly."""
import os
import sys
from pathlib import Path

# Ensure src is on sys.path
forge_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(forge_src))

# Ensure models are found
os.environ.setdefault(
    "STORYTELLER_MODELS_DIR",
    str(Path(__file__).resolve().parent.parent / "ai_models"),
)

# Patch sys.argv to pass through to the script
sys.argv = [
    "run_overnight.py",
    "--seed", "7",
    "--tone", "heroic_fantasy",
    "--title", "The Crystal Accord",
    "--output", str(Path(__file__).resolve().parent.parent / "tmp" / "output"),
    "--config", "config/models.yaml",
]

# Now run the script's main
from scripts.run_overnight import main
main()
