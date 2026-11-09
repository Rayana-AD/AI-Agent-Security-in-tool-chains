"""Factory for harness runners and baselines."""

from __future__ import annotations

from bio_harness.config import get_harness_config
from bio_harness.harness.config import HarnessConfig
from bio_harness.harness.runner import BioHarnessRunner
from bio_harness.llm.base import LLMBackend
from bio_harness.llm.factory import build_llm


def build_runner(config_key: str, llm: LLMBackend | None = None) -> BioHarnessRunner:
    raw = get_harness_config(config_key)
    cfg = HarnessConfig.from_dict(raw)
    backend = llm or build_llm(raw.get("model_settings"))
    return BioHarnessRunner(cfg, backend)
