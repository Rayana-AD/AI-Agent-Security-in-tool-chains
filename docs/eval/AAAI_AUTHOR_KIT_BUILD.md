# AAAI AuthorKit27 build (BioHarness)

## Files

| File | Role |
|------|------|
| `main.tex` | AAAI 2027 anonymous submission source |
| `main_tmlr.tex` | Frozen TMLR copy (pre-AAAI conversion) |
| `references.bib` | Shared bibliography |
| `AuthorKit27/aaai2027.sty`, `AuthorKit27/aaai2027.bst` | AAAI format (keep kit layout; `main.tex` points BibTeX here) |
| `AuthorKit27/` | Full AAAI kit (templates, Word, checklist) |

## Overleaf

Keep the kit under **`AuthorKit27/`**; put **`references.bib`** in the project root with `main.tex`. See **[OVERLEAF.md](./OVERLEAF.md)** or `./scripts/pack_overleaf.sh`.

## Compile (PDFLaTeX only)

**AAAI `aaai2027.sty` requires pdfLaTeX.** XeLaTeX / LuaLaTeX stop with:

```text
* pdfTeX is required to compile this document. Sorry!
```

From the repo root:

```bash
cd /Users/rayana/Desktop/AI-Safety
latexmk -pdf main.tex
```

Or manually:

```bash
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

`aaai2027.sty` sets `\bibliographystyle{aaai2027}` when `natbib` is loaded; do **not** add `\usepackage{hyperref}` or `\usepackage{balance}`.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Sorry! pdfTeX is required` | Switch engine to **pdfLaTeX** (Cursor/VS Code: recipe **AAAI: pdflatex → bibtex → pdflatex ×2** in `.vscode/settings.json`). |
| `File 'aaai2027.sty' not found` | Run from repo root; ensure `aaai2027.sty` exists in `./` or `AuthorKit27/` (see `\input@path` in `main.tex`). |
| `I couldn't open style file aaai2027.bst` | Copy `AuthorKit27/aaai2027.bst` to repo root, or run `bibtex main` from root where `aaai2027.bst` lives. |
| `File 'newtxtext.sty' not found` | Install TeX Live package: `sudo tlmgr install newtx`. |
| Undefined citations after one pass | Run **bibtex main**, then **pdflatex** twice more. |
| No **References** section / all cites are `?` | LaTeX Workshop was likely set to **pdflatex only**. Use default recipe **latexmk (pdf + bibtex)** or run `latexmk -pdf main.tex` from repo root (generates `main.bbl`). |
| Wide tables or equations in two columns | Prefer `table*` for wide tables; split long `equation` blocks with `align`; avoid `\text{...}` lists inside inline math. |
| Compiling `main_tmlr.tex` | That file still uses TMLR; use **`main.tex`** for AAAI. |

## Camera-ready switch

Replace `\usepackage[submission]{aaai2027}` with `\usepackage{aaai2027}` (no submission option), fill real `\author` / `\affiliations`, and restore acknowledgments if required.

## Workshop submission bundle

Include in one archive: `main.tex`, `references.bib`, `aaai2027.sty`, `aaai2027.bst`, all figure PDFs referenced by `\includegraphics`, and any custom `.sty` none beyond the kit.
