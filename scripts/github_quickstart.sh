#!/usr/bin/env bash
# Local smoke: unit tests + one offline matrix cell (no LLM API keys).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]] && command -v python3 >/dev/null; then
  echo "Tip: create a venv and run: pip install -e \".[dev]\""
fi

echo "== [1/2] unit tests (about 1–2 min) =="
python3 -m pytest -q

echo "== [2/2] offline harness smoke: path_heldout × full BioHarness (no API) =="
python3 eval/supplement/run_official_matrix_v2.py \
  --suites path_heldout \
  --configs idea1_provenance_mlp_bio_04

echo "OK — summary: runs/supplement/p2/official_matrix_v2/matrix_summary.json"