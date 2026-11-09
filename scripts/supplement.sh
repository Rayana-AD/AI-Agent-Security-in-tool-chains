#!/usr/bin/env bash
# Run supplement eval scripts with project .venv (Python >=3.10).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ${PY}. Create: python3.11 -m venv .venv && .venv/bin/pip install -e '.[agentdojo]'" >&2
  exit 1
fi
exec "$PY" "$@"
