"""Baseline 2: THRD-inspired multi-turn temporal defense."""

from __future__ import annotations

from bio_harness.harness.runner import BioHarnessRunner
from bio_harness.harness.config import HarnessConfig
from bio_harness.llm.qwen_backend import QwenBackend


def build(llm: QwenBackend | None = None) -> BioHarnessRunner:
    cfg = HarnessConfig(
        name="thrd_style",
        use_shuffle_fold=False,
        use_unidirectional_gate=True,
        use_state_partition=True,
        use_cleave=True,
        use_elastic=False,
        baseline="thrd_style",
        use_llm_judge=False,
    )
    return BioHarnessRunner(cfg, llm or QwenBackend())
