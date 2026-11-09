#!/usr/bin/env bash
# Live AgentDojo bio_04 component ablations (aligned with main paper config).
# Uses a separate progress file so prior misaligned drop-one runs are preserved.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
export PYTHONPATH="${ROOT}/src:${ROOT}"

PROGRESS="${PROGRESS:-${ROOT}/runs/paper_bio04_dropone_probe_v2_progress.json}"
LOGDIR="${LOGDIR:-${ROOT}/runs/agentdojo_upstream_probe_v2}"
PROFILE="${1:-m1_manifest_seed}"
MODEL="${2:-deepseek}"
shift 2 2>/dev/null || true

DEFENSES=(
  bio_04
  bio_04_minus_reflection
  bio_04_minus_feature_shuffle
  bio_04_minus_hard_rules
  bio_04_minus_goal_continuity
  bio_04_minus_metadata_repair
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
  --logdir "${LOGDIR}" \
  --max-batches 0 \
  --continue-on-gate-fail \
  --force-rerun \
  "${DEFENSE_ARGS[@]}" \
  "$@"
