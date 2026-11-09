"""Build LLM backend from config / environment."""

from __future__ import annotations

import os
from typing import Any

from bio_harness.llm.base import LLMBackend
from bio_harness.llm.openai_backend import OpenAICompatibleBackend
from bio_harness.llm.qwen_backend import QwenBackend

HF_DEFAULT_BASE_URL = "https://router.huggingface.co/v1"


def build_llm(model_cfg: dict[str, Any] | None = None, *, backend: str | None = None) -> LLMBackend:
    """Create backend.

    Priority:
      1. explicit `backend` arg
      2. env LLM_BACKEND
      3. model.yaml model.backend
      4. default "local"

    API keys: configs/secrets.yaml > env (HF_TOKEN / OPENAI_API_KEY)
    """
    if model_cfg is None:
        from bio_harness.config import get_model_settings

        model_cfg = get_model_settings()

    cfg = dict(model_cfg)
    name = (backend or os.environ.get("LLM_BACKEND") or cfg.get("backend") or "local").lower()

    if name in ("huggingface", "hf"):
        api_key = (
            (cfg.get("api_key") or "").strip()
            or os.environ.get("HF_TOKEN", "").strip()
            or os.environ.get("HUGGINGFACE_HUB_TOKEN", "").strip()
        )
        hf_block = cfg.get("_huggingface") or {}
        return OpenAICompatibleBackend(
            model=cfg.get("api_model") or hf_block.get("api_model") or "Qwen/Qwen3-32B-Instruct",
            base_url=cfg.get("base_url") or hf_block.get("base_url") or HF_DEFAULT_BASE_URL,
            api_key=api_key or None,
            temperature=float(cfg.get("temperature", 0.7)),
            max_new_tokens=int(cfg.get("max_new_tokens", 512)),
        )

    if name in ("openai", "api", "openai_compatible"):
        api_key = (
            (cfg.get("api_key") or "").strip()
            or (cfg.get("openai_api_key") or "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )
        return OpenAICompatibleBackend(
            model=cfg.get("api_model") or os.environ.get("OPENAI_MODEL"),
            base_url=cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL"),
            api_key=api_key or None,
            temperature=float(cfg.get("temperature", 0.7)),
            max_new_tokens=int(cfg.get("max_new_tokens", 512)),
        )

    if name in ("local", "qwen", "transformers"):
        return QwenBackend(
            model_path=cfg.get("path") or os.environ.get("MODEL"),
            device=cfg.get("device") or os.environ.get("LLM_DEVICE"),
            temperature=float(cfg.get("temperature", 0.7)),
            max_new_tokens=int(cfg.get("max_new_tokens", 512)),
            seed=int(cfg.get("seed", 42)),
        )

    if name in ("openrouter", "openrouter_llama70") or name.startswith("openrouter_"):
        from bio_harness.config import load_yaml

        providers = load_yaml("model.yaml").get("providers") or {}
        pcfg = providers.get(name) or {}
        secret_key = "openrouter_api_key"
        api_key = (
            (cfg.get(secret_key) or "").strip()
            or os.environ.get("OPENROUTER_API_KEY", "").strip()
        )
        return OpenAICompatibleBackend(
            model=cfg.get("api_model") or pcfg.get("api_model"),
            base_url=cfg.get("base_url") or pcfg.get("base_url") or "https://openrouter.ai/api/v1",
            api_key=api_key or None,
            temperature=float(cfg.get("temperature", 0.0)),
            max_new_tokens=int(cfg.get("max_new_tokens", 512)),
        )

    raise ValueError(f"Unknown LLM backend: {name}. Use local, openai, huggingface, or openrouter_*.")


def check_huggingface_config() -> dict[str, Any]:
    """Quick sanity check for HF setup (no network call)."""
    from bio_harness.config import get_model_settings

    cfg = get_model_settings()
    backend = (cfg.get("backend") or "local").lower()
    key = (cfg.get("api_key") or os.environ.get("HF_TOKEN") or "").strip()
    return {
        "backend": backend,
        "api_model": cfg.get("api_model") or (cfg.get("_huggingface") or {}).get("api_model"),
        "base_url": cfg.get("base_url") or HF_DEFAULT_BASE_URL,
        "has_api_key": bool(key),
        "key_prefix": (key[:8] + "...") if len(key) > 8 else "(empty)",
    }
