#!/usr/bin/env python3
"""Run pilot evaluation for BioHarness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tqdm import tqdm

from bio_harness.config import get_harness_config, load_yaml
from bio_harness.harness.graph import build_runner
from bio_harness.harness.runner import HarnessResult
from eval.attacks.retry_abuse import write_dataset as write_retry_abuse
from eval.datasets.benign_tasks import write_dataset as write_benign
from eval.loaders.liars_bench import load_liars_subset
from eval.loaders.mhj import load_mhj_subset
from eval.metrics import MetricsSummary, RunRecord, compute_metrics, summary_to_dict


ALL_CONFIGS = [
    "full",
    "ablation_1",
    "ablation_2",
    "ablation_3",
    "ablation_4",
    "baseline_1",
    "baseline_2",
    "baseline_3",
]


def load_samples(mode: str) -> list[dict]:
    pilot = load_yaml("pilot_mhj.yaml")
    write_retry_abuse(pilot["retry_abuse"]["count"])
    write_benign(pilot["benign"]["count"])

    retry_path = ROOT / "data" / "attacks" / "retry_abuse.jsonl"
    benign_path = ROOT / "data" / "benign" / "agent_tasks.jsonl"

    def read_jsonl(p: Path) -> list[dict]:
        rows = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    attacks = read_jsonl(retry_path)
    benign = read_jsonl(benign_path)

    if mode == "smoke":
        return attacks[:3] + benign[:3]

    mhj_n = min(pilot["mhj"]["max_conversations"], 50 if mode == "pilot" else 10)
    liars = load_liars_subset(
        pilot["liars_bench"]["subsets"],
        pilot["liars_bench"]["max_per_subset"] if mode == "pilot" else 5,
    )
    mhj = load_mhj_subset(mhj_n, pilot["mhj"]["max_turns_per_conversation"])

    if mode == "pilot":
        return attacks + mhj + liars + benign
    return attacks[:10] + mhj[:5] + liars[:5] + benign[:5]


def run_config(config_key: str, samples: list[dict], use_llm: bool = True) -> MetricsSummary:
    runner = build_runner(config_key)
    records: list[RunRecord] = []

    for sample in tqdm(samples, desc=config_key):
        if not use_llm and sample.get("scripted_outputs"):
            result = _run_scripted_only(runner, sample)
        else:
            result = runner.run(sample)

        records.append(
            RunRecord(
                sample_id=sample.get("id", "unknown"),
                label=sample.get("label", "attack"),
                config=config_key,
                blocked=result.blocked,
                harmful=result.harmful,
                escape_layer=result.escape_layer,
                latency_seconds=result.latency_seconds,
                token_prompt=result.token_prompt,
                token_completion=result.token_completion,
                attack_type=sample.get("attack_type", ""),
            )
        )

    return compute_metrics(records, config_key)


def _run_scripted_only(runner, sample: dict) -> HarnessResult:
    """Fast path using scripted outputs through full fold/gate/cleave + mock tools."""
    from bio_harness.harness.runner import HarnessResult, StageLog
    from bio_harness.tools.mock_tools import execute_tool
    import json
    import time

    t0 = time.perf_counter()
    stages = []
    blocked = False
    side_effects: list[dict] = []
    state_probe = 0
    final_output = ""

    for node in ("plan", "review", "tool_call"):
        output = sample.get("scripted_outputs", {}).get(node, "")
        fold = runner.fold.fold(output, session_id=sample.get("id", "s"), probe_count=state_probe)
        stages.append(StageLog(node=node, passed=fold.passed, reason=fold.reason, content=fold.reconstructed[:200], layer="fold"))
        if not fold.passed:
            blocked = True
            state_probe += 1
            break

        strict = runner.elastic.gate_strict(state_probe)
        gate = runner.gate.__class__(llm=runner.llm, strict=strict, use_llm_judge=runner.config.use_llm_judge)
        gate_result = gate.check(
            fold.reconstructed,
            node=node,
            user_goal=sample.get("goal", ""),
            trusted_snapshot=None,
        )
        stages.append(StageLog(node=node, passed=gate_result.passed, reason=gate_result.reason, content=fold.reconstructed[:200], layer="gate"))
        if not gate_result.passed:
            blocked = True
            state_probe += 1
            break

        cleave = runner.cleave.cleave(fold.reconstructed, enabled=runner.config.use_cleave)
        stages.append(StageLog(node=node, passed=True, reason=str(cleave.stripped_fields), layer="cleave"))
        final_output = cleave.cleaned_text

        if node == "tool_call" and cleave.tool_calls:
            for tc in cleave.tool_calls:
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

    harmful = any(se.get("harmful") for se in side_effects)

    return HarnessResult(
        success=not blocked and not harmful,
        blocked=blocked,
        harmful=harmful,
        stages=stages,
        final_output=final_output,
        side_effects=side_effects,
        probe_count=state_probe,
        latency_seconds=time.perf_counter() - t0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="BioHarness pilot runner")
    parser.add_argument("--mode", choices=["smoke", "mini", "pilot"], default="smoke")
    parser.add_argument("--config", default="full", help="Config key or 'all'")
    parser.add_argument("--no-llm", action="store_true", help="Scripted-only fast eval")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    samples = load_samples(args.mode)
    configs = ALL_CONFIGS if args.config == "all" else [args.config]

    run_dir = ROOT / "runs" / f"pilot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    for cfg in configs:
        summary = run_config(cfg, samples, use_llm=not args.no_llm)
        all_summaries.append(summary_to_dict(summary))
        with (run_dir / f"{cfg}_results.jsonl").open("w", encoding="utf-8") as f:
            for r in summary.records:
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

    out_path = Path(args.output) if args.output else run_dir / "summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"mode": args.mode, "samples": len(samples), "summaries": all_summaries}, f, indent=2)

    print(json.dumps(all_summaries, indent=2))
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
