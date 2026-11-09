#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export MODEL="${MODEL:-/Users/rayana/Desktop/AI-Illusion/runs/modelscope_hub/qwen/Qwen3-1.7B}"
export PYTHONPATH="${ROOT}/src:${ROOT}:${PYTHONPATH:-}"
PY="${ROOT}/.venv/bin/python"

echo "=== BioHarness Ablation Suite ==="
echo "Model: $MODEL"

for cfg in full ablation_1 ablation_2 ablation_3 ablation_4 baseline_1 baseline_2 baseline_3; do
  echo "--- Running $cfg ---"
  "$PY" eval/run_pilot.py --mode pilot --config "$cfg" --no-llm
done

echo "=== Done ==="
