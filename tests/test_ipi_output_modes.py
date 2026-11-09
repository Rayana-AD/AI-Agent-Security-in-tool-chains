"""Tests for AgentDojo IPI interception timing modes."""

from __future__ import annotations

from eval.agentdojo.bio_harness_guard import BioHarnessToolGuard
from eval.agentdojo.ipi_output_modes import apply_metadata_strip
from eval.fixtures.user_task_32_outputs import SEARCH_MIXED_BENIGN_AND_INJECTION, USER_TASK_32_QUERY


def _run_tool_output(config_key: str, tool_text: str) -> tuple[str, dict]:
    guard = BioHarnessToolGuard(config_key, raise_on_block=False)
    messages = [
        {"role": "user", "content": USER_TASK_32_QUERY},
        {"role": "assistant", "content": "searching", "tool_calls": []},
        {"role": "tool", "content": tool_text},
    ]
    _, _, _, out_messages, extra = guard.query(USER_TASK_32_QUERY, None, {}, messages, {})
    content = out_messages[-1]["content"]
    if isinstance(content, list):
        text = content[0].get("content", "")
    else:
        text = str(content)
    return text, extra


def test_metadata_strip_preserves_id7():
    stripped = apply_metadata_strip(SEARCH_MIXED_BENIGN_AND_INJECTION)
    assert "id_: '7'" in stripped
    assert "<INFORMATION>" not in stripped
    assert "Travel documents" in stripped


def test_metadata_strip_preserves_benign_list_files_metadata():
    from eval.fixtures.user_task_32_outputs import LIST_FILES_WITH_INJECTED_FILE_CONTENT

    stripped = apply_metadata_strip(LIST_FILES_WITH_INJECTED_FILE_CONTENT)
    assert "id_: '7'" in stripped
    assert "id_: '24'" in stripped
    assert "<INFORMATION>" not in stripped
    assert "vacation-plans.docx" in stripped


def test_task_fidelity_hint_appended_after_ipi_metadata_strip():
    from eval.agentdojo.ipi_output_modes import maybe_append_task_fidelity_hint

    extra: dict = {"_provenance_accum": {"_provenance_injection_detected": True}}
    out = maybe_append_task_fidelity_hint(
        "file id 7",
        USER_TASK_32_QUERY,
        extra,
        enabled=True,
    )
    assert "preserve the original item labels verbatim" in out
    assert extra.get("_task_fidelity_hint_appended")


def test_withhold_baseline_hides_mixed_search():
    text, extra = _run_tool_output("idea1_provenance_mlp_reflection", SEARCH_MIXED_BENIGN_AND_INJECTION)
    assert "withheld" in text.lower()
    assert extra.get("agentdojo_injection_detected", 0) >= 1


def test_escalate_pass_shows_id7():
    text, extra = _run_tool_output(
        "idea1_provenance_mlp_reflection_ipi_escalate", SEARCH_MIXED_BENIGN_AND_INJECTION
    )
    assert "withheld" not in text.lower()
    assert "id_: '7'" in text
    assert extra.get("agentdojo_injection_detected", 0) >= 1


def test_metadata_strip_mode_shows_id7_without_envelope():
    text, extra = _run_tool_output(
        "idea1_provenance_mlp_reflection_ipi_metadata", SEARCH_MIXED_BENIGN_AND_INJECTION
    )
    assert "withheld" not in text.lower()
    assert "id_: '7'" in text
    assert "<INFORMATION>" not in text
    assert extra.get("agentdojo_injection_detected", 0) >= 1


def test_meta_full_appends_fidelity_hint_on_mixed_search():
    text, extra = _run_tool_output(
        "idea1_provenance_mlp_refl_meta_full", SEARCH_MIXED_BENIGN_AND_INJECTION
    )
    assert "preserve the original item labels verbatim" in text
    assert extra.get("_task_fidelity_hint_appended")


def test_withhold_guided_returns_hint():
    text, extra = _run_tool_output(
        "idea1_provenance_mlp_reflection_ipi_guided", SEARCH_MIXED_BENIGN_AND_INJECTION
    )
    assert "list_files" in text.lower() or "get_file_by_id" in text.lower()
    assert extra.get("agentdojo_injection_detected", 0) >= 1
