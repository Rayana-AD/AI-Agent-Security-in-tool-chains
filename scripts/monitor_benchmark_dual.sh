#!/usr/bin/env bash
# Background monitor for DeepSeek + Llama AgentDojo benchmarks.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$ROOT/runs/agentdojo_upstream"
INTERVAL="${MONITOR_INTERVAL_SEC:-120}"
STATUS="$LOGDIR/benchmark_monitor.log"
DEEPSEEK_PID="$LOGDIR/benchmark_full_deepseek.pid"
LLAMA_PID="$LOGDIR/benchmark_full_llama70.pid"
DEEPSEEK_RUN="$LOGDIR/benchmark_20260629_224640"
LLAMA_RUN=$(ls -dt "$LOGDIR"/benchmark_*_llama70 2>/dev/null | head -1 || echo "")
DEEPSEEK_ONLY="${DEEPSEEK_ONLY:-0}"
if [[ -f "$LOGDIR/deepseek_only.mode" ]]; then
  DEEPSEEK_ONLY=1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$STATUS"; }

count_logs() {
  local run_dir="$1"
  local attack="${2:-tool_knowledge}"
  if [[ -d "$run_dir/logs/$attack" ]]; then
    find "$run_dir/logs/$attack" -name "*.json" 2>/dev/null | wc -l | tr -d ' '
  else
    echo "0"
  fi
}

latest_json_age() {
  local run_dir="$1"
  local f
  f=$(find "$run_dir/logs" -name "*.json" -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || true)
  if [[ -n "$f" && -f "$f" ]]; then
    stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$f" 2>/dev/null || stat -c "%y" "$f" 2>/dev/null | cut -d. -f1
  else
    echo "none"
  fi
}

check_one() {
  local label="$1"
  local pid_file="$2"
  local run_dir="$3"
  local pid=""

  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file" 2>/dev/null || true)
  fi

  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    local cpu
    cpu=$(ps -p "$pid" -o pcpu= 2>/dev/null | tr -d ' ' || echo "?")
    local elapsed
    elapsed=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ' || echo "?")
    local nlogs latest
    nlogs=$(count_logs "$run_dir")
    latest=$(latest_json_age "$run_dir")
    log "$label PID=$pid OK elapsed=$elapsed cpu=${cpu}% json_logs=$nlogs latest_json=$latest"
  else
    log "$label PID=${pid:-missing} DEAD — needs restart (watchdog may recover)"
    return 1
  fi
}

log "=== monitor started interval=${INTERVAL}s ==="

while true; do
  ok=0
  check_one "DeepSeek" "$DEEPSEEK_PID" "$DEEPSEEK_RUN" && ok=$((ok + 1)) || true
  if [[ "$DEEPSEEK_ONLY" != "1" && -n "$LLAMA_RUN" ]]; then
    check_one "Llama70" "$LLAMA_PID" "$LLAMA_RUN" && ok=$((ok + 1)) || true
  fi
  expected=1
  [[ "$DEEPSEEK_ONLY" != "1" ]] && expected=2
  if [[ -f "$LOGDIR/benchmark_full_deepseek.log" ]]; then
    tail -1 "$LOGDIR/benchmark_full_deepseek.log" 2>/dev/null | sed 's/^/  ds_tail: /' >> "$STATUS" || true
  fi
  log "heartbeat alive_models=$ok/$expected"
  echo "" >> "$STATUS"
  sleep "$INTERVAL"
done
