#!/usr/bin/env bash
# DeepSeek-only expansion of the attack-framing table.
# Incremental cells: travel (2 tasks) + extra workspace tasks (32, 13).
# Merge with the existing 24-condition progress; do not overwrite Table 1.
#
# Usage:
#   ./scripts/run_m1_framing_expand.sh           # all 16 batches
#   ./scripts/run_m1_framing_expand.sh 1 4       # batches 1–4
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

START_BATCH="${1:-1}"
MAX_BATCHES="${2:-16}"
shift 2 2>/dev/null || true
PROFILE="m1_framing_expand"
PROGRESS="${ROOT}/runs/paper_m1_framing_expand_progress.json"
LOG="${ROOT}/runs/paper_m1_framing_expand.log"
PY="${ROOT}/.venv/bin/python"

mkdir -p "${ROOT}/runs"

echo "=== m1_framing_expand: travel + extra workspace (DeepSeek) ===" | tee -a "$LOG"
echo "  defenses: none, spotlight, detector, bio_04" | tee -a "$LOG"
echo "  batches ${START_BATCH}..$((START_BATCH + MAX_BATCHES - 1)) (max 16)" | tee -a "$LOG"

"${PY}" -u scripts/run_m1_gated_rerun.py \
  --profile "${PROFILE}" \
  --progress-file "${PROGRESS}" \
  --model-mode deepseek \
  --start-batch "${START_BATCH}" \
  --max-batches "${MAX_BATCHES}" \
  --continue-on-gate-fail \
  "$@" 2>&1 | tee -a "$LOG"
