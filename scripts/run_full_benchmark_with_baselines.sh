#!/usr/bin/env bash
# Full AgentDojo v1.2.2: 3 attacks × 4 suites × paper baselines + bio_idea1_provenance.
# Robust dual launch: caffeinate (macOS), pid files, optional watchdog/monitor.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/runs/agentdojo_upstream"
mkdir -p "$LOGDIR"

DEFENSE_ARGS=(
  --defense none
  --defense tool_filter
  --defense repeat_user_prompt
  --defense bio_idea1_provenance
)

if [[ "${INCLUDE_PI_DETECTOR:-0}" == "1" ]]; then
  DEFENSE_ARGS+=(--defense transformers_pi_detector)
fi

DEEPSEEK_DIR="$LOGDIR/benchmark_20260629_224640"
LLAMA_DIR=$(ls -dt "$LOGDIR"/benchmark_*_llama70 2>/dev/null | head -1 || true)
if [[ -z "$LLAMA_DIR" ]]; then
  LLAMA_DIR="$LOGDIR/benchmark_$(date +%Y%m%d_%H%M%S)_llama70"
fi

caffeinate_cmd() {
  if command -v caffeinate >/dev/null 2>&1 && [[ "${DISABLE_CAFFEINATE:-0}" != "1" ]]; then
    echo "caffeinate -dims"
  fi
}

run_one() {
  local mode="$1"
  local run_dir="$2"
  local log_file="$3"
  local pid_file="$4"
  local label="$5"

  if [[ -f "$pid_file" ]]; then
    local old
    old=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      if [[ "${RESTART_DEAD:-0}" == "1" ]]; then
        echo "$label already running PID=$old — skip"
        return 0
      fi
      echo "Stopping $label PID=$old"
      kill "$old" 2>/dev/null || true
      sleep 2
      kill -0 "$old" 2>/dev/null && kill -9 "$old" 2>/dev/null || true
    fi
  fi

  mkdir -p "$run_dir"
  echo "=== $(date -Iseconds) start $label mode=$mode ===" >> "$log_file"

  local -a cmd=("$PY" -u eval/run_agentdojo_benchmark.py --model-mode "$mode" "${DEFENSE_ARGS[@]}" --run-dir "$run_dir")
  local -a wrap=()
  local caf
  caf=$(caffeinate_cmd)
  if [[ -n "$caf" ]]; then
    read -r -a wrap <<< "$caf"
  fi

  # Subshell + nohup so workers survive IDE/shell session teardown.
  if [[ ${#wrap[@]} -gt 0 ]]; then
    nohup bash -c 'exec "$@"' _ "${wrap[@]}" "${cmd[@]}" >> "$log_file" 2>&1 < /dev/null &
  else
    nohup bash -c 'exec "$@"' _ "${cmd[@]}" >> "$log_file" 2>&1 < /dev/null &
  fi
  local pid=$!
  disown -h "$pid" 2>/dev/null || disown "$pid" 2>/dev/null || true
  echo "$pid" > "$pid_file"
  echo "Started $label PID=$pid log=$log_file run_dir=$run_dir"
}

start_monitor() {
  local mon_pid="$LOGDIR/benchmark_monitor.pid"
  local wd_pid="$LOGDIR/benchmark_watchdog.pid"

  if [[ -f "$mon_pid" ]]; then
    local mp
    mp=$(cat "$mon_pid" 2>/dev/null || true)
    if [[ -n "$mp" ]] && kill -0 "$mp" 2>/dev/null; then
      echo "Monitor already running PID=$mp"
      return 0
    fi
  fi

  nohup bash -c 'exec bash "$1"' _ "$ROOT/scripts/monitor_benchmark_dual.sh" \
    >> "$LOGDIR/benchmark_monitor.log" 2>&1 < /dev/null &
  echo $! > "$mon_pid"
  disown -h "$(cat "$mon_pid")" 2>/dev/null || true
  echo "Monitor PID=$(cat "$mon_pid") → tail -f $LOGDIR/benchmark_monitor.log"

  if [[ "${DISABLE_WATCHDOG:-0}" != "1" ]]; then
    if [[ -f "$wd_pid" ]]; then
      local wp
      wp=$(cat "$wd_pid" 2>/dev/null || true)
      kill -0 "$wp" 2>/dev/null && kill "$wp" 2>/dev/null || true
    fi
    nohup bash -c 'exec bash "$1"' _ "$ROOT/scripts/benchmark_watchdog.sh" \
      >> "$LOGDIR/benchmark_watchdog.log" 2>&1 < /dev/null &
    echo $! > "$wd_pid"
    disown -h "$(cat "$wd_pid")" 2>/dev/null || true
    echo "Watchdog PID=$(cat "$wd_pid") (auto-restart dead workers every 5min)"
  fi
}

echo "=== $(date -Iseconds) launch dual benchmark ===" | tee -a "$LOGDIR/benchmark_launch.log"

if [[ "${RESTART_DEAD:-0}" == "1" ]]; then
  is_alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }
  is_alive "$LOGDIR/benchmark_full_deepseek.pid" || run_one deepseek "$DEEPSEEK_DIR" \
    "$LOGDIR/benchmark_full_deepseek.log" "$LOGDIR/benchmark_full_deepseek.pid" "DeepSeek"
  is_alive "$LOGDIR/benchmark_full_llama70.pid" || run_one openrouter_llama70 "$LLAMA_DIR" \
    "$LOGDIR/benchmark_full_llama70.log" "$LOGDIR/benchmark_full_llama70.pid" "Llama70"
else
  run_one deepseek "$DEEPSEEK_DIR" \
    "$LOGDIR/benchmark_full_deepseek.log" "$LOGDIR/benchmark_full_deepseek.pid" "DeepSeek"
  run_one openrouter_llama70 "$LLAMA_DIR" \
    "$LOGDIR/benchmark_full_llama70.log" "$LOGDIR/benchmark_full_llama70.pid" "Llama70"
  start_monitor
fi

echo ""
echo "Defenses: none, tool_filter, repeat_user_prompt, bio_idea1_provenance"
echo "DeepSeek report: $DEEPSEEK_DIR/report.json"
echo "Llama report:    $LLAMA_DIR/report.json"
echo ""
echo "Monitor:  tail -f $LOGDIR/benchmark_monitor.log"
echo "Workers:  tail -f $LOGDIR/benchmark_full_deepseek.log"
echo "Status:   ps -p \$(cat $LOGDIR/benchmark_full_deepseek.pid),\$(cat $LOGDIR/benchmark_full_llama70.pid)"
