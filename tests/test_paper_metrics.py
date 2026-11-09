"""Tests for paper_metrics significance helpers."""

from eval.paper_metrics import (
    cross_model_comparison,
    mcnemar_test,
    paired_significance_tests,
    paired_task_metrics,
)


def test_mcnemar_no_discordant():
    out = mcnemar_test(b=0, c=0)
    assert out["p_value"] == 1.0
    assert out["n_discordant"] == 0


def test_mcnemar_exact_all_improve():
    out = mcnemar_test(b=6, c=0, exact=True)
    assert out["p_value"] <= 0.05
    assert out["b"] == 6


def test_paired_significance_vs_none():
    rows = [
        {"suite": "workspace", "user_task": "user_task_0", "defense": "none", "utility": 1.0, "security": 1.0},
        {"suite": "workspace", "user_task": "user_task_0", "defense": "meta", "utility": 1.0, "security": 1.0},
        {"suite": "workspace", "user_task": "user_task_1", "defense": "none", "utility": 0.0, "security": 1.0},
        {"suite": "workspace", "user_task": "user_task_1", "defense": "meta", "utility": 1.0, "security": 1.0},
    ]
    sig = paired_significance_tests(rows, baseline_defense="none", compare_defenses=["meta"])
    comp = sig["comparisons"]["meta"]
    assert comp["n_paired"] == 2
    assert comp["utility_mcnemar"]["b"] == 1
    assert comp["utility_mcnemar"]["c"] == 0
    assert comp["utility_mcnemar"]["p_value"] == 1.0  # single discordant pair → exact p=1


def test_paired_task_metrics_includes_significance():
    rows = [
        {"suite": "w", "user_task": "t0", "defense": "none", "utility": 1.0, "security": 1.0},
        {"suite": "w", "user_task": "t0", "defense": "full", "utility": 1.0, "security": 1.0},
    ]
    metrics = paired_task_metrics(rows)
    assert "significance" in metrics
    assert "comparisons" in metrics["significance"]


def test_cross_model_comparison():
    live_by_model = {
        "deepseek": {
            "n_tasks": 2,
            "paired_metrics": {
                "defenses": {
                    "none": {"utility_mean": 0.5, "security_mean": 1.0},
                    "bio_idea1_provenance_reflection_meta_full": {
                        "utility_mean": 1.0,
                        "security_mean": 1.0,
                    },
                }
            },
        },
        "openrouter_llama70": {
            "n_tasks": 2,
            "paired_metrics": {
                "defenses": {
                    "none": {"utility_mean": 0.4, "security_mean": 1.0},
                    "bio_idea1_provenance_reflection_meta_full": {
                        "utility_mean": 0.8,
                        "security_mean": 1.0,
                    },
                }
            },
        },
    }
    out = cross_model_comparison(live_by_model)
    assert len(out["models"]) == 2
    assert out["models"][0]["utility_retention"] == 1.0  # capped at 1.0
