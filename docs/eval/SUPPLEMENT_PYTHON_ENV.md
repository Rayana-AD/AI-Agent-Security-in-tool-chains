# Supplement live eval — Python environment

## Problem

System default Python may be **Anaconda 3.8** (`/opt/anaconda3/bin/python3`), which lacks `typing.Annotated` and breaks AutoDojo / IPIGuard.

## Fix (one-time)

```bash
cd /Users/rayana/Desktop/AI-Safety
python3.11 -m venv .venv          # or use existing .venv (3.13)
.venv/bin/pip install -e ".[agentdojo,supplement-live]"
.venv/bin/pip install -e third_party/ipiguard/agentdojo
```

Clone peers (already in repo):

- `third_party/AutoDojo`
- `third_party/ipiguard`
- `third_party/InjecAgent`

## Run live smokes

Always use project venv:

```bash
./scripts/supplement.sh eval/supplement/run_all_live_smokes.py
```

Or individually:

```bash
./scripts/supplement.sh eval/supplement/run_p1_autodojo_smoke.py --execute --defense bio_04
./scripts/supplement.sh eval/supplement/run_p1_injecagent_live.py --execute --max-cases 5 --defense bio_04
./scripts/supplement.sh eval/supplement/run_p2_ipiguard_live.py --execute --defense ipiguard
```

API keys: `configs/secrets.yaml` → `deepseek_api_key` (primary), optional `openrouter_api_key`.

## Notes

- **AutoDojo**: uses `eval/run_agentdojo_benchmark.py` + `autodojo_plugin` (bio_04).
- **InjecAgent**: DeepSeek native API; optional `--defense bio_04` sanitizes tool observations.
- **IPIGuard**: vendored `agentdojo` fork; DeepSeek-V3 + `defense=ipiguard` (OpenRouter GPT may 403 TOS).
- Do **not** export `PYTHONPATH` with `third_party/AutoDojo` globally — `eval/supplement/bootstrap_env.py` strips it to avoid fork conflicts.
