#!/usr/bin/env bash
# Llama 3.3 70B full eval: supplementary (fast) then AgentDojo multi-attack full benchmark.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=".venv/bin/python"
LOG_DIR="runs/agentdojo_upstream"
mkdir -p "$LOG_DIR"

echo "=== Phase 1: supplementary benchmarks (citation + Idea2 v2) ==="
$PY eval/run_supplementary_benchmarks.py \
  --model-mode openrouter_llama70 \
  2>&1 | tee "$LOG_DIR/llama70_supplementary.log"

echo "=== Phase 2: AgentDojo full (3 attacks × 4 suites × bio v2) ==="
nohup $PY eval/run_agentdojo_benchmark.py \
  --model-mode openrouter_llama70 \
  --skip-tool-filter \
  2>&1 | tee "$LOG_DIR/llama70_full.log" &

echo "AgentDojo full benchmark PID: $!"
echo "Tail: tail -f $LOG_DIR/llama70_full.log"
