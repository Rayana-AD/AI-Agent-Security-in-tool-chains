#!/usr/bin/env bash
# Run MELON + Task Shield on DeepSeek × m1_manifest_seed (24 conditions).
# Does not re-run none / spotlighting / bio_04.
set -euo pipefail
cd "$(dirname "$0")/.."
START="${1:-1}"
MAX="${2:-24}"
mkdir -p runs logs
exec .venv/bin/python -u scripts/run_peer_baselines.py \
  --profile m1_manifest_seed \
  --progress-file runs/paper_peer_baselines_deepseek_progress.json \
  --start-batch "$START" \
  --max-batches "$MAX" \
  2>&1 | tee -a logs/peer_baselines_deepseek.log
