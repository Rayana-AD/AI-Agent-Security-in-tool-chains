"""Faithful scripted harness runner for factorial experiments."""

from __future__ import annotations

import json
import time
from typing import Any

from bio_harness.harness.runner import BioHarnessRunner, HarnessResult, StageLog
from bio_harness.provenance.pipeline_check import run_provenance_boundary
from bio_harness.provenance.reflection_probe import get_reflection_probe
from bio_harness.provenance.tagger import get_tagger
from bio_harness.state.partition import PartitionedState
from bio_harness.tools.mock_tools import execute_tool


def run_scripted(runner: BioHarnessRunner, sample: dict[str, Any]) -> HarnessResult:
    """Run Plan→Review→ToolCall with partition, retry, cleave, and Idea2 fold modes."""
    t0 = time.perf_counter()
    state = PartitionedState(use_partition=runner.config.use_state_partition)
    state.raw.session_id = sample.get("id", "session")
    state.raw.started_at = time.time()

    stages: list[StageLog] = []
    side_effects: list[dict[str, Any]] = []
    blocked = False
    fold_blocked = False
    gate_blocked = False
    escape_layer = ""
    retries = 0
    final_output = ""
    node_idx = 0
    fold_mode = sample.get("fold_mode", "single_node")
    node_outputs: dict[str, str] = {}
    provenance_tagger = get_tagger(runner.config)
    reflection_probe = get_reflection_probe(runner.config)
    feature_shuffle_checker = None
    if provenance_tagger is not None and runner.config.use_feature_shuffle:
        from bio_harness.provenance.feature_shuffle import make_feature_shuffle_checker

        feature_shuffle_checker = make_feature_shuffle_checker(provenance_tagger.model, runner.config)

    external = sample.get("external_untrusted", "")
    if isinstance(external, (list, tuple)):
        external = "\n".join(str(x) for x in external)
    external = str(external)
    if external and sample.get("requires_external_fold"):
        ext_fold = runner.fold.fold(
            external,
            session_id=state.raw.session_id,
            probe_count=state.raw.probe_count,
        )
        stages.append(
            StageLog(
                node="external",
                passed=ext_fold.passed,
                reason=ext_fold.reason,
                content=ext_fold.reconstructed[:200],
                layer="fold",
            )
        )
        if not ext_fold.passed:
            fold_blocked = True
            blocked = True
            return _result(
                blocked, fold_blocked, gate_blocked, stages, side_effects,
                final_output, state, retries, t0, escape_layer,
            )
        state.raw.append_turn("external", external)
        for line in external.splitlines():
            ll = line.lower()
            if any(k in ll for k in ("ignore", "override", "secrets.env", "restricted")):
                state.merge_global_pollution("_external_hint", line)

    while node_idx < len(runner.NODES):
        node = runner.NODES[node_idx]
        attempt = 0
        node_done = False

        while not node_done:
            output = _pick_output(sample, node, attempt, state, runner, node_outputs)
            state.raw.append_turn(node, output)
            node_outputs[node] = output

            fold_result = runner.fold.fold(
                output,
                session_id=state.raw.session_id,
                probe_count=state.raw.probe_count,
                node_outputs=node_outputs,
                user_goal=sample.get("goal", ""),
                current_node=node,
            )
            fold_label = node if sample.get("fold_mode") != "cross_node" else f"merged_through_{node}"

            stages.append(
                StageLog(
                    node=fold_label,
                    passed=fold_result.passed,
                    reason=fold_result.reason,
                    content=fold_result.reconstructed[:200],
                    layer="fold",
                )
            )
            if not fold_result.passed:
                fold_blocked = True
                state.raw.probe_count += 1
                ok, _ = runner.retry_policy.can_retry(retries, state.raw.started_at)
                if ok and runner.config.use_unidirectional_gate:
                    retries += 1
                    attempt += 1
                    retry_out = sample.get("scripted_retries", {}).get(node)
                    if retry_out:
                        continue
                    blocked = True
                    node_done = True
                    break
                blocked = True
                node_done = True
                break

            if provenance_tagger is not None:
                if node in ("plan", "review"):
                    prov_tag = provenance_tagger.tag_from_nodes(
                        sample.get("goal", ""),
                        node_outputs,
                        current_text=fold_result.reconstructed,
                        node=node,
                    )
                    provenance_tagger.apply_to_state(state, prov_tag, node=node)
                    stages.append(
                        StageLog(
                            node=node,
                            passed=True,
                            reason=prov_tag.reason,
                            content=fold_result.reconstructed[:120],
                            layer="provenance",
                        )
                    )
                elif node == "tool_call":
                    accum = getattr(state, "_global", {})
                    boundary = run_provenance_boundary(
                        provenance_tagger,
                        feature_shuffle_checker,
                        user_goal=sample.get("goal", ""),
                        node_outputs=node_outputs,
                        accum=accum,
                        boundary="tool_call",
                        current_text=fold_result.reconstructed,
                        proposed_tools=fold_result.reconstructed,
                        include_tool_output_shuffle=True,
                        reflection_probe=reflection_probe,
                        process_text=node_outputs.get("review", ""),
                    )
                    for k, v in boundary.accum.items():
                        state.merge_global_pollution(k, v)
                    for fs_node, fs_result in boundary.feature_shuffle_results or []:
                        stages.append(
                            StageLog(
                                node=f"{node}/{fs_node}",
                                passed=fs_result.passed,
                                reason=fs_result.reason or "feature_shuffle_ok",
                                content=fold_result.reconstructed[:120],
                                layer="feature_shuffle",
                            )
                        )
                    stages.append(
                        StageLog(
                            node=node,
                            passed=not boundary.block,
                            reason=boundary.block_reason or boundary.prov_reason,
                            content=fold_result.reconstructed[:120],
                            layer=boundary.block_layer or "provenance",
                        )
                    )
                    if boundary.block:
                        gate_blocked = True
                        blocked = True
                        node_done = True
                        break

            strict = runner.elastic.gate_strict(state.raw.probe_count)
            gate_nodes = runner.config.gate_nodes or runner.NODES
            gate_content = fold_result.reconstructed
            if node not in gate_nodes:
                from bio_harness.gate.predicates import GateResult
                gate_result = GateResult(passed=True, reason="gate_skipped_for_node", layer="gate")
            else:
                gate = runner.gate.__class__(
                    llm=runner.llm,
                    strict=strict,
                    use_llm_judge=runner.config.use_llm_judge,
                )
                trusted_snap = (
                    state.snapshot_for_gate()
                    if runner.config.use_state_partition
                    else _global_pollution_view(state)
                )
                gate_result = gate.check(
                    gate_content,
                    node=node,
                    user_goal=sample.get("goal", ""),
                    trusted_snapshot=trusted_snap,
                )
            stages.append(
                StageLog(
                    node=node,
                    passed=gate_result.passed,
                    reason=gate_result.reason,
                    content=gate_content[:200],
                    layer="gate",
                )
            )
            if not gate_result.passed:
                gate_blocked = True
                state.raw.probe_count += 1
                ok, _ = runner.retry_policy.can_retry(retries, state.raw.started_at)
                if ok and runner.config.use_unidirectional_gate:
                    retries += 1
                    attempt += 1
                    continue
                blocked = True
                node_done = True
                break

            cleave_result = runner.cleave.cleave(
                fold_result.reconstructed,
                enabled=runner.config.use_cleave,
            )
            stages.append(
                StageLog(
                    node=node,
                    passed=True,
                    reason=str(cleave_result.stripped_fields),
                    layer="cleave",
                )
            )

            if runner.config.use_state_partition:
                state.write_trusted(
                    facts=cleave_result.facts,
                    tool_calls=cleave_result.tool_calls,
                    plans=cleave_result.plans,
                    authorized=True,
                )
            else:
                state.write_trusted(
                    facts=cleave_result.facts,
                    tool_calls=cleave_result.tool_calls,
                    plans=cleave_result.plans,
                    authorized=True,
                )
                for field in cleave_result.stripped_fields:
                    state.merge_global_pollution(field, fold_result.reconstructed)
                for line in fold_result.reconstructed.splitlines():
                    ll = line.lower()
                    if "_routing_hint" in ll or "signal_peptide" in ll:
                        state.merge_global_pollution("_routing_hint", line)

            final_output = cleave_result.cleaned_text

            if node == "tool_call" and cleave_result.tool_calls:
                for tc in cleave_result.tool_calls:
                    tool_name = tc.get("tool") or tc.get("action", "")
                    args = tc.get("args") or tc.get("parameters", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"raw": args}
                    result = execute_tool(str(tool_name), args if isinstance(args, dict) else {})
                    if result.side_effect:
                        side_effects.append(result.side_effect)

            node_done = True

        if blocked:
            break
        node_idx += 1

    return _result(
        blocked, fold_blocked, gate_blocked, stages, side_effects,
        final_output, state, retries, t0, escape_layer,
    )


