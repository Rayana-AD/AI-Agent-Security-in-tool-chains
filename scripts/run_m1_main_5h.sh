#!/usr/bin/env bash
# Main-conference primary live run (~400 pairs, deepseek, budget ≤5h).
#
# Profile: m1_main_5h
#   50 tasks × 2 attacks × 1 injection × 4 defenses
#   none | spotlight | transformers_pi_detector | bio_04
#
# Usage:
#   ./scripts/run_m1_main_5h.sh              # all 8 batches, continue on gate fail
#   ./scripts/run_m1_main_5h.sh 3 2          # batches 3–4
#   ./scripts/run_m1_main_5h.sh 1 8 --dry-run
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

START_BATCH="${1:-1}"
MAX_BATCHES="${2:-8}"
shift 2 2>/dev/null || true

PROFILE="m1_main_5h"
PROGRESS="${ROOT}/runs/paper_m1_main_5h_progress.json"
LOG="${ROOT}/runs/paper_m1_main_5h.log"
PY="${ROOT}/.venv/bin/python"

mkdir -p "${ROOT}/runs"

echo "=== m1_main_5h: 50 tasks, 400 pairs/model, ~5h budget ===" | tee -a "$LOG"
echo "  defenses: none, spotlight, transformers_pi_detector, bio_04" | tee -a "$LOG"
echo "  batches ${START_BATCH}..$((START_BATCH + MAX_BATCHES - 1)) (max 8)" | tee -a "$LOG"

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
