#!/usr/bin/env bash
# DEPRECATED naming (bio04/bio05 mix). Prefer: ./scripts/run_table1_remeasure.sh
# Paper remeasure scope (Oct 2026, reflection probe v2):
#   - DeepSeek + Llama: bio_04 ONLY on m1_manifest_seed (24 batches each)
#   - Baselines (none/spotlight/detector/TS/MELON): frozen from July progress
#   - Table 2–3 / Fig 3–4: keep existing (framing expand Oct + official_matrix_v2)
#   - Optional: live drop-one for appendix Table 4 / Fig 5 (DeepSeek spare budget)
#
# Usage:
#   ./scripts/run_paper_remeasure_bio04.sh main          # DeepSeek + Llama bio_04 + merge
#   ./scripts/run_paper_remeasure_bio04.sh smoke         # 3-batch DeepSeek smoke (required before deepseek)
#   ./scripts/run_paper_remeasure_bio04.sh deepseek      # DeepSeek bio_04 only (24 batches)
#   ./scripts/run_paper_remeasure_bio04.sh llama         # Llama bio_04 only
#   ./scripts/run_paper_remeasure_bio04.sh merge         # merge only (after live runs)
#   ./scripts/run_paper_remeasure_bio04.sh dropone       # appendix ablation (6 defenses × 24 batches)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
LOGDIR="${ROOT}/runs/agentdojo_upstream_probe_v2"
PROBE="${ROOT}/scripts/run_m1_manifest_seed_probe_v2.sh"

SEED_DEEP="${ROOT}/runs/paper_m1_manifest_seed_bio_elastic_progress.json"
SEED_LLAMA="${ROOT}/runs/paper_m1_manifest_seed_llama70_bio_elastic_progress.json"
PROG_DS="${ROOT}/runs/paper_m1_manifest_seed_probe_v2_bio05_r3_progress.json"
PROG_LLAMA="${ROOT}/runs/paper_m1_manifest_seed_probe_v2_llama70_bio05_r3_progress.json"
MERGED_DS="${ROOT}/runs/paper_m1_manifest_seed_probe_v2_merged_deepseek_r3.json"
MERGED_LLAMA="${ROOT}/runs/paper_m1_manifest_seed_probe_v2_merged_llama70_r3.json"
LOG_DS="${ROOT}/runs/agentdojo_upstream_probe_v2/deepseek_r3"
LOG_LLAMA="${ROOT}/runs/agentdojo_upstream_probe_v2/llama70"
PROG_SMOKE="${ROOT}/runs/paper_m1_manifest_seed_probe_v2_bio05_r3_smoke_progress.json"
LOG_SMOKE="${ROOT}/runs/agentdojo_upstream_probe_v2/deepseek_r3_smoke"
SMOKE_OK="${ROOT}/runs/paper_bio05_r3_smoke.ok"

_run_live() {
  local mode="$1"
  local progress="$2"
  local logdir="$3"
  local start_batch="${4:-1}"
  local max_batches="${5:-0}"
  mkdir -p "${logdir}"
  local -a batch_args=(--max-batches 0)
  if [[ "${max_batches}" -gt 0 ]]; then
    batch_args=(--start-batch "${start_batch}" --max-batches "${max_batches}")
  fi
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile m1_manifest_seed \
    --progress-file "${progress}" \
    --logdir "${logdir}" \
    "${batch_args[@]}" \
    --continue-on-gate-fail \
    --force-rerun \
    --defenses-only bio_05 \
    $([[ "${mode}" == "llama" ]] && echo --model-mode openrouter_llama70 || echo --model-mode deepseek)
}

_smoke() {
  rm -f "${SMOKE_OK}"
  rm -f "${PROG_SMOKE}"
  echo "Smoke: 3 batches -> ${PROG_SMOKE} logdir=${LOG_SMOKE}"
  # Batches 1, 5 (ii|inj1|slack), 19 (direct|inj0|banking)
  for spec in "1:1" "5:1" "19:1"; do
    local start="${spec%%:*}"
    local n="${spec##*:}"
    _run_live deepseek "${PROG_SMOKE}" "${LOG_SMOKE}" "${start}" "${n}"
  done
  "${PY}" scripts/check_bio05_remeasure_smoke.py \
    --progress "${PROG_SMOKE}" \
    --logdir "${LOG_SMOKE}"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SMOKE_OK}"
  echo "Smoke OK stamp -> ${SMOKE_OK}"
}