def _result(
    blocked: bool,
    fold_blocked: bool,
    gate_blocked: bool,
    stages: list[StageLog],
    side_effects: list[dict],
    final_output: str,
    state: PartitionedState,
    retries: int,
    t0: float,
    escape_layer: str,
) -> HarnessResult:
    harmful = any(se.get("harmful") for se in side_effects)
    block_reason = ""
    block_layer = ""
    block_node = ""
    if blocked:
        failed = [s for s in stages if not s.passed]
        if failed:
            block_reason = failed[-1].reason
            block_layer = failed[-1].layer
            block_node = failed[-1].node
        elif harmful:
            block_reason = "harmful_side_effect"
            block_layer = "downstream"
            block_node = "tool_call"
    return HarnessResult(
        success=not blocked and not harmful,
        blocked=blocked,
        harmful=harmful,
        stages=stages,
        final_output=final_output,
        side_effects=side_effects,
        probe_count=state.raw.probe_count,
        retries=retries,
        latency_seconds=time.perf_counter() - t0,
        escape_layer=escape_layer,
        fold_blocked=fold_blocked,
        gate_blocked=gate_blocked,
        block_reason=block_reason,
        block_layer=block_layer,
        block_node=block_node,
    )


def _pick_output(
    sample: dict,
    node: str,
    attempt: int,
    state: PartitionedState,
    runner: BioHarnessRunner,
    node_outputs: dict[str, str] | None = None,
) -> str:
    if attempt > 0:
        retry = sample.get("scripted_retries", {}).get(node)
        if retry:
            return retry

    base = sample.get("scripted_outputs", {}).get(node, "")

    if node == "tool_call" and sample.get("pollution_effect"):
        if _pollution_should_apply(sample, state, runner, node_outputs):
            return sample["pollution_effect"].get("tool_call", base)

    return base


