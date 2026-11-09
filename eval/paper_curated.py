"""Load M1 / workshop curated live profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

TASK_TYPE_OVERRIDES: dict[tuple[str, str], str] = {
    ("workspace", "user_task_32"): "file_ipi_share",
    ("workspace", "user_task_13"): "email_actions",
    ("workspace", "user_task_15"): "calendar_create",
    ("workspace", "user_task_0"): "calendar_read",
    ("workspace", "user_task_2"): "simple_query",
    ("travel", "user_task_0"): "travel_reserve",
    ("travel", "user_task_1"): "travel_multi",
    ("banking", "user_task_0"): "banking_balance",
    ("banking", "user_task_1"): "banking_transfer",
    ("slack", "user_task_0"): "slack_read",
    ("slack", "user_task_1"): "slack_post",
}


def _load_yaml(name: str) -> dict[str, Any]:
    from bio_harness.config import load_yaml

    return dict(load_yaml(name) or {})


def _sorted_user_tasks(suite_name: str) -> list[str]:
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite("v1.2.2", suite_name)
    return sorted(suite.user_tasks.keys(), key=lambda x: int(x.split("_")[-1]))


def _sorted_injection_task_ids(suite_name: str, benchmark_version: str = "v1.2.2") -> list[str]:
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite(benchmark_version, suite_name)
    return sorted(
        suite.injection_tasks.keys(),
        key=lambda task_id: int(task_id.rsplit("_", 1)[-1]),
    )


def resolve_injection_task_id(
    suite_name: str,
    logical_id: str,
    *,
    benchmark_version: str = "v1.2.2",
) -> str:
    """Map profile slot ``injection_task_N`` to the Nth task in an AgentDojo suite."""
    slot = int(logical_id.rsplit("_", 1)[-1])
    available = _sorted_injection_task_ids(suite_name, benchmark_version)
    if slot < 0 or slot >= len(available):
        raise KeyError(
            f"{logical_id!r} has no counterpart in suite {suite_name!r} "
            f"(available: {available})"
        )
    return available[slot]


def logical_injection_task_id(
    suite_name: str,
    actual_id: str,
    *,
    benchmark_version: str = "v1.2.2",
) -> str:
    """Inverse of :func:`resolve_injection_task_id` for log normalization."""
    available = _sorted_injection_task_ids(suite_name, benchmark_version)
    slot = available.index(actual_id)
    return f"injection_task_{slot}"


def build_curated_tasks(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Sample anchor + evenly-spaced tasks to hit per-suite quotas."""
    quotas: dict[str, int] = dict(profile.get("suite_quotas") or {})
    anchors: dict[str, list[str]] = {
        k: list(v) for k, v in (profile.get("anchor_tasks") or {}).items()
    }
    rows: list[dict[str, str]] = []
    for suite, quota in quotas.items():
        all_tasks = _sorted_user_tasks(suite)
        picked: list[str] = []
        for ut in anchors.get(suite, []):
            if ut in all_tasks and ut not in picked:
                picked.append(ut)
        if len(picked) < quota:
            remaining = [t for t in all_tasks if t not in picked]
            step = max(1, len(remaining) // max(1, quota - len(picked)))
            for t in remaining[::step]:
                if len(picked) >= quota:
                    break
                picked.append(t)
            idx = 0
            while len(picked) < quota and idx < len(remaining):
                if remaining[idx] not in picked:
                    picked.append(remaining[idx])
                idx += 1
        for ut in picked[:quota]:
            task_type = TASK_TYPE_OVERRIDES.get((suite, ut), f"{suite}_general")
            rows.append({"suite": suite, "user_task": ut, "task_type": task_type})
    return rows


def load_curated_profile(name: str = "m1") -> dict[str, Any]:
    cfg = _load_yaml("paper_curated.yaml")
    if name not in cfg and name == "m1_manifest_seed":
        seed = _load_yaml("stress_manifest_seed.yaml")
        if name in seed:
            cfg = {**cfg, name: seed[name]}
    if name not in cfg:
        raise KeyError(f"Unknown curated profile {name!r}; choose from {list(cfg)}")
    profile = dict(cfg[name])
    profile["tasks"] = build_curated_tasks(profile)
    profile["name"] = name
    profile["n_tasks"] = len(profile["tasks"])
    profile["n_pairs_estimate"] = (
        profile["n_tasks"]
        * len(profile.get("attacks") or [1])
        * len(profile.get("injection_tasks") or [1])
        * len(profile.get("defenses") or [1])
    )
    return profile


def scale_check(profile: dict[str, Any]) -> dict[str, Any]:
    """Compare profile against validation.md M1 thresholds."""
    n_tasks = profile.get("n_tasks", 0)
    n_pairs = profile.get("n_pairs_estimate", 0)
    return {
        "profile": profile.get("name"),
        "n_tasks": n_tasks,
        "n_pairs_estimate_per_model": n_pairs,
        "m1_tasks_ge_50": n_tasks >= 50,
        "m1_pairs_ge_150": n_pairs >= 150,
        "n_suites": len({t["suite"] for t in profile.get("tasks") or []}),
        "n_attacks": len(profile.get("attacks") or []),
        "n_injections": len(profile.get("injection_tasks") or []),
        "n_defenses": len(profile.get("defenses") or []),
        "n_models": len(profile.get("model_modes") or []),
    }
