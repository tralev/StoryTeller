#!/usr/bin/env python3
"""Download GGUF models from Hugging Face with progress bars.

Replaces the bash pull_models.sh with a Python version that shows
download progress via rich or tqdm.

Usage:
    python scripts/pull_models.py
    python scripts/pull_models.py --with-images
    python scripts/pull_models.py --models-dir ./ai_models
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.request import urlretrieve

# Model definitions — sync with config/models.yaml
MODELS: dict[str, dict[str, str]] = {
    "qwen2.5-7b-instruct-q4_k_m": {
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "file": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "size_gb": 4.4,
        "required": True,
    },
    "phi-3.5-mini-instruct-q4_k_m": {
        "url": "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "file": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "size_gb": 2.2,
        "required": True,
    },
    "llama-3.2-3b-instruct-q4_k_m": {
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_gb": 2.0,
        "required": False,
    },
    "sdxl-turbo-q8_0": {
        "url": "https://huggingface.co/OlegSkutte/sdxl-turbo-GGUF/resolve/main/sd_xl_turbo_1.0.q8_0.gguf",
        "file": "sd_xl_turbo_1.0.q8_0.gguf",
        "size_gb": 3.8,
        "required": False,
    },
}


def _download_with_progress(url: str, dest: str, label: str) -> None:
    """Download a file with a simple progress indicator."""
    print(f"  Downloading {label}...", end=" ", flush=True)

    try:
        urlretrieve(url, dest)
        size_mb = Path(dest).stat().st_size / (1024 * 1024)
        print(f"done ({size_mb:.0f} MB)")
    except Exception as e:
        print(f"FAILED: {e}")
        # Remove partial download
        Path(dest).unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Download StoryTeller GGUF models")
    parser.add_argument(
        "--with-images", action="store_true", help="Also download SDXL-Turbo image model (~3.8 GB)"
    )
    parser.add_argument(
        "--models-dir", type=str, default="~/.storyteller/models", help="Directory to store models"
    )
    parser.add_argument(
        "--all", action="store_true", help="Download all models including optional ones"
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir).expanduser()
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print("  StoryTeller — Model Downloader")
    print(f"  Target: {models_dir}")
    print(f"{'=' * 60}\n")

    total_gb = 0.0
    to_download: list[tuple[str, dict[str, str]]] = []

    for name, info in MODELS.items():
        dest = models_dir / info["file"]
        if dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"  ✓ {name} ({size_mb:.0f} MB) — already downloaded")
            continue

        if info["required"] or args.all:
            to_download.append((name, info))
            total_gb += info["size_gb"]
        elif name == "sdxl-turbo-q8_0" and args.with_images:
            to_download.append((name, info))
            total_gb += info["size_gb"]

    if not to_download:
        print("\n  All models already downloaded!")
        return

    print(f"\n  To download: {len(to_download)} model(s) (~{total_gb:.1f} GB total)\n")

    # Check disk space (simple check)
    try:
        stat = os.statvfs(models_dir)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        if free_gb < total_gb * 1.2:
            print(f"  ⚠ Warning: Only {free_gb:.1f} GB free. Need ~{total_gb:.1f} GB.\n")
    except Exception:
        pass

    failed: list[str] = []
    for name, info in to_download:
        dest = models_dir / info["file"]
        try:
            _download_with_progress(info["url"], str(dest), name)
        except Exception as e:
            failed.append(f"{name}: {e}")

    print(f"\n{'=' * 60}")
    if failed:
        print(f"  {len(to_download) - len(failed)} succeeded, {len(failed)} failed:")
        for f in failed:
            print(f"    ✗ {f}")
        sys.exit(1)
    else:
        print(f"  All {len(to_download)} model(s) downloaded successfully!")
        print(f"  Location: {models_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
