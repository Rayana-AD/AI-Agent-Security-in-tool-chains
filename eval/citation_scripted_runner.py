"""Literature-task harness runner with citation gate integration."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bio_harness.baselines.agentdojo_defenses import DefenseBaseline, build_defense
from bio_harness.citation.gate import CitationGate
from bio_harness.citation.verify import StrictBibVerifier
from bio_harness.harness.runner import BioHarnessRunner, HarnessResult, StageLog
from bio_harness.state.partition import PartitionedState

LITERATURE_NODES = ("plan", "draft", "verify", "tool_call")


def run_literature_scripted(runner: BioHarnessRunner, sample: dict[str, Any]) -> HarnessResult:
    """Plan → Draft → Citation Verify → ToolCall with optional external defense."""
    t0 = time.perf_counter()
    state = PartitionedState(use_partition=runner.config.use_state_partition)
    state.raw.session_id = sample.get("id", "session")
    state.raw.started_at = time.time()

    stages: list[StageLog] = []
    side_effects: list[dict[str, Any]] = []
    blocked = False
    fold_blocked = False
    gate_blocked = False
    citation_blocked = False
    defense_blocked = False
    retries = 0
    final_output = ""
    node_outputs: dict[str, str] = {}

    external_defense: DefenseBaseline | None = None
    if runner.config.external_defense:
        external_defense = build_defense(runner.config.external_defense)

    metadata_overrides = sample.get("metadata_overrides")
    citation_gate = None
    if runner.config.use_citation_gate:
        allowed = set(runner.config.citation_allowed_bib_files)
        verifier = StrictBibVerifier(metadata_overrides=metadata_overrides)
        citation_gate = CitationGate(
            allowed_bib_files=allowed,
            fail_on_unknown_cite=True,
            fail_on_inline_doi_mismatch=True,
        )
        citation_gate.verifier = verifier

    for node in LITERATURE_NODES:
        attempt = 0
        node_done = False
        while not node_done:
            output = _pick_output(sample, node, attempt)
            state.raw.append_turn(node, output)
            node_outputs[node] = output

            if external_defense and node in ("draft", "verify", "tool_call"):
                d = external_defense.check_text(
                    output,
                    node,
                    {"source": sample.get("source", "internal"), "goal": sample.get("goal", "")},
                )
                stages.append(
                    StageLog(node=node, passed=d.allow, reason=d.reason, content=output[:200], layer="defense")
                )
                if not d.allow:
                    defense_blocked = True
                    blocked = True
                    node_done = True
                    break

            if node == "verify":
                if runner.config.use_citation_gate and citation_gate:
                    draft = node_outputs.get("draft", output)
                    bib_text = sample.get("bib_text", "")
                    bib_file = sample.get("bib_file")
                    if bib_file:
                        path = Path(bib_file)
                        if path.name not in citation_gate.allowed_bib_files:
                            cg = citation_gate.check(draft, bib_text=bib_text)
                        else:
                            citation_gate.bib_path = path
                            cg = citation_gate.check(draft)
                    else:
                        cg = citation_gate.check(draft, bib_text=bib_text)

                    stages.append(
                        StageLog(
                            node="citation_verify",
                            passed=cg.passed,
                            reason=cg.blocked_reason,
                            content=draft[:200],
                            layer="citation_gate",
                        )
                    )
                    if not cg.passed:
                        citation_blocked = True
                        blocked = True
                        node_done = True
                        break
                node_done = True
                continue

            fold_result = runner.fold.fold(
                output,
                session_id=state.raw.session_id,
                probe_count=state.raw.probe_count,
                node_outputs=node_outputs,
                user_goal=sample.get("goal", ""),
                current_node=node if node != "verify" else "review",
            )
            stages.append(
                StageLog(
                    node=node,
                    passed=fold_result.passed,
                    reason=fold_result.reason,
                    content=fold_result.reconstructed[:200],
                    layer="fold",
                )
            )
            if not fold_result.passed:
                fold_blocked = True
                blocked = True
                node_done = True
                break

            if runner.config.use_unidirectional_gate and node in ("draft", "tool_call"):
                strict = runner.elastic.gate_strict(state.raw.probe_count)
                gate = runner.gate.__class__(
                    llm=runner.llm,
                    strict=strict,
                    use_llm_judge=runner.config.use_llm_judge,
                )
                gate_result = gate.check(
                    fold_result.reconstructed,
                    node=node,
                    user_goal=sample.get("goal", ""),
                    trusted_snapshot=state.snapshot_trusted() if runner.config.use_state_partition else None,
                )
                stages.append(
                    StageLog(
                        node=node,
                        passed=gate_result.passed,
                        reason=gate_result.reason,
                        content=fold_result.reconstructed[:200],
                        layer="gate",
                    )
                )
                if not gate_result.passed:
                    gate_blocked = True
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
            final_output = cleave_result.cleaned_text

            if node == "tool_call" and cleave_result.tool_calls and external_defense:
                for tc in cleave_result.tool_calls:
                    tool_name = tc.get("tool") or tc.get("action", "")
                    args = tc.get("args") or tc.get("parameters", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"raw": args}
                    d = external_defense.check_tool_call(
                        str(tool_name),
                        args if isinstance(args, dict) else {},
                        {"source": sample.get("source", "internal")},
                    )
                    stages.append(
                        StageLog(node=node, passed=d.allow, reason=d.reason, layer="defense")
                    )
                    if not d.allow:
                        defense_blocked = True
                        blocked = True
                        break

            node_done = True

        if blocked:
            break

    harmful = any(se.get("harmful") for se in side_effects)
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
        fold_blocked=fold_blocked,
        gate_blocked=gate_blocked or citation_blocked or defense_blocked,
    )


def _pick_output(sample: dict, node: str, attempt: int) -> str:
    if attempt > 0:
        retry = sample.get("scripted_retries", {}).get(node)
        if retry:
            return retry
    return sample.get("scripted_outputs", {}).get(node, "")
