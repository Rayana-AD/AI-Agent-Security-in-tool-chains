#!/usr/bin/env bash
# Table 1 live bio row remeasure (Oct 2026+).
# Uses defense label bio_remeasure only — never overwrites July bio_04 logs.
# Harness config: idea1_provenance_mlp_bio_04 (fold_gate_cleave + excess-shift).
#
# Usage:
#   ./scripts/run_table1_remeasure.sh smoke      # 3 batches + checker (required before full)
#   ./scripts/run_table1_remeasure.sh deepseek   # 24 batches
#   ./scripts/run_table1_remeasure.sh llama
#   ./scripts/run_table1_remeasure.sh merge
#   ./scripts/run_table1_remeasure.sh diff-smoke # per-task vs July anchor batch
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"

DEFENSE="bio_remeasure"
SEED_DEEP="${ROOT}/runs/paper_m1_manifest_seed_bio_elastic_progress.json"
SEED_LLAMA="${ROOT}/runs/paper_m1_manifest_seed_llama70_bio_elastic_progress.json"
RUNS="${ROOT}/runs/table1_remeasure"
PROG_DS="${RUNS}/deepseek_progress.json"
PROG_LLAMA="${RUNS}/llama_progress.json"
PROG_SMOKE="${RUNS}/smoke_progress.json"
LOG_DS="${RUNS}/logs/deepseek"
LOG_LLAMA="${RUNS}/logs/llama"
LOG_SMOKE="${RUNS}/logs/smoke"
MERGED_DS="${RUNS}/merged_deepseek.json"
MERGED_LLAMA="${RUNS}/merged_llama.json"
SMOKE_OK="${RUNS}/smoke.ok"
JULY_ANCHOR_BENCH="${ROOT}/runs/agentdojo_upstream/benchmark_20260713_011555"

_run() {
  local mode="$1" progress="$2" logdir="$3"
  local start="${4:-1}" max="${5:-0}"
  mkdir -p "${logdir}" "${RUNS}"
  local -a batch=(--max-batches 0)
  [[ "${max}" -gt 0 ]] && batch=(--start-batch "${start}" --max-batches "${max}")
  "${PY}" -u scripts/run_m1_gated_rerun.py \
    --profile m1_manifest_seed \
    --progress-file "${progress}" \
    --logdir "${logdir}" \
    "${batch[@]}" \
    --continue-on-gate-fail \
    --force-rerun \
    --defenses-only "${DEFENSE}" \
    $([[ "${mode}" == "llama" ]] && echo --model-mode openrouter_llama70 || echo --model-mode deepseek)
}

_smoke() {
  rm -f "${SMOKE_OK}" "${PROG_SMOKE}"
  echo "Table1 smoke (defense=${DEFENSE}) -> ${PROG_SMOKE}"
  for spec in "1:1" "5:1" "19:1"; do
    _run deepseek "${PROG_SMOKE}" "${LOG_SMOKE}" "${spec%%:*}" "${spec##*:}"
  done
  "${PY}" scripts/check_table1_remeasure_smoke.py \
    --progress "${PROG_SMOKE}" \
    --logdir "${LOG_SMOKE}" \
    --defense "${DEFENSE}"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SMOKE_OK}"
}

_merge() {
  "${PY}" scripts/merge_bio_elastic_gate_results.py \
    --seed "${SEED_DEEP}" --progress "${PROG_DS}" --out "${MERGED_DS}"
  echo "merged -> ${MERGED_DS}"
  if [[ -f "${SEED_LLAMA}" && -f "${PROG_LLAMA}" ]]; then
    "${PY}" scripts/merge_bio_elastic_gate_results.py \
      --seed "${SEED_LLAMA}" --progress "${PROG_LLAMA}" --out "${MERGED_LLAMA}"
  fi
  echo "Export: ${PY} eval/supplement/run_p0_peer_table.py --main ${MERGED_DS} --experiment-id peer_deepseek_table1_remeasure"
}

_diff_smoke() {
  local cand
  cand="$(find "${LOG_SMOKE}" -maxdepth 1 -name 'benchmark_*' -type d 2>/dev/null | sort | head -1)"
  for b in "${LOG_SMOKE}"/benchmark_*; do
    [[ -d "${b}" ]] || continue
    if [[ -f "${b}/report.json" ]] && grep -q '"important_instructions"' "${b}/report.json" 2>/dev/null; then
      if grep -q banking "${b}/report.json"; then cand="${b}"; fi
    fi
  done
  [[ -d "${JULY_ANCHOR_BENCH}" ]] || { echo "Missing July anchor: ${JULY_ANCHOR_BENCH}" >&2; exit 1; }
  [[ -n "${cand}" ]] || { echo "No smoke banking ii bench under ${LOG_SMOKE}" >&2; exit 1; }
  "${PY}" scripts/diff_table1_user_tasks.py \
    --reference-bench "${JULY_ANCHOR_BENCH}" --reference-defense bio_04 \
    --candidate-bench "${cand}" --candidate-defense "${DEFENSE}" \
    --suite banking
}

MODE="${1:-smoke}"
case "${MODE}" in
  smoke) _smoke ;;
  deepseek)
    [[ -f "${SMOKE_OK}" ]] || { echo "Run: $0 smoke" >&2; exit 1; }
    rm -f "${PROG_DS}"
    _run deepseek "${PROG_DS}" "${LOG_DS}"
    ;;
  llama) _run llama "${PROG_LLAMA}" "${LOG_LLAMA}" ;;
  merge) _merge ;;
  diff-smoke) _diff_smoke ;;
  *)
    echo "Usage: $0 {smoke|deepseek|llama|merge|diff-smoke}" >&2
    exit 1
    ;;
esac
