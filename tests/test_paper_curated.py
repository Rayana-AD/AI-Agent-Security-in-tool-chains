"""Tests for M1 curated profile builder."""

from eval.paper_curated import (
    build_curated_tasks,
    load_curated_profile,
    logical_injection_task_id,
    resolve_injection_task_id,
    scale_check,
)


def test_m1_profile_task_count():
    profile = load_curated_profile("m1")
    assert profile["n_tasks"] == 50
    assert len({t["suite"] for t in profile["tasks"]}) == 4


def test_m1_scale_check_passes():
    profile = load_curated_profile("m1")
    check = scale_check(profile)
    assert check["m1_tasks_ge_50"] is True
    assert check["m1_pairs_ge_150"] is True
    assert check["n_attacks"] >= 2
    assert check["n_injections"] >= 2
    assert check["n_defenses"] >= 8


def test_workshop_profile_smaller():
    profile = load_curated_profile("workshop")
    assert profile["n_tasks"] == 11
    assert profile["n_pairs_estimate"] < 150


def test_slack_injection_task_mapping():
    assert resolve_injection_task_id("slack", "injection_task_0") == "injection_task_1"
    assert resolve_injection_task_id("slack", "injection_task_1") == "injection_task_2"
    assert resolve_injection_task_id("banking", "injection_task_0") == "injection_task_0"
    assert logical_injection_task_id("slack", "injection_task_1") == "injection_task_0"


def test_anchor_tasks_preserved():
    profile = load_curated_profile("m1")
    keys = {(t["suite"], t["user_task"]) for t in profile["tasks"]}
    assert ("workspace", "user_task_32") in keys
    assert ("travel", "user_task_0") in keys
