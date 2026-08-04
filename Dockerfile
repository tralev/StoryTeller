# StoryTeller Forge — Docker image for overnight generation
#
# Build:
#   docker build -t storyteller-forge .
#
# Run (via docker-compose):
#   docker compose run forge --seed 7 --tone heroic_fantasy --title "The Crystal Accord"
#
# Or use the convenience script:
#   bash forge/scripts/run_docker.sh

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── App directory ────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ──────────────────────────────────────────────
COPY forge/pyproject.toml forge/setup.py /app/
COPY forge/src/ /app/src/
COPY forge/config/ /app/config/
COPY forge/scripts/ /app/scripts/

RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir llama-cpp-python psutil

# ── Data directories (mounted as volumes) ────────────────────────────
RUN mkdir -p /data/models /data/output

# ── Environment ────────────────────────────────────────────────────
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# ── Entrypoint ────────────────────────────────────────────────────────
# Default: run the overnight test with logging
# Override with docker compose run forge [args...]
ENTRYPOINT ["python", "/app/scripts/run_overnight.py"]
CMD ["--seed", "7", "--tone", "heroic_fantasy", "--title", "The Crystal Accord", "--output", "/data/output"]
