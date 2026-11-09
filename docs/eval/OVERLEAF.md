# Overleaf: Author Kit in `AuthorKit27/`

`main.tex` is written for the **unzipped AAAI Author Kit layout**:

- `AuthorKit27/aaai2027.sty`, `AuthorKit27/aaai2027.bst` — format files (do **not** move to root)
- `references.bib` — your paper bibliography (repo root, **not** `AuthorKit27/aaai2027.bib`)

`\input@path` finds the `.sty`; a small `\bibliographystyle` patch in `main.tex` sends BibTeX to `AuthorKit27/aaai2027.bst` (BibTeX does not use `\input@path`).

## Overleaf settings

1. **Compiler:** pdfLaTeX  
2. **Main document:** `main.tex` (project root)  
3. **Recompile** once  

## If citations are still `(?)`

Open **Logs → `main.blg`**. Success:

```text
The style file: AuthorKit27/aaai2027.bst
Database file #1: references.bib
```

Common mistakes:

| Problem | Fix |
|---------|-----|
| `I couldn't open style file aaai2027.bst` | Old `main.tex` without the patch; sync latest `main.tex` |
| `I couldn't open database file references.bib` | Upload `references.bib` next to `main.tex` |
| Kit only partially uploaded | Need `AuthorKit27/aaai2027.sty` **and** `.bst` in that folder |

## Zip upload

```bash
./scripts/pack_overleaf.sh
```

Upload `dist/overleaf-bioharness.zip` (**New Project → Upload Project**).
