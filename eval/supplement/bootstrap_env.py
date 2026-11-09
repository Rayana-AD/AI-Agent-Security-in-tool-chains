"""Bootstrap supplement live eval: project venv (>=3.10), secrets, PYTHONPATH."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
MIN_PYTHON = (3, 10)

_SECRET_ENV_MAP = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "huggingface_api_key": "HUGGINGFACE_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def repo_root() -> Path:
    return ROOT


def venv_python() -> Path:
    return VENV_PYTHON


def ensure_venv_python() -> None:
    """Re-exec with .venv if the current interpreter is too old (e.g. conda 3.8)."""
    _strip_third_party_agentdojo_from_pythonpath(os.environ)
    if sys.version_info >= MIN_PYTHON:
        return
    if not VENV_PYTHON.is_file():
        raise RuntimeError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required; create venv:\n"
            f"  python3.11 -m venv .venv && .venv/bin/pip install -e '.[agentdojo]'"
        )
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def _load_yaml_secrets() -> dict:
    path = ROOT / "configs" / "secrets.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _strip_third_party_agentdojo_from_pythonpath(env: dict) -> None:
    """Avoid cross-contamination between vendored AgentDojo / IPIGuard forks."""
    raw = env.get("PYTHONPATH", "")
    if not raw:
        return
    parts = [
        p
        for p in raw.split(os.pathsep)
        if p
        and "third_party/AutoDojo" not in p
        and "third_party/ipiguard" not in p
        and "third_party/InjecAgent" not in p
    ]
    if parts:
        env["PYTHONPATH"] = os.pathsep.join(parts)
    else:
        env.pop("PYTHONPATH", None)


def apply_secrets_to_env(env: dict | None = None) -> dict:
    """Map configs/secrets.yaml into process env (without overwriting existing vars)."""
    env = dict(os.environ if env is None else env)
    _strip_third_party_agentdojo_from_pythonpath(env)
    secrets = _load_yaml_secrets()
    for yaml_key, env_key in _SECRET_ENV_MAP.items():
        val = secrets.get(yaml_key)
        if val and env_key not in env:
            env[env_key] = str(val)
    # OpenAI-compatible clients (IPIGuard, InjecAgent GPTModel)
    if secrets.get("openrouter_api_key"):
        if "OPENAI_API_KEY" not in env:
            env["OPENAI_API_KEY"] = str(secrets["openrouter_api_key"])
        if "OPENAI_BASE_URL" not in env:
            env["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    elif secrets.get("deepseek_api_key"):
        if "OPENAI_API_KEY" not in env:
            env["OPENAI_API_KEY"] = str(secrets["deepseek_api_key"])
        if "OPENAI_BASE_URL" not in env:
            env["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"
    if secrets.get("deepseek_api_key") and "DEEPSEEK_API_KEY" not in env:
        env["DEEPSEEK_API_KEY"] = str(secrets["deepseek_api_key"])
    if "DEEPSEEK_BASE_URL" not in env:
        env["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
    return env


def _join_pythonpath(env: dict, *paths: Path) -> None:
    parts = [str(p) for p in paths if p.is_dir() or (p / "agentdojo").is_dir()]
    existing = env.get("PYTHONPATH", "")
    merged = os.pathsep.join([*parts, existing] if existing else parts)
    if merged:
        env["PYTHONPATH"] = merged


def env_for_bio_harness(*extra_paths: Path) -> dict:
    env = apply_secrets_to_env()
    _join_pythonpath(env, ROOT / "src", ROOT, *extra_paths)
    return env


def env_for_autodojo() -> dict:
    env = env_for_bio_harness(ROOT / "third_party" / "AutoDojo" / "agentdojo" / "src")
    env["AGENTDOJO_DEFENSE_PLUGINS"] = "eval.supplement.autodojo_plugin"
    return env


def env_for_ipiguard() -> dict:
    env = apply_secrets_to_env()
    ipi_src = ROOT / "third_party" / "ipiguard" / "agentdojo" / "src"
    ipi_run = ROOT / "third_party" / "ipiguard" / "run"
    _join_pythonpath(env, ipi_src, ipi_run, ROOT / "src", ROOT)
    return env


def env_for_injecagent() -> dict:
    env = apply_secrets_to_env()
    inj = ROOT / "third_party" / "InjecAgent"
    _join_pythonpath(env, inj, ROOT / "src", ROOT)
    env["PYTHONPATH"] = f"{inj}{os.pathsep}{env.get('PYTHONPATH', '')}"
    return env


def git_head(path: Path) -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
