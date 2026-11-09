#!/usr/bin/env bash
# m1_manifest_seed on OpenRouter Llama 3.3 70B — separate progress/log/figures.
#
# Usage:
#   ./scripts/run_m1_manifest_seed_llama70.sh
#   ./scripts/run_m1_manifest_seed_llama70.sh 13 12 --force-rerun
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

START_BATCH="${1:-1}"
MAX_BATCHES="${2:-24}"
shift 2 2>/dev/null || true

PROFILE="m1_manifest_seed"
MODEL="openrouter_llama70"
PROGRESS="${ROOT}/runs/paper_m1_manifest_seed_llama70_progress.json"
LOG="${ROOT}/runs/paper_m1_manifest_seed_llama70.log"
FIGURES="${ROOT}/figures/m1_manifest_seed_llama70"
PY="${ROOT}/.venv/bin/python"

mkdir -p "${ROOT}/runs" "${FIGURES}"

echo "=== m1_manifest_seed | model=${MODEL} ===" | tee -a "$LOG"
echo "  progress: ${PROGRESS}" | tee -a "$LOG"
echo "  batches ${START_BATCH}..$((START_BATCH + MAX_BATCHES - 1))" | tee -a "$LOG"

"${PY}" -u scripts/run_m1_gated_rerun.py \
  --profile "${PROFILE}" \
  --model-mode "${MODEL}" \
  --progress-file "${PROGRESS}" \
  --start-batch "${START_BATCH}" \
  --max-batches "${MAX_BATCHES}" \
  --stress-probe-first \
  --continue-on-gate-fail \
  "$@" 2>&1 | tee -a "$LOG"

RC=${PIPESTATUS[0]}

echo "" | tee -a "$LOG"
echo "=== Summarize (${MODEL}) ===" | tee -a "$LOG"
"${PY}" scripts/run_m1_gated_rerun.py \
  --profile "${PROFILE}" \
  --model-mode "${MODEL}" \
  --progress-file "${PROGRESS}" \
  --summarize-only 2>&1 | tee -a "$LOG" || true

echo "" | tee -a "$LOG"
echo "=== Figures (${MODEL}) ===" | tee -a "$LOG"
"${PY}" eval/plot_m1_manifest_seed.py \
  --progress "${PROGRESS}" \
  --out "${FIGURES}" 2>&1 | tee -a "$LOG" || true

exit "${RC}"
