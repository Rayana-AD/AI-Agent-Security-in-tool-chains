"""Unit tests for dot-product reflective provenance."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bio_harness.provenance.features import ProvenanceContext
from bio_harness.provenance.reflection_scales import (
    ReflectionSaturationScales,
    load_process_scales,
    load_scales,
)
from bio_harness.provenance.reflection_probe import (
    DotKeyProjector,
    ReflectionProbe,
    goal_alignment,
    householder_reflect,
    split_process_segments,
    stream_dot_reflect,
)

def _probe() -> ReflectionProbe:
    scales = load_scales() or ReflectionSaturationScales(
        tau_alpha=0.45,
        tau_delta=0.22,
        delta_baseline=1.05,
        stat="p75",
        source="paper_fallback",
    )
    proc = load_process_scales() or scales
    return ReflectionProbe(
        block_threshold=0.40,
        saturation_scales=scales,
        process_scales=proc,
    )
from eval.attacks.reflection_process_samples import build_samples


def test_householder_reflect_is_involutory():
    g = np.array([1.0, 0.0, 0.0])
    v = np.array([0.3, 0.7, 0.2])
    v = v / np.linalg.norm(v)
    rho = householder_reflect(v, g)
    back = householder_reflect(rho, g)
    np.testing.assert_allclose(back, v, atol=1e-6)
    assert abs(float(np.dot(g, rho)) + float(np.dot(g, v))) < 1e-5


def test_dot_projector_is_unit_and_scaled():
    proj = DotKeyProjector(dim=64)
    q = proj.project("verify bibliography arxiv ids")
    assert abs(float(np.linalg.norm(q)) - 1.0) < 1e-6
    k = proj.project("check ref.bib entries")
    score = proj.score(q, k)
    assert -1.0 <= score <= 1.0
    assert abs(score - float(np.dot(q, k)) / math.sqrt(64)) < 1e-9


def test_stream_intercepts_hemisphere_flip():
    proj = DotKeyProjector(dim=64)
    goal = "verify bibliography"
    segments = [
        "The paper is indeed real and valid.",
        "Wait! Does the arXiv ID actually exist?",
        "No! The sequential number 20172 is impossible.",
    ]
    stream = stream_dot_reflect(proj, goal, segments, flip_limit=1)
    assert stream.sign_flips >= 1
    assert stream.truncated_at is not None
    assert stream.intercept_reason == "dot_hemisphere_flip"


def test_thinking_loop_fixture_blocks_with_early_truncate():
    probe = _probe()
    sample = next(s for s in build_samples() if s["id"] == "refl_thinking_loop_arxiv")
    result = probe.analyze_process(sample["goal"], sample["process_text"])
    assert result.metrics.n_segments >= 8
    assert result.block_recommended, result.as_dict()


def test_benign_linear_verify_passes():
    probe = _probe()
    sample = next(s for s in build_samples() if s["id"] == "refl_benign_linear_verify")
    result = probe.analyze_process(sample["goal"], sample["process_text"])
    assert not result.block_recommended, result.as_dict()


def test_cross_node_drift_blocks():
    probe = _probe()
    sample = next(s for s in build_samples() if s["id"] == "refl_cross_node_drift")
    ctx = ProvenanceContext(
        user_goal=sample["goal"],
        review=sample["review"],
        tool_context=sample["tool_context"],
        proposed_tools_json=sample["proposed_tools_json"],
        node="tool_call",
    )
    result = probe.analyze_context(ctx)
    assert result.block_recommended, result.as_dict()


def test_cross_node_aligned_passes():
    probe = _probe()
    sample = next(s for s in build_samples() if s["id"] == "refl_cross_node_aligned")
    ctx = ProvenanceContext(
        user_goal=sample["goal"],
        review=sample["review"],
        tool_context=sample["tool_context"],
        proposed_tools_json=sample["proposed_tools_json"],
        node="tool_call",
    )
    result = probe.analyze_context(ctx)
    assert not result.block_recommended, result.as_dict()


def test_rational_lie_churn_blocks():
    probe = _probe()
    sample = next(s for s in build_samples() if s["id"] == "refl_rational_lie_churn")
    ctx = ProvenanceContext(
        user_goal=sample["goal"],
        review=sample["review"],
        tool_context=sample["tool_context"],
        node="tool_call",
    )
    result = probe.analyze_context(ctx, process_text=sample["process_text"])
    assert result.block_recommended, result.as_dict()


@pytest.mark.parametrize("sample", build_samples(), ids=lambda s: s["id"])
def test_fixture_expectations(sample):
    probe = _probe()
    if sample.get("process_text") and not sample.get("review"):
        result = probe.analyze_process(sample["goal"], sample["process_text"])
    else:
        ctx = ProvenanceContext(
            user_goal=sample["goal"],
            review=sample.get("review", ""),
            tool_context=sample.get("tool_context", ""),
            proposed_tools_json=sample.get("proposed_tools_json", ""),
            node="tool_call",
        )
        result = probe.analyze_context(ctx, process_text=sample.get("process_text", ""))
    assert result.block_recommended == sample["expect_block"], result.as_dict()


def test_dot_mirror_complexity_is_linear_in_segments():
    """Smoke: long trace stays fast — only dot products, no SVD."""
    import time

    probe = _probe()
    seg = "Wait! Let's check the arXiv title again against ref.bib line 202."
    long_text = " ".join([seg] * 200)
    t0 = time.perf_counter()
    result = probe.analyze_process("verify bibliography entries", long_text)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.25, f"too slow: {elapsed:.3f}s"
    assert result.metrics.n_segments >= 50
