#!/usr/bin/env python3
"""Provenance generalization audit: in-distribution vs held-out vs rules-off."""

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
from eval.attacks.idea1_subtle_pollution import write_dataset as write_in_dist
from eval.attacks.idea1_subtle_pollution_heldout import write_dataset as write_heldout
from eval.scripted_runner import run_scripted


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_benign(limit: int = 10) -> list[dict]:
    path = ROOT / "data/benign/agent_tasks.jsonl"
    rows = read_jsonl(path)[:limit]
    for b in rows:
        b = dict(b)
        b.setdefault("label", "benign")
        b.setdefault("attack_type", "benign")
    return rows


def summarize(records: list[dict], *, label_filter: str | None = None) -> dict:
    rows = records if label_filter is None else [r for r in records if r["label"] == label_filter]
    if not rows:
        return {"n": 0}
    attacks = [r for r in rows if r["label"] == "attack"]
    benign = [r for r in rows if r["label"] == "benign"]
    return {
        "n": len(rows),
        "n_attack": len(attacks),
        "n_benign": len(benign),
        "attack_block_rate": round(sum(1 for r in attacks if r["blocked"]) / max(len(attacks), 1), 4),
        "benign_fpr": round(sum(1 for r in benign if r["blocked"]) / max(len(benign), 1), 4),
        "block_layers": dict(
            defaultdict(
                int,
                {r["block_layer"]: 1 for r in attacks if r["blocked"] and r.get("block_layer")},
            )
        ),
    }


def run_suite(config: str, samples: list[dict], *, suite_name: str) -> list[dict]:
    runner = build_runner(config)
    records = []
    for sample in samples:
        hr = run_scripted(runner, sample)
        is_attack = sample.get("label", "attack") != "benign"
        records.append(
            {
                "suite": suite_name,
                "config": config,
                "sample_id": sample.get("id"),
                "label": sample.get("label", "attack"),
                "attack_type": sample.get("attack_type", ""),
                "blocked": hr.blocked,
                "block_layer": getattr(hr, "block_layer", ""),
                "block_reason": getattr(hr, "block_reason", ""),
                "attack_success": is_attack and hr.harmful and not hr.blocked,
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Provenance generalization audit")
    parser.add_argument(
        "--configs",
        nargs="+",
        default=["idea1_provenance_mlp", "idea1_provenance_mlp_no_rules"],
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    write_in_dist()
    write_heldout()
    in_dist = read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution.jsonl")
    held_out = read_jsonl(ROOT / "data/attacks/idea1_subtle_pollution_heldout.jsonl")
    benign = load_benign()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or (ROOT / "runs" / f"provenance_generalization_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    report: dict = {"configs": args.configs, "suites": {}}

    for config in args.configs:
        report["suites"][config] = {}
        for suite_name, samples in (
            ("in_distribution", in_dist + benign),
            ("held_out", held_out + benign),
        ):
            records = run_suite(config, samples, suite_name=suite_name)
            all_records.extend(records)
            atk = summarize(records, label_filter="attack")
            ben = summarize(records, label_filter="benign")
            by_type: dict[str, dict] = defaultdict(lambda: {"n": 0, "blocked": 0})
            for r in records:
                if r["label"] != "attack":
                    continue
                by_type[r["attack_type"]]["n"] += 1
                by_type[r["attack_type"]]["blocked"] += int(r["blocked"])
            report["suites"][config][suite_name] = {
                "attacks": atk,
                "benign": ben,
                "by_attack_type": {
                    k: {
                        "n": v["n"],
                        "block_rate": round(v["blocked"] / max(v["n"], 1), 4),
                    }
                    for k, v in sorted(by_type.items())
                },
            }

    csv_path = out_dir / "records.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_records[0].keys()))
        w.writeheader()
        w.writerows(all_records)

    report_path = out_dir / "generalization_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Generalization audit → {out_dir}\n")
    for config in args.configs:
        print(f"## {config}")
        for suite_name in ("in_distribution", "held_out"):
            s = report["suites"][config][suite_name]
            atk = s["attacks"]
            ben = s["benign"]
            print(
                f"  [{suite_name}] attack_block={atk.get('attack_block_rate', 0)*100:.1f}% "
                f"benign_fpr={ben.get('benign_fpr', 0)*100:.1f}% "
                f"layers={atk.get('block_layers', {})}"
            )
            for atype, stats in s.get("by_attack_type", {}).items():
                print(f"    {atype}: {stats['block_rate']*100:.0f}% ({stats['n']})")
        print()


if __name__ == "__main__":
    main()
