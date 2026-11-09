#!/usr/bin/env python3
"""Fine-grained provenance pipeline audit: per-sample stage traces."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.harness.graph import build_runner
from eval.attacks.idea1_subtle_pollution import write_dataset as write_subtle
from eval.scripted_runner import run_scripted


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_samples() -> list[dict]:
    write_subtle()
    subtle = read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution.jsonl")
    benign = read_jsonl(ROOT / "data/benign/agent_tasks.jsonl")[:10]
    for b in benign:
        b = dict(b)
        b.setdefault("label", "benign")
        b.setdefault("attack_type", "benign")
    return subtle + benign


def main() -> None:
    parser = argparse.ArgumentParser(description="Provenance pipeline fine-grained audit")
    parser.add_argument("--config", default="idea1_provenance")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: runs/provenance_audit_<ts>)",
    )
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or (ROOT / "runs" / f"provenance_audit_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = build_runner(args.config)
    samples = load_samples()

    stage_rows: list[dict] = []
    summary_rows: list[dict] = []

    for sample in samples:
        result = run_scripted(runner, sample)
        label = sample.get("label", "attack")
        attack_type = sample.get("attack_type", "")
        for stage in result.stages:
            stage_rows.append(
                {
                    "sample_id": sample.get("id"),
                    "label": label,
                    "attack_type": attack_type,
                    "node": stage.node,
                    "layer": stage.layer,
                    "passed": stage.passed,
                    "reason": stage.reason,
                }
            )
        summary_rows.append(
            {
                "sample_id": sample.get("id"),
                "label": label,
                "attack_type": attack_type,
                "blocked": result.blocked,
                "harmful": result.harmful,
                "block_layer": result.block_layer,
                "block_node": result.block_node,
                "block_reason": result.block_reason,
                "fold_blocked": result.fold_blocked,
                "gate_blocked": result.gate_blocked,
            }
        )

    stages_path = out_dir / "stage_traces.csv"
    summary_path = out_dir / "sample_summary.csv"
    with stages_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stage_rows[0].keys()))
        w.writeheader()
        w.writerows(stage_rows)
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        if row["label"] == "attack":
            by_type[row["attack_type"]].append(row)

    report = {
        "config": args.config,
        "n_samples": len(samples),
        "n_attack": sum(1 for r in summary_rows if r["label"] == "attack"),
        "n_benign": sum(1 for r in summary_rows if r["label"] == "benign"),
        "attack_block_rate": round(
            sum(1 for r in summary_rows if r["label"] == "attack" and r["blocked"])
            / max(sum(1 for r in summary_rows if r["label"] == "attack"), 1),
            4,
        ),
        "benign_fpr": round(
            sum(1 for r in summary_rows if r["label"] == "benign" and r["blocked"])
            / max(sum(1 for r in summary_rows if r["label"] == "benign"), 1),
            4,
        ),
        "by_attack_type": {},
        "block_layers": defaultdict(int),
    }
    for atype, rows in sorted(by_type.items()):
        report["by_attack_type"][atype] = {
            "n": len(rows),
            "block_rate": round(sum(1 for r in rows if r["blocked"]) / len(rows), 4),
            "layers": dict(
                defaultdict(
                    int,
                    {r["block_layer"]: 1 for r in rows if r["blocked"] and r["block_layer"]},
                )
            ),
        }
        for r in rows:
            if r["blocked"] and r["block_layer"]:
                report["block_layers"][r["block_layer"]] += 1

    report["block_layers"] = dict(report["block_layers"])
    report_path = out_dir / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Audit → {out_dir}")
    print(f"  attack block rate: {report['attack_block_rate']*100:.1f}%")
    print(f"  benign FPR:        {report['benign_fpr']*100:.1f}%")
    for atype, stats in report["by_attack_type"].items():
        print(f"  {atype}: block {stats['block_rate']*100:.1f}% ({stats['n']} samples)")


if __name__ == "__main__":
    main()
