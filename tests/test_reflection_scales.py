"""Reflection saturation scales from empirical (Δα, δ) pairs."""

from __future__ import annotations

import pytest

from bio_harness.provenance.reflection_scales import (
    PAPER_TAU_ALPHA,
    PAPER_TAU_DELTA_EXCESS,
    ReflectionSaturationScales,
    scales_from_pairs,
)


def test_scales_from_pairs_excess_delta():
    pairs = [(0.04, 1.1), (0.06, 1.2), (0.08, 1.3), (0.10, 1.25)]
    s = scales_from_pairs(pairs, stat="median")
    assert s.delta_baseline == 1.225  # median δ
    assert s.tau_alpha == 0.07
    # Excesses vs baseline 1.225: 0, 0, 0.075, 0.025 → median excess 0.0125, stat median
    assert s.norm_shift(1.1) == 0.0
    assert s.norm_alpha(0.035) < 1.0


def test_eq7_additive_fuses_hat_alpha_and_hat_delta():
    s = ReflectionSaturationScales(
        tau_alpha=0.10,
        tau_delta=0.20,
        delta_baseline=1.10,
    )
    # Low Δα, low excess → low sum
    assert s.step_fused(0.02, 1.12) < 0.4
    # High Δα alone contributes fully to sum (not capped by min with small δ̂)
    assert s.step_fused(0.08, 1.12) == pytest.approx(0.9, abs=1e-6)
    # High excess δ̂ adds to low α̂
    assert s.step_fused(0.02, 1.45) == pytest.approx(1.0, abs=1e-6)


def test_scales_empty_falls_back_to_paper():
    s = scales_from_pairs([], stat="median")
    assert s.tau_alpha == PAPER_TAU_ALPHA
    assert s.tau_delta == PAPER_TAU_DELTA_EXCESS
    assert s.source == "paper_fallback"
