#!/usr/bin/env bash
# Public GitHub / release zip: code + eval + tests, no paper LaTeX or run artifacts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGING="$(mktemp -d)"
OUT="$ROOT/dist/github-ai-agent-security-tool-chains.zip"
trap 'rm -rf "$STAGING"' EXIT

mkdir -p "$ROOT/dist"
rm -f "$OUT"

copy_tree() {
  local src="$1"
  local dst="$2"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    rsync -a \
      --exclude '.DS_Store' \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude '.pytest_cache' \
      "$src/" "$dst/"
  fi
}

# --- core ---
rsync -a \
  --exclude '.DS_Store' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.egg-info' \
  "$ROOT/src/" "$STAGING/src/"
copy_tree "$ROOT/tests" "$STAGING/tests"
copy_tree "$ROOT/configs" "$STAGING/configs"
copy_tree "$ROOT/data" "$STAGING/data"
copy_tree "$ROOT/models" "$STAGING/models"
copy_tree "$ROOT/docs" "$STAGING/docs"
copy_tree "$ROOT/scripts" "$STAGING/scripts"

mkdir -p "$STAGING/eval"
for part in agentdojo attacks fixtures supplement datasets; do
  if [[ -d "$ROOT/eval/$part" ]]; then
    copy_tree "$ROOT/eval/$part" "$STAGING/eval/$part"
  fi
done
rsync -a \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  --exclude 'datasets/cache' \
  --include '*.py' \
  --exclude '*' \
  "$ROOT/eval/" "$STAGING/eval/"

cp "$ROOT/pyproject.toml" "$STAGING/"
cp "$ROOT/README.github.md" "$STAGING/README.md"
cp "$ROOT/README.github.zh.md" "$STAGING/README.zh.md"
cp "$ROOT/docs/GITHUB_PUBLIC_RELEASE.md" "$STAGING/docs/GITHUB_PUBLIC_RELEASE.md"
cp "$ROOT/eval/supplement/AUTODOJO_INTEGRATION.md" "$STAGING/eval/supplement/" 2>/dev/null || true

# Ensure secrets template only
rm -f "$STAGING/configs/secrets.yaml"

# Trim paper-only paths if they slipped into docs copy
rm -rf "$STAGING/docs/eval/OVERLEAF.md" 2>/dev/null || true

(
  cd "$STAGING"
  zip -qr "$OUT" . \
    -x 'runs/*' \
    -x '.venv/*' \
    -x 'dist/*' \
    -x '*/third_party/*'
)

echo "Wrote $OUT"
unzip -l "$OUT" | tail -20
echo ""
echo "Next: unzip, git init, push to github.com/Rayana-AD/AI-Agent-Security-in-tool-chains"
echo "See docs/GITHUB_PUBLIC_RELEASE.md for double-blind checklist."
