"""Baseline 3: SemanticSmooth-style input paraphrase smoothing."""

from __future__ import annotations

from bio_harness.harness.runner import BioHarnessRunner
from bio_harness.harness.config import HarnessConfig
from bio_harness.llm.qwen_backend import QwenBackend


def build(llm: QwenBackend | None = None) -> BioHarnessRunner:
    cfg = HarnessConfig(
        name="semantic_smooth",
        use_shuffle_fold=False,
        use_unidirectional_gate=True,
        use_state_partition=True,
        use_cleave=True,
        use_elastic=False,
        baseline="semantic_smooth",
    )
    return BioHarnessRunner(cfg, llm or QwenBackend())
