#!/usr/bin/env python3
"""Run citation hallucination harness experiments."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import yaml
from tqdm import tqdm

from bio_harness.config import CONFIGS_DIR
from bio_harness.harness.graph import build_runner
from eval.attacks.citation_hallucination import write_all
from eval.citation_scripted_runner import run_literature_scripted

CONFIG_KEYS = [
    "citation_gate_only",
    "full_citation",
    "schema_only",
]


def load_spec(name: str) -> dict:
    with (CONFIGS_DIR / "ablations.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return spec["experiments"][name]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Citation hallucination harness eval")
    parser.add_argument("--experiment", default="exp_citation_hallucination")
    parser.add_argument("--config", action="append", dest="configs")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    write_all()
    spec = load_spec(args.experiment)
    configs = args.configs or spec.get("configs", CONFIG_KEYS)
    dataset_path = ROOT / "data" / "attacks" / "citation" / "citation_hallucination.jsonl"
    samples = read_jsonl(dataset_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output or (ROOT / "runs" / f"{args.experiment}_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {"experiment": args.experiment, "configs": {}, "samples": len(samples)}

    for cfg_key in configs:
        runner = build_runner(cfg_key)
        results = []
        blocked = 0
        false_allow = 0
        for sample in tqdm(samples, desc=cfg_key):
            hr = run_literature_scripted(runner, sample)
            attack_blocked = hr.blocked
            expected_block = sample.get("expected_block", not sample.get("benign", False))
            if expected_block and attack_blocked:
                blocked += 1
            if expected_block and not attack_blocked:
                false_allow += 1
            results.append(
                {
                    "id": sample["id"],
                    "attack_type": sample.get("attack_type"),
                    "benign": sample.get("benign", False),
                    "blocked": hr.blocked,
                    "expected_block": expected_block,
                    "stages": [{"node": s.node, "layer": s.layer, "passed": s.passed, "reason": s.reason} for s in hr.stages],
                }
            )
        attacks = [s for s in samples if not s.get("benign")]
        asr = false_allow / max(len(attacks), 1)
        block_rate = blocked / max(len(attacks), 1)
        benign_ok = sum(
            1 for r, s in zip(results, samples) if s.get("benign") and not r["blocked"]
        )
        benign_total = sum(1 for s in samples if s.get("benign"))
        report["configs"][cfg_key] = {
            "attack_success_rate": round(asr, 4),
            "block_rate": round(block_rate, 4),
            "benign_utility": round(benign_ok / max(benign_total, 1), 4),
        }
        with (out_dir / f"{cfg_key}_results.jsonl").open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with (out_dir / "report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