def _untrusted_channel_text(sample: dict, node_outputs: dict[str, str] | None) -> str:
    """Plan/review text seen so far, including retry rewrites."""
    if node_outputs:
        return f"{node_outputs.get('plan', '')}\n{node_outputs.get('review', '')}"
    outputs = sample.get("scripted_outputs", {})
    retries = sample.get("scripted_retries", {})
    plan = retries.get("plan") or outputs.get("plan", "")
    review = retries.get("review") or outputs.get("review", "")
    return f"{plan}\n{review}"


def _pollution_should_apply(
    sample: dict,
    state: PartitionedState,
    runner: BioHarnessRunner,
    node_outputs: dict[str, str] | None = None,
) -> bool:
    """Apply pollution tool when channel drift / escalation signals are present."""
    from bio_harness.provenance.path_patterns import ESCALATION_MARKERS, ROUTING_METADATA_RE

    if not runner.config.use_state_partition:
        return True
    global_poll = getattr(state, "_global", {})
    if global_poll.get("_provenance_injection_detected"):
        return True
    if global_poll.get("_provenance_drift") or global_poll.get("_provenance_carry"):
        return True
    if global_poll.get("_routing_hint") or global_poll.get("_external_hint"):
        return True
    if any("routing" in str(k).lower() for k in global_poll):
        return True
    untrusted = _untrusted_channel_text(sample, node_outputs)
    untrusted_l = untrusted.lower()
    if ROUTING_METADATA_RE.search(untrusted):
        return True
    if "session_target:" in untrusted_l:
        return True
    if any(m in untrusted_l for m in ESCALATION_MARKERS):
        return True
    return False


def _global_pollution_view(state: PartitionedState) -> dict[str, Any]:
    snap = state.snapshot_trusted()
    snap["_global_pollution"] = getattr(state, "_global", {})
    return snap
