"""M2 scientific rigor metrics for paper experiments."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def utility_retention(defense_util: float, baseline_util: float) -> float:
    if baseline_util <= 0:
        return 0.0 if defense_util <= 0 else 1.0
    return max(0.0, min(1.0, defense_util / baseline_util))


def security_retention(defense_sec: float) -> float:
    return max(0.0, min(1.0, defense_sec))


def pareto_hypervolume_2d(points: list[tuple[float, float]], ref: tuple[float, float] = (0.0, 0.0)) -> float:
    """2D hypervolume (maximize utility & security) with reference point ref."""
    if not points:
        return 0.0
    rx, ry = ref
    sorted_pts = sorted(set(points), key=lambda p: (p[0], p[1]), reverse=True)
    hv = 0.0
    prev_y = ry
    for x, y in sorted_pts:
        if x <= rx or y <= ry:
            continue
        hv += max(0.0, x - rx) * max(0.0, y - prev_y)
        prev_y = max(prev_y, y)
    return hv


def bootstrap_ci(
    values: list[float],
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "std": 0.0}
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    boots = []
    n = len(arr)
    for _ in range(n_boot):
        sample = arr[rng.integers(0, n, size=n)]
        boots.append(float(np.mean(sample)))
    boots_arr = np.asarray(boots)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if n > 1 else 0.0,
        "ci_low": float(np.quantile(boots_arr, alpha / 2)),
        "ci_high": float(np.quantile(boots_arr, 1 - alpha / 2)),
    }


def _chi2_sf(x: float, df: int = 1) -> float:
    """Survival function for chi-square(df). Uses regularized gamma when df=1."""
    if x <= 0:
        return 1.0
    if df == 1:
        return float(math.erfc(math.sqrt(x / 2.0)))
    # Fallback for df>1 via incomplete gamma (scipy-free, df small only)
    k = df / 2.0
    return float(math.gammaincc(k, x / 2.0))


def _binom_cdf(k: int, n: int, p: float = 0.5) -> float:
    total = 0.0
    for i in range(k + 1):
        total += math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))
    return total


def mcnemar_test(*, b: int, c: int, exact: bool | None = None) -> dict[str, Any]:
    """McNemar on discordant pairs: b=defense-only success, c=baseline-only success."""
    n_disc = b + c
    if n_disc == 0:
        return {
            "b": b,
            "c": c,
            "n_discordant": 0,
            "statistic": 0.0,
            "p_value": 1.0,
            "method": "none",
        }
    use_exact = exact if exact is not None else n_disc < 25
    if use_exact:
        lo = min(b, c)
        hi = max(b, c)
        p_one = _binom_cdf(lo, n_disc, 0.5)
        p_two = min(1.0, 2.0 * p_one)
        return {
            "b": b,
            "c": c,
            "n_discordant": n_disc,
            "statistic": float(b - c),
            "p_value": p_two,
            "method": "exact_binomial",
        }
    stat = (abs(b - c) - 1) ** 2 / n_disc
    return {
        "b": b,
        "c": c,
        "n_discordant": n_disc,
        "statistic": stat,
        "p_value": _chi2_sf(stat, df=1),
        "method": "chi2_cc",
    }


def _task_key(row: dict[str, Any]) -> tuple[str, ...]:
    parts = [
        str(row.get("suite", "")),
        str(row.get("user_task", row.get("task_id", ""))),
    ]
    if row.get("attack"):
        parts.append(str(row["attack"]))
    if row.get("injection_task"):
        parts.append(str(row["injection_task"]))
    rep = row.get("replicate")
    if rep is not None:
        parts.append(str(rep))
    return tuple(parts)


def paired_significance_tests(
    rows: list[dict[str, Any]],
    *,
    baseline_defense: str = "none",
    compare_defenses: list[str] | None = None,
) -> dict[str, Any]:
    """McNemar tests for utility/security vs baseline on matched tasks."""
    by_task_defense: dict[tuple[str, ...], dict[str, dict[str, float]]] = {}
    defenses_seen: set[str] = set()
    for row in rows:
        defense = str(row["defense"])
        defenses_seen.add(defense)
        key = _task_key(row)
        by_task_defense.setdefault(key, {})[defense] = {
            "utility": float(row["utility"]),
            "security": float(row["security"]),
        }

    targets = compare_defenses or sorted(d for d in defenses_seen if d != baseline_defense)
    out: dict[str, Any] = {"baseline_defense": baseline_defense, "comparisons": {}}
    for defense in targets:
        util_b = util_c = sec_b = sec_c = 0
        n_paired = 0
        for task_rows in by_task_defense.values():
            base = task_rows.get(baseline_defense)
            cand = task_rows.get(defense)
            if base is None or cand is None:
                continue
            n_paired += 1
            if cand["utility"] >= 0.5 and base["utility"] < 0.5:
                util_b += 1
            elif cand["utility"] < 0.5 and base["utility"] >= 0.5:
                util_c += 1
            if cand["security"] >= 0.5 and base["security"] < 0.5:
                sec_b += 1
            elif cand["security"] < 0.5 and base["security"] >= 0.5:
                sec_c += 1
        out["comparisons"][defense] = {
            "n_paired": n_paired,
            "utility_mcnemar": mcnemar_test(b=util_b, c=util_c),
            "security_mcnemar": mcnemar_test(b=sec_b, c=sec_c),
        }
    return out


def paired_task_metrics(rows: list[dict[str, Any]], *, baseline_defense: str = "none") -> dict[str, Any]:
    """Per-defense utility/security with retention vs baseline."""
    by_defense: dict[str, list[dict]] = {}
    for row in rows:
        by_defense.setdefault(row["defense"], []).append(row)

    baseline_rows = by_defense.get(baseline_defense, [])
    baseline_util = float(np.mean([r["utility"] for r in baseline_rows])) if baseline_rows else 0.0

    out: dict[str, Any] = {"baseline_defense": baseline_defense, "baseline_utility": baseline_util, "defenses": {}}
    for defense, drows in by_defense.items():
        utils = [float(r["utility"]) for r in drows]
        secs = [float(r["security"]) for r in drows]
        out["defenses"][defense] = {
            "n": len(drows),
            "utility_mean": float(np.mean(utils)) if utils else 0.0,
            "security_mean": float(np.mean(secs)) if secs else 0.0,
            "utility_retention": utility_retention(float(np.mean(utils)) if utils else 0.0, baseline_util),
            "security_retention": security_retention(float(np.mean(secs)) if secs else 0.0),
            "utility_ci": bootstrap_ci(utils),
            "security_ci": bootstrap_ci(secs),
            "pareto_points": list(zip(utils, secs)),
        }
    out["significance"] = paired_significance_tests(rows, baseline_defense=baseline_defense)
    return out


def cross_model_comparison(
    live_by_model: dict[str, dict[str, Any]],
    *,
    baseline_defense: str = "none",
    candidate: str = "bio_idea1_provenance_reflection_meta_full",
) -> dict[str, Any]:
    """Compare utility retention across models on the same curated slice."""
    models = sorted(live_by_model.keys())
    rows_out: list[dict[str, Any]] = []
    for model in models:
        block = live_by_model[model]
        metrics = block.get("paired_metrics") or {}
        defs = metrics.get("defenses") or {}
        base_u = float((defs.get(baseline_defense) or {}).get("utility_mean", 0.0))
        cand_u = float((defs.get(candidate) or {}).get("utility_mean", 0.0))
        cand_s = float((defs.get(candidate) or {}).get("security_mean", 0.0))
        rows_out.append(
            {
                "model_mode": model,
                "n_tasks": block.get("n_tasks"),
                "baseline_utility": base_u,
                f"{candidate}_utility": cand_u,
                f"{candidate}_security": cand_s,
                "utility_retention": utility_retention(cand_u, base_u),
                "security_retention": security_retention(cand_s),
            }
        )
    return {"baseline_defense": baseline_defense, "candidate": candidate, "models": rows_out}


def frontier_dominance(
    rows: list[dict[str, Any]],
    *,
    anchor: str = "tool_filter",
    candidate: str = "bio_idea1_provenance_reflection_meta_full",
) -> dict[str, Any]:
    """Compare candidate vs anchor at matched security level (approximate)."""
    by_def: dict[str, tuple[float, float]] = {}
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["defense"], []).append(row)
    for defense, drows in buckets.items():
        by_def[defense] = (
            float(np.mean([r["utility"] for r in drows])),
            float(np.mean([r["security"] for r in drows])),
        )

    anchor_u, anchor_s = by_def.get(anchor, (0.0, 0.0))
    cand_u, cand_s = by_def.get(candidate, (0.0, 0.0))
    return {
        "anchor": anchor,
        "candidate": candidate,
        "anchor_utility": anchor_u,
        "anchor_security": anchor_s,
        "candidate_utility": cand_u,
        "candidate_security": cand_s,
        "utility_delta_at_similar_security": cand_u - anchor_u,
        "security_delta": cand_s - anchor_s,
        "candidate_dominates_on_both": cand_u >= anchor_u and cand_s >= anchor_s,
    }


def module_delta_vs_full(
    module_rows: list[dict[str, Any]],
    *,
    full_id: str = "M0_full",
) -> list[dict[str, Any]]:
    full = next((r for r in module_rows if r["scheme_id"] == full_id), None)
    if not full:
        return []
    full_u = utility_score_from_row_import(full)
    full_s = security_score_from_row_import(full)
    deltas = []
    for row in module_rows:
        if row["scheme_id"] == full_id:
            continue
        u = utility_score_from_row_import(row)
        s = security_score_from_row_import(row)
        deltas.append(
            {
                "scheme_id": row["scheme_id"],
                "config_key": row["config_key"],
                "utility_delta": u - full_u,
                "security_delta": s - full_s,
                "utility_score": u,
                "security_score": s,
            }
        )
    return deltas


def utility_score_from_row_import(row: dict[str, Any]) -> float:
    from eval.paper_probe import security_score_from_row, utility_score_from_row

    return utility_score_from_row(row)


def security_score_from_row_import(row: dict[str, Any]) -> float:
    from eval.paper_probe import security_score_from_row

    return security_score_from_row(row)


def enrich_offline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from eval.paper_probe import security_score_from_row, utility_score_from_row

    out = []
    for row in rows:
        enriched = dict(row)
        enriched["utility_score"] = utility_score_from_row(row)
        enriched["security_score"] = security_score_from_row(row)
        out.append(enriched)
    return out


def hypervolume_by_group(rows: list[dict[str, Any]], group_key: str = "stage") -> dict[str, float]:
    enriched = enrich_offline_rows(rows)
    groups: dict[str, list[tuple[float, float]]] = {}
    for row in enriched:
        groups.setdefault(str(row.get(group_key, "all")), []).append(
            (row["utility_score"], row["security_score"])
        )
    return {g: pareto_hypervolume_2d(pts) for g, pts in groups.items()}
