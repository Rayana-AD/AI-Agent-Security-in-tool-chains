#!/usr/bin/env bash
# Re-run m1_manifest_seed with current harness (reflection excess-shift + conjunctive gate).
# All outputs are NEW — never writes to runs/agentdojo_upstream or July progress files.
#
# Usage:
#   ./scripts/run_m1_manifest_seed_probe_v2.sh full          # DeepSeek, 4 defenses, 24 batches (~90–120 min)
#   ./scripts/run_m1_manifest_seed_probe_v2.sh bio_only    # DeepSeek, bio_04 only, 24 batches (~30–45 min)
#   ./scripts/run_m1_manifest_seed_probe_v2.sh expand      # travel+workspace framing expand, 16 batches
#   ./scripts/run_m1_manifest_seed_probe_v2.sh llama       # Llama-3.3-70B on OpenRouter, bio_04 only
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-full}"
PY="${ROOT}/.venv/bin/python"
LOGDIR="${ROOT}/runs/agentdojo_upstream_probe_v2"
# Set by caller (deepseek vs llama subdirs) to avoid parallel benchmark_* races.
LOG="${ROOT}/runs/paper_m1_manifest_seed_probe_v2.log"

_common() {
  mkdir -p "${ROOT}/runs"
  echo "logdir=${LOGDIR}" | tee -a "$LOG"
}

_run() {
  local profile="$1"
  local model="$2"
  local progress="$3"
  shift 3
  _common
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile "${profile}" \
    --model-mode "${model}" \
    --progress-file "${progress}" \
    --logdir "${LOGDIR}" \
    --start-batch 1 \
    --max-batches 0 \
    --continue-on-gate-fail \
    --force-rerun \
    "$@" 2>&1 | tee -a "$LOG"
}

case "${MODE}" in
  full)
    _run "m1_manifest_seed" "deepseek" "${ROOT}/runs/paper_m1_manifest_seed_probe_v2_progress.json"
    ;;
  bio_only)
    LOGDIR="${ROOT}/runs/agentdojo_upstream_probe_v2/deepseek_r3"
    _run "m1_manifest_seed" "deepseek" "${ROOT}/runs/paper_m1_manifest_seed_probe_v2_bio05_r3_progress.json" \
      --defenses-only bio_05
    ;;
  expand)
    _run "m1_framing_expand" "deepseek" "${ROOT}/runs/paper_m1_framing_expand_probe_v2_progress.json"
    ;;
  llama)
    LOGDIR="${ROOT}/runs/agentdojo_upstream_probe_v2/llama70_r3"
    _run "m1_manifest_seed" "openrouter_llama70" \
      "${ROOT}/runs/paper_m1_manifest_seed_probe_v2_llama70_bio05_r3_progress.json" \
      --defenses-only bio_05
    ;;
  *)
    echo "Usage: $0 {full|bio_only|expand|llama}" >&2
    exit 1
    ;;
esac

echo "" | tee -a "$LOG"
echo "Next: ${PY} eval/plot_m1_manifest_seed.py --progress <progress.json> --out figures/m1_manifest_seed_probe_v2" | tee -a "$LOG"
echo "Peer table (bio row + frozen TS/MELON): ${PY} eval/supplement/run_p0_peer_table.py --main <progress> --experiment-id peer_deepseek_24cond_probe_v2" | tee -a "$LOG"
