#!/usr/bin/env bash
# Fully detached dual benchmark via Python double-fork daemon.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$ROOT/runs/agentdojo_upstream"
mkdir -p "$LOGDIR"
WRAPPER="$LOGDIR/benchmark_wrapper.log"

"$ROOT/.venv/bin/python" "$ROOT/scripts/benchmark_daemon.py" >> "$WRAPPER" 2>&1
echo "Launched via benchmark_daemon.py — see $WRAPPER and $LOGDIR/benchmark_monitor.log"

