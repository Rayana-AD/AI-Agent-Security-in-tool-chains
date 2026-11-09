"""Configuration loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = ROOT / "configs"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIGS_DIR / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_secrets() -> dict[str, Any]:
    path = CONFIGS_DIR / "secrets.yaml"
    if not path.exists():
        return {}
    return load_yaml("secrets.yaml")


def get_model_settings() -> dict[str, Any]:
    """Merged model runtime settings: model.yaml + secrets.yaml + huggingface block."""
    root = load_yaml("model.yaml")
    model = dict(root.get("model") or {})
    hf = dict(root.get("huggingface") or {})
    secrets = load_secrets()

    hf_key = (
        secrets.get("huggingface_api_key")
        or secrets.get("hf_token")
        or __import__("os").environ.get("HF_TOKEN")
        or __import__("os").environ.get("HUGGINGFACE_API_KEY")
    )
    if hf_key and str(hf_key).strip():
        model["api_key"] = str(hf_key).strip()
    if secrets.get("huggingface_api_model"):
        model["api_model"] = secrets["huggingface_api_model"]
    if secrets.get("openai_api_key"):
        model.setdefault("openai_api_key", secrets["openai_api_key"].strip())
    if secrets.get("deepseek_api_key"):
        model.setdefault("deepseek_api_key", secrets["deepseek_api_key"].strip())
    if secrets.get("openrouter_api_key"):
        model.setdefault("openrouter_api_key", secrets["openrouter_api_key"].strip())

    if hf.get("api_model"):
        model["api_model"] = hf["api_model"]
    if hf.get("base_url"):
        model["base_url"] = hf["base_url"]

    model["_huggingface"] = hf
    return model


def get_harness_config(config_key: str) -> dict[str, Any]:
    ablations = load_yaml("ablations.yaml")
    paper = load_yaml("paper_experiments.yaml")
    configs = dict(ablations.get("configs") or {})
    configs.update(paper.get("configs") or {})
    if config_key not in configs:
        raise KeyError(f"Unknown config key: {config_key}")
    cfg = configs[config_key].copy()
    cfg["model"] = load_yaml("model.yaml")
    cfg["model_settings"] = get_model_settings()
    cfg["pilot"] = load_yaml("pilot_mhj.yaml")
    return cfg
