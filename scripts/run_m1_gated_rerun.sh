#!/usr/bin/env bash
# Stable detached M1 utility-fix gated rerun (same pattern as run_m1_live.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG="${ROOT}/runs/paper_m1_gated_rerun_v2.log"
PIDFILE="${ROOT}/runs/paper_m1_gated_rerun_v2.pid"
PROGRESS="${ROOT}/runs/paper_m1_utility_fix_rerun_v2.json"

START_BATCH="${1:-1}"
MAX_BATCHES="${2:-0}"

mkdir -p "${ROOT}/runs"

if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Already running (pid $OLD_PID)."
    echo "  log:      $LOG"
    echo "  progress: $PROGRESS"
    echo "  tail -f $LOG"
    exit 1
  fi
  rm -f "$PIDFILE"
fi

CMD=(
  "${ROOT}/.venv/bin/python" -u "${ROOT}/scripts/run_m1_gated_rerun.py"
  --progress-file "$PROGRESS"
  --start-batch "$START_BATCH"
)
if [[ "$MAX_BATCHES" != "0" ]]; then
  CMD+=(--max-batches "$MAX_BATCHES")
fi
# First full rerun: force fresh benchmark logs for incomplete batches.
if [[ ! -f "$PROGRESS" ]] || [[ "$(cat "$PROGRESS" 2>/dev/null)" == "{}" ]]; then
  CMD+=(--force-rerun)
fi

nohup "${CMD[@]}" >> "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDFILE"

echo "Started M1 gated rerun v2 (pid $(cat "$PIDFILE"))"
echo "  log:      $LOG"
echo "  progress: $PROGRESS"
echo "  batches:  start=$START_BATCH max=$MAX_BATCHES (0=all)"
echo ""
echo "Monitor:  tail -f $LOG"
echo "Status:   kill -0 \$(cat $PIDFILE) 2>/dev/null && echo running || echo stopped"
echo ""
echo "Tip: paste this script into the Cursor integrated terminal (foreground"
echo "session survives). Agent nohup launches may exit when the agent turn ends."
