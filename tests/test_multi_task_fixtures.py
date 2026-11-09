"""E6 multi-task offline fixture probes."""

from __future__ import annotations

from eval.fixtures.task_fixtures import TASK_FIXTURES
from eval.paper_probe import run_multi_task_offline, security_score_from_row


def test_multi_task_meta_full_all_secure():
    rows = run_multi_task_offline("idea1_provenance_mlp_refl_meta_full")
    assert len(rows) == 4
    assert all(r["security_score"] == 1.0 for r in rows)
    for row in rows:
        fixture = TASK_FIXTURES[row["task_id"] if row["task_id"] != "user_task_0" else "travel_user_task_0"]
        if row["task_id"] == "user_task_0" and row["suite"] == "travel":
            fixture = TASK_FIXTURES["travel_user_task_0"]
        elif row["task_id"] in TASK_FIXTURES:
            fixture = TASK_FIXTURES[row["task_id"]]
        else:
            continue
        assert security_score_from_row(row, fixture) == 1.0
