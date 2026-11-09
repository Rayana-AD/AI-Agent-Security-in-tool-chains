#!/usr/bin/env bash
# Tiered M1 experiment strategy — fast feedback before full 800-pair runs.
#
# Tier 0 (~30s):  unit tests + offline probes (no LLM)
# Tier 1 (~2m/batch):  m1_probe — 1 task, none+bio_04, persona attack
# Tier 2 (~5m/batch):  m1_gated_light — 2 tasks, 4 defenses, gated readout
# Tier main (~3–4h):   m1_main_5h — 50 tasks, 400 pairs, main-conference table
# Tier 3 (20–40h):     m1 full profile (800+ pairs, 2 models)
#
# Usage:
#   ./scripts/run_m1_tiered.sh 0              # offline only
#   ./scripts/run_m1_tiered.sh 1              # probe batch 1 (slack)
#   ./scripts/run_m1_tiered.sh main           # main-conference run (5h budget)
#   ./scripts/run_m1_tiered.sh main 3 2       # main run batches 3–4
#   ./scripts/run_m1_tiered.sh 1 4            # probe batches 1–4 (all suites)
#   ./scripts/run_m1_tiered.sh 2 3            # gated_light start batch 3
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TIER="${1:-1}"
shift || true
START_BATCH=1
MAX_BATCHES=1
if [[ $# -ge 2 && "$1" =~ ^[0-9]+$ && "$2" =~ ^[0-9]+$ ]]; then
  START_BATCH="$1"
  MAX_BATCHES="$2"
  shift 2
elif [[ $# -eq 1 && "$1" =~ ^[0-9]+$ ]]; then
  if [[ "$TIER" == "1" ]]; then
    MAX_BATCHES="$1"
  else
    START_BATCH="$1"
  fi
  shift
fi

PY="${ROOT}/.venv/bin/python"

tier0() {
  echo "=== Tier 0: pytest + offline probes ==="
  "${PY}" -m pytest \
    tests/test_m1_gated_stress.py \
    tests/test_carry_simplified.py \
    tests/test_cleave_carry_linkage.py \
    tests/test_channel_gradient.py \
    -q
  "${PY}" -c "from eval.run_paper_suite import run_offline; import json; print(json.dumps(run_offline(), indent=2)[:8000])"
}

tier1() {
  local profile="m1_probe"
  local progress="${ROOT}/runs/paper_m1_probe_progress.json"
  echo "=== Tier 1: ${profile} batch ${START_BATCH} count ${MAX_BATCHES} ==="
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile "${profile}" \
    --progress-file "${progress}" \
    --start-batch "${START_BATCH}" \
    --max-batches "${MAX_BATCHES}" \
    --stress-probe-first \
    --continue-on-gate-fail \
    "$@"
}

tier2() {
  local profile="m1_gated_light"
  local progress="${ROOT}/runs/paper_m1_gated_light_progress.json"
  echo "=== Tier 2: ${profile} batch ${START_BATCH} count ${MAX_BATCHES} ==="
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile "${profile}" \
    --progress-file "${progress}" \
    --start-batch "${START_BATCH}" \
    --max-batches "${MAX_BATCHES}" \
    --stress-probe-first \
    --continue-on-gate-fail \
    "$@"
}

tier_main() {
  local start="${START_BATCH:-1}"
  local count="${MAX_BATCHES:-8}"
  exec "${ROOT}/scripts/run_m1_main_5h.sh" "${start}" "${count}" "$@"
}

tier3() {
  local profile="m1"
  local progress="${ROOT}/runs/paper_m1_progress.json"
  echo "=== Tier 3: ${profile} batch ${START_BATCH} count ${MAX_BATCHES} ==="
  echo "Warning: full M1 — expect ~20–40h for all batches on deepseek."
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile "${profile}" \
    --progress-file "${progress}" \
    --start-batch "${START_BATCH}" \
    --max-batches "${MAX_BATCHES}" \
    --stress-probe-first \
    --continue-on-gate-fail \
    "$@"
}

case "${TIER}" in
  0) tier0 ;;
  1) tier1 ;;
  2) tier2 ;;
  main|m1_main_5h) tier_main ;;
  3) tier3 ;;
  *)
    echo "Unknown tier ${TIER}. Use 0|1|2|main|3."
    exit 1
    ;;
esac
