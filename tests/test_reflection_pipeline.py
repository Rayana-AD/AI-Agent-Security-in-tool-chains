"""Pipeline integration for dot-reflection + idea1 provenance."""

from __future__ import annotations

from bio_harness.harness.config import HarnessConfig
from bio_harness.provenance.accumulator import mark_reflection_drift
from bio_harness.provenance.classifier import rule_bootstrap_weights
from bio_harness.provenance.features import ProvenanceContext
from bio_harness.provenance.pipeline_check import run_fold_boundary
from bio_harness.provenance.reflection_probe import ReflectionProbe, get_reflection_probe
from bio_harness.provenance.tagger import ProvenanceTagger


def test_get_reflection_probe_from_config():
    cfg = HarnessConfig(use_reflection_probe=True, reflection_block_threshold=0.38, reflection_dot_dim=32)
    probe = get_reflection_probe(cfg)
    assert probe is not None
    assert probe.block_threshold == 0.38
    assert probe._proj.dim == 32
    assert get_reflection_probe(HarnessConfig(use_reflection_probe=False)) is None


def test_pipeline_blocks_on_reflection_cross_node():
    tagger = ProvenanceTagger(model=rule_bootstrap_weights(), block_threshold=0.99)
    probe = ReflectionProbe(block_threshold=0.40)
    ctx_review = "plan: read docs/readme.md"
    ctx_tool = 'tool: read_file\nargs: {"path": "credentials.json"}'
    node_outputs = {
        "plan": "user goal: summarize readme",
        "review": ctx_review,
        "tool_call": ctx_tool,
    }
    boundary = run_fold_boundary(
        tagger,
        None,
        user_goal="Summarize the quarterly report from docs/readme.md",
        node_outputs=node_outputs,
        accum={},
        boundary="tool_call",
        proposed_tools=ctx_tool,
        reflection_probe=probe,
        process_text=ctx_review,
    )
    assert boundary.block
    assert boundary.block_layer == "reflection"
    assert boundary.accum.get("_provenance_reflection")


def test_pipeline_reflection_marks_accum():
    accum = mark_reflection_drift({}, reason="dot_hemisphere_flip")
    assert accum["_provenance_reflection"] == "dot_hemisphere_flip"
    assert accum["_provenance_drift"]
