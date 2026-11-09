#!/usr/bin/env bash
# Restart dead benchmark workers (not the monitor). Runs alongside dual benchmark.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$ROOT/runs/agentdojo_upstream"
INTERVAL="${WATCHDOG_INTERVAL_SEC:-300}"
LAUNCH="$ROOT/scripts/run_full_benchmark_with_baselines.sh"
DAEMON="$ROOT/.venv/bin/python $ROOT/scripts/benchmark_daemon.py"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watchdog] $*" >> "$LOGDIR/benchmark_watchdog.log"; }

is_alive() {
  local pf="$1"
  [[ -f "$pf" ]] || return 1
  local pid
  pid=$(cat "$pf" 2>/dev/null || true)
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

log "watchdog started interval=${INTERVAL}s"

while true; do
  need=0
  is_alive "$LOGDIR/benchmark_full_deepseek.pid" || need=1
  if [[ "${DEEPSEEK_ONLY:-0}" != "1" ]]; then
    is_alive "$LOGDIR/benchmark_full_llama70.pid" || need=1
  fi

  if [[ "$need" -eq 1 ]]; then
    log "dead worker detected — invoking launch script (RESTART_DEAD=1)"
    if [[ -f "$LOGDIR/deepseek_only.mode" ]]; then
      RESTART_DEAD=1 DEEPSEEK_ONLY=1 $DAEMON >> "$LOGDIR/benchmark_watchdog.log" 2>&1 || log "daemon launch failed"
    else
      RESTART_DEAD=1 bash "$LAUNCH" >> "$LOGDIR/benchmark_watchdog.log" 2>&1 || log "launch failed"
    fi
  fi
  sleep "$INTERVAL"
done
