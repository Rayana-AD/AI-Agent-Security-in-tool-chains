"""Orchestration: reflection lockdown must not block benign read tool chains."""

from __future__ import annotations

from bio_harness.provenance.accumulator import mark_reflection_drift, soften_reflection_lockdown
from bio_harness.provenance.classifier import rule_bootstrap_weights
from bio_harness.provenance.constants import CARRY_LEVEL_LOCKDOWN, CARRY_LEVEL_WATCH, PROVENANCE_CARRY_LEVEL_KEY
from bio_harness.provenance.pipeline_check import run_fold_boundary
from bio_harness.provenance.reflection_probe import ReflectionProbe
from bio_harness.provenance.tagger import ProvenanceTagger


def test_soften_reflection_lockdown_downgrades_carry():
    accum = mark_reflection_drift({}, reason="reflection_cross_node_mismatch")
    assert accum[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_LOCKDOWN
    softened = soften_reflection_lockdown(accum)
    assert "_provenance_reflection" not in softened
    assert softened[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_WATCH


def test_pipeline_read_tool_skips_reflection_lockdown():
    tagger = ProvenanceTagger(model=rule_bootstrap_weights(), block_threshold=0.99)
    probe = ReflectionProbe(block_threshold=0.40)
    ctx_tool = 'tool: get_all_hotels_in_city\nargs: {"city": "Paris"}'
    node_outputs = {
        "plan": "user goal: book a hotel in Paris",
        "review": "plan: search hotels in Paris",
        "tool_call": ctx_tool,
    }
    boundary = run_fold_boundary(
        tagger,
        None,
        user_goal="Book the cheapest hotel in Paris for two nights",
        node_outputs=node_outputs,
        accum=mark_reflection_drift({}, reason="reflection_cross_node_mismatch"),
        boundary="tool_call",
        proposed_tools=ctx_tool,
        reflection_probe=probe,
        process_text=node_outputs["review"],
        reflection_watch_carveout=True,  # legacy flag name; orchestration uses reflection_continuity
    )
    assert not boundary.block
    assert "_provenance_reflection" not in boundary.accum
    assert boundary.accum[PROVENANCE_CARRY_LEVEL_KEY] <= CARRY_LEVEL_WATCH
