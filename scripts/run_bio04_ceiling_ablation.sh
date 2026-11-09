#!/usr/bin/env bash
# Live AgentDojo carry-ceiling (Γ) ablations vs bio_04 (DeepSeek first).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
export PYTHONPATH="${ROOT}/src:${ROOT}"

PROGRESS="${PROGRESS:-${ROOT}/runs/paper_bio04_ceiling_ablation_progress.json}"
PROFILE="${1:-m1_manifest_seed}"
MODEL="${2:-deepseek}"
shift 2 2>/dev/null || true

DEFENSES=(
  bio_04
  bio_04_ceiling_off
  bio_04_ceiling_flat_open
  bio_04_ceiling_flat_lock
  bio_04_ceiling_strict
  bio_04_ceiling_loose
)

DEFENSE_ARGS=()
for d in "${DEFENSES[@]}"; do
  DEFENSE_ARGS+=(--defense "$d")
done

echo "Profile: ${PROFILE}  model: ${MODEL}"
echo "Progress: ${PROGRESS}"
echo "Defenses: ${DEFENSES[*]}"

"${PY}" -u "${ROOT}/scripts/run_m1_gated_rerun.py" \
  --profile "${PROFILE}" \
  --model-mode "${MODEL}" \
  --progress-file "${PROGRESS}" \
  --max-batches 0 \
  --no-stress-check \
  --continue-on-gate-fail \
  "${DEFENSE_ARGS[@]}" \
  "$@"
