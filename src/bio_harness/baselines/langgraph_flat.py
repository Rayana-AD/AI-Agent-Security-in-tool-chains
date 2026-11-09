"""Baseline 1: LangGraph-style flat schema, no cleave, no partition."""

from __future__ import annotations

from bio_harness.harness.runner import BioHarnessRunner
from bio_harness.harness.config import HarnessConfig
from bio_harness.llm.qwen_backend import QwenBackend


def build(llm: QwenBackend | None = None) -> BioHarnessRunner:
    cfg = HarnessConfig(
        name="langgraph_flat",
        use_shuffle_fold=False,
        use_unidirectional_gate=False,
        use_state_partition=False,
        use_cleave=False,
        use_elastic=False,
        baseline="langgraph_flat",
    )
    return BioHarnessRunner(cfg, llm or QwenBackend())
