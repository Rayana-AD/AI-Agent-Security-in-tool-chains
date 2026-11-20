# AI agent security in tool chains

This file mirrors the GitHub English README. For the full install paths and tables, use **[README.github.md](README.github.md)** (published as `README.md` on GitHub).

Quick copy-paste after clone:

```bash
pip install -e ".[dev]"
pytest -q
./scripts/github_quickstart.sh
```

**Headline AgentDojo numbers (stress-18, DeepSeek):** security **38.0% → 100%**, utility **67.6% → 92.6%** with BioHarness; **100%** security on all 24 conditions for DeepSeek and Llama-3-70B.