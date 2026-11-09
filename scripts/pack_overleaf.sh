#!/usr/bin/env bash
# Overleaf upload bundle: main.tex + references.bib + AuthorKit27/ (sty/bst) + figures.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/overleaf-bioharness.zip"
mkdir -p "$ROOT/dist"
rm -f "$OUT"
(
  cd "$ROOT"
  zip -q "$OUT" \
    main.tex \
    references.bib \
    AuthorKit27/aaai2027.sty \
    AuthorKit27/aaai2027.bst \
    BioPiP3.pdf \
    figures/paper_results/fig_end_to_end_frontier.pdf \
    figures/paper_results/fig_attack_type_tradeoff.pdf \
    figures/paper_results/fig_extended_suite_gap.pdf
)
echo "Wrote $OUT"
unzip -l "$OUT"
