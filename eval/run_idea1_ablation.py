"""Idea1 channel ablation + subtle pollution experiments with fine-grained logging."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import yaml
from tqdm import tqdm

from bio_harness.config import CONFIGS_DIR
from bio_harness.harness.graph import build_runner
from eval.attacks.idea1_subtle_pollution import write_dataset as write_subtle
from eval.attacks.retry_abuse import write_dataset as write_retry_abuse
from eval.scripted_runner import run_scripted

EXPERIMENTS = [
    "exp_idea1_channel_ablation",
    "exp_idea1_subtle_pollution",
    "exp_idea1_provenance_eval",
]


def load_spec(name: str) -> dict:
    with (CONFIGS_DIR / "ablations.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return spec["experiments"][name]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_dataset(name: str) -> list[dict]:
    if name == "idea1_subtle_pollution":
        write_subtle()
        return read_jsonl(ROOT / "data" / "attacks" / "idea1_subtle_pollution.jsonl")
    if name == "idea1_channel_mixed":
        write_retry_abuse(30)
        write_subtle()
        attacks = read_jsonl(ROOT / "data" / "attacks" / "retry_abuse.jsonl")
        attacks = [s for s in attacks if s.get("attack_type") in ("state_pollution", "retry_abuse")]
        subtle = read_jsonl(ROOT / "data" / "attacks" / "idea1_subtle_pollution.jsonl")[:8]
        benign = read_jsonl(ROOT / "data" / "benign" / "agent_tasks.jsonl")[:10]
        for b in benign:
            b = dict(b)
            b.setdefault("label", "benign")
            b.setdefault("attack_type", "benign")
        return attacks + subtle + benign
    raise ValueError(f"Unknown dataset: {name}")


def run_experiment(exp_name: str) -> dict:
    spec = load_spec(exp_name)
    samples = load_dataset(spec["dataset"])
    configs = spec["configs"]
    run_dir = ROOT / "runs" / f"{exp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    summaries: list[dict] = []

    for cfg in configs:
        runner = build_runner(cfg)
        records = []
        for sample in tqdm(samples, desc=f"{exp_name}/{cfg}"):
            hr = run_scripted(runner, sample)
            is_attack = sample.get("label", "attack") != "benign"
            harmful = hr.harmful and not hr.blocked
            records.append(
                {
                    "sample_id": sample.get("id"),
                    "config": cfg,
                    "attack_type": sample.get("attack_type", "unknown"),
                    "label": sample.get("label", "attack"),
                    "blocked": hr.blocked,
                    "harmful": hr.harmful,
                    "attack_success": is_attack and harmful,
                    "fold_blocked": hr.fold_blocked,
                    "gate_blocked": hr.gate_blocked,
                    "block_layer": getattr(hr, "block_layer", ""),
                    "block_node": getattr(hr, "block_node", ""),
                    "block_reason": getattr(hr, "block_reason", ""),
                    "retries": hr.retries,
                }
            )
        all_records.extend(records)

        attacks = [r for r in records if r["label"] == "attack"]
        benign = [r for r in records if r["label"] == "benign"]
        summaries.append(
            {
                "config": cfg,
                "n": len(records),
                "n_attacks": len(attacks),
                "asr": round(sum(1 for r in attacks if r["attack_success"]) / max(len(attacks), 1), 4),
                "block_rate": round(sum(1 for r in attacks if r["blocked"]) / max(len(attacks), 1), 4),
                "fpr": round(sum(1 for r in benign if r["blocked"]) / max(len(benign), 1), 4),
                "benign_utility": round(sum(1 for r in benign if not r["blocked"]) / max(len(benign), 1), 4),
            }
        )

        with (run_dir / f"{cfg}_results.jsonl").open("w", encoding="utf-8") as f:
            for row in records:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Per attack_type × config ASR
    by_attack: dict[str, dict] = {}
    for cfg in configs:
        for at in sorted({r["attack_type"] for r in all_records}):
            sub = [r for r in all_records if r["config"] == cfg and r["attack_type"] == at and r["label"] == "attack"]
            if not sub:
                continue
            key = f"{cfg}::{at}"
            by_attack[key] = {
                "config": cfg,
                "attack_type": at,
                "n": len(sub),
                "asr": round(sum(1 for r in sub if r["attack_success"]) / len(sub), 4),
                "block_rate": round(sum(1 for r in sub if r["blocked"]) / len(sub), 4),
            }

    # Block reason distribution for idea1_only
    reason_dist = Counter(
        (r["block_layer"], r["block_reason"][:60])
        for r in all_records
        if r["config"] == "idea1_only" and r["blocked"]
    )

    report = {
        "experiment": exp_name,
        "description": spec.get("description"),
        "dataset": spec.get("dataset"),
        "n_samples": len(samples),
        "summaries": summaries,
        "by_attack_type": by_attack,
        "idea1_only_block_reasons": [{"layer": k[0], "reason": k[1], "count": v} for k, v in reason_dist.most_common(15)],
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # CSV for quick diff
    csv_lines = ["config,attack_type,n,asr,block_rate"]
    for v in by_attack.values():
        csv_lines.append(f"{v['config']},{v['attack_type']},{v['n']},{v['asr']},{v['block_rate']}")
    (run_dir / "asr_by_attack.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    report["run_dir"] = str(run_dir)
    return report


def print_findings(reports: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("IDEA1 ABLATION SUMMARY")
    print("=" * 60)
    for rep in reports:
        print(f"\n## {rep['experiment']}")
        print(f"   {rep['description']}")
        print(f"   → {rep['run_dir']}\n")
        for s in rep["summaries"]:
            print(
                f"   {s['config']:22s} ASR={s['asr']:6.1%}  block={s['block_rate']:6.1%}  "
                f"FPR={s.get('fpr', 0):6.1%}  benign_util={s.get('benign_utility', 0):6.1%}"
            )

        # Highlight leaks vs idea1_only baseline
        base = {k.split("::")[1]: v for k, v in rep["by_attack_type"].items() if k.startswith("idea1_only::")}
        print("\n   Leaks vs idea1_only (ASR > 0 on other configs):")
        found = False
        for key, v in sorted(rep["by_attack_type"].items()):
            if v["config"] == "idea1_only" or v["asr"] == 0:
                continue
            b = base.get(v["attack_type"], {})
            if v["asr"] > b.get("asr", 0):
                print(f"     {v['config']:20s} {v['attack_type']:22s} ASR={v['asr']:.1%} (idea1={b.get('asr', 0):.1%})")
                found = True
        if not found:
            print("     (none — all configs match or idea1_only also leaks)")

        if rep.get("idea1_only_block_reasons"):
            print("\n   idea1_only block layers:")
            for row in rep["idea1_only_block_reasons"][:8]:
                print(f"     [{row['layer']}] {row['reason'][:50]} ×{row['count']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Idea1 channel ablation + subtle pollution")
    parser.add_argument("--experiment", choices=EXPERIMENTS + ["all"], default="all")
    args = parser.parse_args()
    names = EXPERIMENTS if args.experiment == "all" else [args.experiment]
    reports = [run_experiment(n) for n in names]
    print_findings(reports)


if __name__ == "__main__":
    main()
