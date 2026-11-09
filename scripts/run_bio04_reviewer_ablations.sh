#!/usr/bin/env bash
# Fast bio_04-aligned reviewer ablations (scripted audits, ~2–5 min total).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
export PYTHONPATH="${ROOT}/src:${ROOT}"

echo "== Config alignment audit =="
"${PY}" "${ROOT}/eval/run_bio04_config_audit.py"

echo
echo "== Provenance generalization (bio_04 vs no hard rules) =="
"${PY}" "${ROOT}/eval/run_provenance_generalization_audit.py"

echo
echo "== Integration ablation (bio_04 vs minus reflection) =="
"${PY}" "${ROOT}/eval/run_provenance_integration_ablation.py"

echo
echo "Done. For live AgentDojo drop-one, rerun with defenses:"
echo "  bio_04 bio_04_minus_reflection bio_04_minus_feature_shuffle \\"
echo "  bio_04_minus_hard_rules bio_04_minus_goal_continuity bio_04_minus_metadata_repair"
