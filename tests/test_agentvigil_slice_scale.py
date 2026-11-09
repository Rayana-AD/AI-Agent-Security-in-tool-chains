"""Scale metadata for AgentVigil injection slice."""

from eval.supplement.run_golorial_agentvigil_slice import _scale_summary


def test_scale_summary_fuzz_first():
    plan = {
        "banking": {
            "anchor_user": "user_task_0",
            "user_tasks": ["user_task_0"],
            "injection_tasks": ["injection_task_0", "injection_task_1"],
            "n_distinct_goals": 2,
            "injection_slots_mode": "manifest",
        }
    }
    scale = _scale_summary(
        plan,
        mcts_template_set="golorial6",
        skip_static_screen=True,
        screen_template_set=None,
    )
    assert scale["estimand"] == "mcts_per_injection_goal"
    assert scale["n_mcts_runs"] == 2
    assert scale["n_static_screen_agent_runs"] == 0
    assert scale["skip_static_screen"] is True


def test_scale_summary_with_screen():
    plan = {
        "banking": {
            "anchor_user": "user_task_0",
            "user_tasks": ["user_task_0"],
            "injection_tasks": ["injection_task_0"],
            "n_distinct_goals": 1,
            "injection_slots_mode": "all",
        }
    }
    scale = _scale_summary(
        plan,
        mcts_template_set="golorial6",
        skip_static_screen=False,
        screen_template_set="extended",
    )
    assert scale["n_static_screen_agent_runs"] == 12
    assert scale["n_mcts_runs"] == 1
