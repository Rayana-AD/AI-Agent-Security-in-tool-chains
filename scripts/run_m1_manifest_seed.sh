#!/usr/bin/env bash
# Full defense comparison on stress-manifest seed slice.
# 9 tasks × 4 attacks × 2 injections × 4 defenses = 288 pairs (~2–3h deepseek)
#
# Usage:
#   ./scripts/run_m1_manifest_seed.sh           # all 24 batches
#   ./scripts/run_m1_manifest_seed.sh 1 4       # batches 1–4
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

START_BATCH="${1:-1}"
MAX_BATCHES="${2:-24}"
shift 2 2>/dev/null || true
PROFILE="m1_manifest_seed"
PROGRESS="${ROOT}/runs/paper_m1_manifest_seed_progress.json"
LOG="${ROOT}/runs/paper_m1_manifest_seed.log"
PY="${ROOT}/.venv/bin/python"

mkdir -p "${ROOT}/runs"

echo "=== m1_manifest_seed: spotlight-gap seed slice, full defenses ===" | tee -a "$LOG"
echo "  defenses: none, spotlight, transformers_pi_detector, bio_04" | tee -a "$LOG"
echo "  batches ${START_BATCH}..$((START_BATCH + MAX_BATCHES - 1)) (max 24)" | tee -a "$LOG"

"${PY}" -u scripts/run_m1_gated_rerun.py \
  --profile "${PROFILE}" \
  --progress-file "${PROGRESS}" \
  --start-batch "${START_BATCH}" \
  --max-batches "${MAX_BATCHES}" \
  --stress-probe-first \
  --continue-on-gate-fail \
  "$@" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== Summarize ===" | tee -a "$LOG"
"${PY}" scripts/run_m1_gated_rerun.py \
  --profile "${PROFILE}" \
  --progress-file "${PROGRESS}" \
  --summarize-only 2>&1 | tee -a "$LOG"