_merge() {
  if [[ ! -f "${SEED_DEEP}" ]]; then
    echo "Missing seed: ${SEED_DEEP}" >&2
    exit 1
  fi
  if [[ ! -f "${PROG_DS}" ]]; then
    echo "Missing DeepSeek bio_04 progress: ${PROG_DS}" >&2
    exit 1
  fi
  "${PY}" scripts/merge_bio_elastic_gate_results.py \
    --seed "${SEED_DEEP}" \
    --progress "${PROG_DS}" \
    --out "${MERGED_DS}"
  echo "DeepSeek merged -> ${MERGED_DS}"

  if [[ -f "${SEED_LLAMA}" && -f "${PROG_LLAMA}" ]]; then
    "${PY}" scripts/merge_bio_elastic_gate_results.py \
      --seed "${SEED_LLAMA}" \
      --progress "${PROG_LLAMA}" \
      --out "${MERGED_LLAMA}"
    echo "Llama merged -> ${MERGED_LLAMA}"
  else
    echo "Skip Llama merge (seed or prog missing)."
  fi

  echo ""
  echo "Export Table 1 / Fig 2 / Fig 3 (DeepSeek bio row + frozen peers):"
  echo "  ${PY} eval/supplement/run_p0_peer_table.py --main ${MERGED_DS} --experiment-id peer_deepseek_24cond_probe_v2"
  echo "Figures:"
  echo "  ${PY} eval/plot_m1_manifest_seed.py --progress ${MERGED_DS} --out figures/m1_manifest_seed_probe_v2"
  echo "  ${PY} eval/plot_paper_results.py  # if wired to merged progress path"
}

_dropone() {
  PROGRESS="${ROOT}/runs/paper_bio05_dropone_probe_v2_r2_progress.json"
  echo "Live drop-one (Table 4) -> ${PROGRESS} logdir=${LOG_DS}"
  mkdir -p "${LOG_DS}"
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile m1_manifest_seed \
    --model-mode deepseek \
    --progress-file "${PROGRESS}" \
    --logdir "${LOG_DS}" \
    --max-batches 0 \
    --continue-on-gate-fail \
    --force-rerun \
    --defenses-only bio_05 \
    --defenses-only bio_04_minus_reflection \
    --defenses-only bio_04_minus_feature_shuffle \
    --defenses-only bio_04_minus_hard_rules \
    --defenses-only bio_04_minus_goal_continuity \
    --defenses-only bio_04_minus_metadata_repair
}

MODE="${1:-main}"
case "${MODE}" in
  main)
    if [[ ! -f "${SMOKE_OK}" ]]; then
      echo "Run smoke first: ./scripts/run_paper_remeasure_bio04.sh smoke" >&2
      exit 1
    fi
    rm -f "${PROG_DS}"
    _run_live deepseek "${PROG_DS}" "${LOG_DS}"
    _run_live llama "${PROG_LLAMA}" "${LOG_LLAMA}"
    _merge
    ;;
  smoke) _smoke ;;
  deepseek)
    if [[ ! -f "${SMOKE_OK}" ]]; then
      echo "Run smoke first: ./scripts/run_paper_remeasure_bio04.sh smoke" >&2
      exit 1
    fi
    rm -f "${PROG_DS}"
    _run_live deepseek "${PROG_DS}" "${LOG_DS}"
    ;;
  llama) _run_live llama "${PROG_LLAMA}" "${LOG_LLAMA}" ;;
  merge) _merge ;;
  dropone) _dropone ;;
  *)
    echo "Usage: $0 {smoke|deepseek|llama|merge|main|dropone}" >&2
    exit 1
    ;;
esac
