#!/usr/bin/env bash
# Build stress manifest: cached AgentDojo scan + scripted harness sweep.
# Optional live none sweep: RUN_LIVE_NONE=1 ./scripts/run_stress_manifest.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT="${STRESS_MANIFEST_OUT:-runs/stress_manifest.json}"
PROFILE="${STRESS_MANIFEST_PROFILE:-m1_none_sweep}"

ARGS=(--scan-only --scripted --output "$OUT" --write-seed-yaml configs/stress_manifest_seed.yaml)

if [[ "${RUN_LIVE_NONE:-0}" == "1" ]]; then
  ARGS=(--scan-only --scripted --live-none --profile "$PROFILE" --output "$OUT" --write-seed-yaml configs/stress_manifest_seed.yaml)
fi

if [[ "${RUN_LIVE_EXTRA:-0}" == "1" ]]; then
  ARGS=(--scan-only --scripted --live-extra --output "$OUT" --write-seed-yaml configs/stress_manifest_seed.yaml)
fi

echo "[stress_manifest] python eval/run_stress_manifest.py ${ARGS[*]}"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python
fi
"$PYTHON" eval/run_stress_manifest.py "${ARGS[@]}"

echo ""
echo "Top spotlight gaps (spotlight also fails when none succeeds):"
python - <<'PY'
import json
from pathlib import Path
p = Path("runs/stress_manifest.json")
if not p.exists():
    raise SystemExit(0)
m = json.loads(p.read_text())
gaps = m.get("agentdojo", {}).get("spotlight_gaps") or []
for row in gaps[:15]:
    print(
        f"  {row['suite']:10} {row['user_task']:14} {row['attack']:32} "
        f"inj={row['injection_task']} none_util={row['none_utility']}"
    )
print(f"  … total {len(gaps)} spotlight gaps")
PY
