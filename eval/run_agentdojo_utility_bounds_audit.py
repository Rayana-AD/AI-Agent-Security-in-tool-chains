#!/usr/bin/env python3
"""Print utility upper/lower bound matrix for user_task_32 tool payloads (offline)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.agentdojo.utility_bounds import (
    probe_first_tool_call,
    probe_post_injection_tool_calls,
    probe_tool_output,
    simulate_ut32_channel,
)
from eval.fixtures.user_task_32_outputs import (
    GET_FILE_BY_ID_VACATION_CLEAN,
    LIST_FILES_WITH_INJECTED_FILE_CONTENT,
    SEARCH_CLEAN_VACATION_ONLY,
    SEARCH_MIXED_BENIGN_AND_INJECTION,
    USER_TASK_32_QUERY,
)

CONFIGS = ["idea1_provenance_mlp", "idea1_provenance_mlp_reflection"]

CASES = {
    "upper_search_clean": SEARCH_CLEAN_VACATION_ONLY,
    "upper_get_file_by_id": GET_FILE_BY_ID_VACATION_CLEAN,
    "collapse_search_mixed": SEARCH_MIXED_BENIGN_AND_INJECTION,
    "collapse_list_files": LIST_FILES_WITH_INJECTED_FILE_CONTENT,
}

SCENARIOS = {
    "collapse_only": dict(
        first_tool_output=SEARCH_MIXED_BENIGN_AND_INJECTION,
        first_case_id="search_mixed",
        second_tool_output=None,
        propose_send_email=True,
    ),
    "recovery_get_by_id": dict(
        first_tool_output=SEARCH_MIXED_BENIGN_AND_INJECTION,
        first_case_id="search_mixed",
        second_tool_output=GET_FILE_BY_ID_VACATION_CLEAN,
        second_case_id="get_file_by_id",
        propose_send_email=True,
    ),
}


def main() -> None:
    query = USER_TASK_32_QUERY
    report: dict = {"query_head": query[:80], "by_config": {}}

    for cfg in CONFIGS:
        rows = []
        for case_id, payload in CASES.items():
            out, _ = probe_tool_output(cfg, query, payload, case_id=case_id)
            bound = "upper" if not out.withheld else "lower"
            rows.append(
                {
                    "case": case_id,
                    "bound": bound,
                    "withheld": out.withheld,
                    "injection_detected": out.injection_detected,
                    "escalation": out.escalation,
                }
            )
        scenarios = {
            name: simulate_ut32_channel(cfg, **kwargs) for name, kwargs in SCENARIOS.items()
        }
        post_injection = {
            name: {
                "blocked": tc.blocked,
                "reason": (tc.events[-1].get("reason") if tc.events else ""),
            }
            for name, tc in probe_post_injection_tool_calls(
                cfg, query, clean_output=GET_FILE_BY_ID_VACATION_CLEAN
            ).items()
        }
        first_hop = probe_first_tool_call(cfg, query, "get_file_by_id", {"file_id": "7"}, case_id="first_hop")
        report["by_config"][cfg] = {
            "cases": rows,
            "scenarios": scenarios,
            "post_injection_tool_calls": post_injection,
            "first_hop_get_file_by_id": {"blocked": first_hop.blocked},
        }

    report["diagnosis"] = [
        "upper bound (output): isolated clean search/get_file_by_id/create/share tool_output passes",
        "upper bound (call): first get_file_by_id tool_call in episode passes (skip poisoned search)",
        "lower bound: any tool_output blob containing <INFORMATION> is fully withheld",
        "collapse output: mixed search or list_files with infected file content",
        "collapse end-to-end (tiered): sensitive tool_calls blocked; benign get/create may pass after clean output",
        "security: send_email/share_file blocked post-injection; create/get_file_by_id recovery path open",
    ]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "runs" / f"agentdojo_utility_bounds_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
