#!/usr/bin/env bash
# Detached M1 live benchmark with resume checkpoints.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG="${ROOT}/runs/paper_suite_m1_live.log"
PIDFILE="${ROOT}/runs/paper_suite_m1_live.pid"
PROGRESS="${ROOT}/runs/paper_m1_live_progress.json"

mkdir -p "${ROOT}/runs"

if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Already running (pid $OLD_PID). Log: $LOG"
    exit 1
  fi
  rm -f "$PIDFILE"
fi

# Seed resume pointer for the partial banking run if no progress exists yet.
if [[ ! -f "$PROGRESS" && -d "${ROOT}/runs/agentdojo_upstream/benchmark_20260707_152721" ]]; then
  cat > "$PROGRESS" <<EOF
{
  "completed": {},
  "active": {
    "deepseek|important_instructions|injection_task_0|banking": {
      "run_dir": "${ROOT}/runs/agentdojo_upstream/benchmark_20260707_152721"
    }
  }
}
EOF
  echo "Seeded progress resume → benchmark_20260707_152721"
fi

nohup "${ROOT}/.venv/bin/python" -u "${ROOT}/eval/run_paper_suite.py" \
  --live --m1-scale --skip-offline --plot \
  --progress-file "$PROGRESS" \
  >> "$LOG" 2>&1 < /dev/null &

echo $! > "$PIDFILE"
echo "Started M1 live benchmark (pid $(cat "$PIDFILE"))"
echo "  log:      $LOG"
echo "  progress: $PROGRESS"
echo "  tail -f $LOG"
echo ""
echo "Tip: run this script from Terminal.app for a fully detached job."
echo "If the process exits immediately, re-run the same command in Terminal."
