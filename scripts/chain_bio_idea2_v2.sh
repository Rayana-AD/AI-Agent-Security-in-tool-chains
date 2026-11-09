#!/usr/bin/env bash
# Wait for an in-flight AgentDojo benchmark, then run bio_idea2_v2 on the same run dir.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUN_DIR="${RUN_DIR:-runs/agentdojo_upstream/benchmark_20260629_224640}"
WAIT_PID="${1:-${WAIT_PID:-}}"
LOG="${LOG:-runs/agentdojo_upstream/bio_idea2_v2_after_bio_full.log}"
PY="${ROOT}/.venv/bin/python"

if [[ -z "$WAIT_PID" ]]; then
  echo "Usage: $0 <benchmark-pid>"
  echo "  Or:  WAIT_PID=<pid> [RUN_DIR=...] $0"
  exit 1
fi

echo "=== Chain: wait PID $WAIT_PID → bio_idea2_v2 ===" | tee -a "$LOG"
echo "Run dir: $RUN_DIR" | tee -a "$LOG"

exec "$PY" eval/run_agentdojo_benchmark.py \
  --model-mode auto \
  --run-dir "$RUN_DIR" \
  -d bio_idea2_v2 \
  --force-rerun \
  --wait-pid "$WAIT_PID" \
  2>&1 | tee -a "$LOG"
