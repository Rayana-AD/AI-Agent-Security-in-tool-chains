"""Unit tests for M1 gated rerun stress (none-only) vs defense gates."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "run_m1_gated_rerun",
    ROOT / "scripts" / "run_m1_gated_rerun.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

check_stress = _mod.check_stress
check_defense = _mod.check_defense
evaluate_batch_gates = _mod.evaluate_batch_gates


def test_stress_fails_when_none_security_too_high():
    ok, issues, summary = check_stress(
        {"none_security": 1.0, "none_utility": 0.5, "none_ASR": 0.0},
        max_none_security=0.90,
        min_none_asr=0.10,
    )
    assert not ok
    assert summary["interpretation"].startswith("invalid")
    assert any("none security" in i and "too high" in i for i in issues)
    assert any("ASR" in i and "too low" in i for i in issues)


def test_stress_passes_when_none_asr_high():
    ok, issues, summary = check_stress(
        {"none_security": 0.0, "none_utility": 1.0, "none_ASR": 1.0},
        max_none_security=0.90,
        min_none_asr=0.10,
    )
    assert ok
    assert issues == []
    assert "valid" in summary["interpretation"]


def test_defense_skipped_when_stress_invalid_and_legacy_skip():
    gate = evaluate_batch_gates(
        {
            "none_security": 1.0,
            "none_ASR": 0.0,
            "none_utility": 0.5,
            "meta_full_security": 1.0,
            "meta_full_utility": 0.5,
            "bio_security": {},
            "meta_full_fail_mechanisms": {},
        },
        batch_key="test",
        min_retention=0.65,
        max_none_security=0.90,
        min_none_asr=0.10,
        require_stress=True,
        always_check_defense=False,
    )
    assert not gate.stress_ok
    assert not gate.defense_ok
    assert not gate.ok
    assert gate.defense_skipped
    assert any("skipped" in i.lower() for i in gate.defense_issues)


def test_defense_checked_even_when_stress_invalid_by_default():
    gate = evaluate_batch_gates(
        {
            "none_security": 1.0,
            "none_ASR": 0.0,
            "none_utility": 1.0,
            "meta_full_security": 1.0,
            "meta_full_utility": 0.5,
            "bio_security": {},
            "meta_full_fail_mechanisms": {"feature_shuffle": 1},
        },
        batch_key="test",
        min_retention=0.65,
        max_none_security=0.90,
        min_none_asr=0.10,
        require_stress=True,
        always_check_defense=True,
    )
    assert not gate.stress_ok
    assert not gate.defense_ok
    assert not gate.paper_comparable
    assert not gate.defense_skipped
    assert any("retention" in i for i in gate.defense_issues)


def test_defense_evaluated_only_after_stress_pass():
    gate = evaluate_batch_gates(
        {
            "none_security": 0.0,
            "none_ASR": 1.0,
            "none_utility": 1.0,
            "meta_full_security": 1.0,
            "meta_full_utility": 0.5,
            "bio_security": {"bio_idea1_provenance_reflection_meta_full": 1.0},
            "meta_full_fail_mechanisms": {"other_block": 1},
        },
        batch_key="test",
        min_retention=0.65,
        max_none_security=0.90,
        min_none_asr=0.10,
        require_stress=True,
    )
    assert gate.stress_ok
    assert not gate.defense_ok
    assert any("retention" in i for i in gate.defense_issues)


def test_defense_fails_on_meta_full_security_when_stress_ok():
    gate = evaluate_batch_gates(
        {
            "none_security": 0.25,
            "none_ASR": 0.75,
            "none_utility": 0.8,
            "meta_full_security": 0.5,
            "meta_full_utility": 0.6,
            "bio_security": {},
            "meta_full_fail_mechanisms": {},
        },
        batch_key="test",
        min_retention=0.65,
        max_none_security=0.90,
        min_none_asr=0.10,
        require_stress=True,
    )
    assert gate.stress_ok
    assert not gate.defense_ok
    assert any("meta_full security" in i for i in gate.defense_issues)


def test_m1_probe_profile_loads():
    from eval.paper_curated import load_curated_profile, scale_check

    p = load_curated_profile("m1_probe")
    assert p["n_tasks"] == 4
    assert p["defenses"] == ["none", "bio_04"]
    assert p.get("stress_check") is True
    sc = scale_check(p)
    assert sc["n_pairs_estimate_per_model"] == 4 * 1 * 1 * 2


def test_m1_main_5h_profile_loads():
    from eval.paper_curated import load_curated_profile, scale_check

    p = load_curated_profile("m1_main_5h")
    assert p["n_tasks"] == 50
    assert p["defenses"] == [
        "none",
        "spotlighting_with_delimiting",
        "transformers_pi_detector",
        "bio_04",
    ]
    assert "repeat_user_prompt" not in p["defenses"]
    assert p.get("stress_check") is True
    sc = scale_check(p)
    assert sc["n_pairs_estimate_per_model"] == 50 * 2 * 1 * 4
    assert sc["m1_tasks_ge_50"]


def test_m1_gated_light_profile_loads():
    from eval.paper_curated import load_curated_profile, scale_check

    p = load_curated_profile("m1_gated_light")
    assert p["n_tasks"] == 8
    assert "important_instructions_persona" in p["attacks"]
    sc = scale_check(p)
    assert sc["n_pairs_estimate_per_model"] == 8 * 2 * 1 * 4
