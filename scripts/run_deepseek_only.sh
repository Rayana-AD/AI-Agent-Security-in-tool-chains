#!/usr/bin/env bash
# Launch DeepSeek-only AgentDojo benchmark (resume + utility/error re-run).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
LOGDIR="$ROOT/runs/agentdojo_upstream"

echo "=== $(date -Iseconds) prepare DeepSeek re-run ==="
"$ROOT/.venv/bin/python" "$ROOT/scripts/prepare_deepseek_rerun.py" --run-dir "$LOGDIR/benchmark_20260629_224640"

echo "=== launch DeepSeek-only daemon ==="
DEEPSEEK_ONLY=1 "$ROOT/.venv/bin/python" "$ROOT/scripts/benchmark_daemon.py" | tee -a "$LOGDIR/benchmark_wrapper.log"

echo ""
echo "Monitor: tail -f $LOGDIR/benchmark_monitor.log"
echo "Worker:  tail -f $LOGDIR/benchmark_full_deepseek.log"
