#!/usr/bin/env python3
"""P0: Export Task Shield / MELON peer comparison from existing progress JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.supplement.results_store import SupplementRunStore

PEER_PROGRESS = ROOT / "runs" / "paper_peer_baselines_deepseek_progress.json"
MAIN_PROGRESS = ROOT / "runs" / "paper_m1_manifest_seed_bio_elastic_progress.json"
DEFAULT_EXPERIMENT_ID = "peer_deepseek_24cond"


def _macro(rows: list[dict], u_key: str, s_key: str) -> dict[str, float]:
    if not rows:
        return {"utility": 0.0, "security": 0.0, "n": 0}
    return {
        "n": len(rows),
        "utility": round(sum(r[u_key] or 0 for r in rows) / len(rows), 4),
        "security": round(sum(r[s_key] or 0 for r in rows) / len(rows), 4),
    }


def build_rows(peer: dict, main: dict) -> list[dict]:
    peer_metrics = peer.get("peer_metrics") or {}
    gate = main.get("gate_results") or {}
    rows = []
    for key, pd in peer_metrics.items():
        m = gate.get(key, {})
        per_def = (m.get("metrics") or {}).get("per_defense") or {}
        parts = key.split("|")
        rows.append(
            {
                "key": key,
                "model": parts[0],
                "attack": parts[1],
                "injection_task": parts[2],
                "suite": parts[3],
                "stress_ok": bool(m.get("stress_ok")),
                "none": per_def.get("none") or {},
                "spotlighting": per_def.get("spotlighting_with_delimiting") or {},
                "detector": per_def.get("transformers_pi_detector")
                or per_def.get("deberta_injection_detector")
                or {},
                "bio_04": per_def.get("bio_04") or {},
                "task_shield": pd.get("task_shield") or {},
                "melon": pd.get("melon") or {},
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    flat: list[dict] = []
    for r in rows:
        flat.append(
            {
                "key": r["key"],
                "stress": r["stress_ok"],
                "suite": r["suite"],
                "attack": r["attack"],
                "none_u": (r["none"] or {}).get("utility"),
                "none_s": (r["none"] or {}).get("security"),
                "spot_u": (r["spotlighting"] or {}).get("utility"),
                "spot_s": (r["spotlighting"] or {}).get("security"),
                "det_u": (r["detector"] or {}).get("utility"),
                "det_s": (r["detector"] or {}).get("security"),
                "bio_u": (r["bio_04"] or {}).get("utility"),
                "bio_s": (r["bio_04"] or {}).get("security"),
                "ts_u": (r["task_shield"] or {}).get("utility"),
                "ts_s": (r["task_shield"] or {}).get("security"),
                "melon_u": (r["melon"] or {}).get("utility"),
                "melon_s": (r["melon"] or {}).get("security"),
            }
        )

    stress = [x for x in flat if x["stress"]]
    by_suite: dict[str, list] = defaultdict(list)
    for x in stress:
        by_suite[x["suite"]].append(x)

    def pack(subset: list[dict]) -> dict:
        return {
            "none": _macro(subset, "none_u", "none_s"),
            "spotlighting": _macro(subset, "spot_u", "spot_s"),
            "detector": _macro(subset, "det_u", "det_s"),
            "bio_04": _macro(subset, "bio_u", "bio_s"),
            "task_shield": _macro(subset, "ts_u", "ts_s"),
            "melon": _macro(subset, "melon_u", "melon_s"),
        }

    return {
        "n_conditions": len(flat),
        "n_stress": len(stress),
        "key_overlap": len(rows),
        "all24": pack(flat),
        "stress18": pack(stress),
        "stress_by_suite": {suite: pack(sub) for suite, sub in sorted(by_suite.items())},
        "per_condition": flat,
        "citations": {
            "task_shield": "jia2025taskshield",
            "melon": "zhu2025melon",
        },
        "implementation_notes": {
            "task_shield": "No official code; LLM goal-alignment port in eval/agentdojo/peer_defenses.py",
            "melon": "Port from github.com/kaijiezhu11/MELON; HashingVectorizer replaces OpenAI embeddings",
        },
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# P0 Peer Baselines — DeepSeek 24-condition manifest",
        "",
        "## Stress macro (18 conditions)",
        "",
        "| Defense | Utility | Security |",
        "|---------|---------|----------|",
    ]
    for name, label in [
        ("none", "none"),
        ("spotlighting", "spotlighting"),
        ("detector", "transformers_pi_detector"),
        ("bio_04", "bio_04"),
        ("task_shield", "task_shield"),
        ("melon", "melon"),
    ]:
        m = report["stress18"][name]
        lines.append(f"| {label} | {m['utility']*100:.1f}% | {m['security']*100:.1f}% |")
    lines += ["", "## Stress by suite", ""]
    for suite, data in report["stress_by_suite"].items():
        lines.append(f"### {suite} (n={data['bio_04']['n']})")
        lines.append("| Defense | U | S |")
        lines.append("|---------|---|---|")
        for name in ("none", "spotlighting", "detector", "bio_04", "task_shield", "melon"):
            m = data[name]
            lines.append(f"| {name} | {m['utility']*100:.1f}% | {m['security']*100:.1f}% |")
        lines.append("")
    lines += [
        "## Robustness",
        "- Same 24 keys as main manifest (`gate_results` overlap 24/24).",
        "- DeepSeek-Chat only; Llama peer not run.",
        "- Task Shield / MELON are faithful ports — see `docs/eval/P0_PEER_BASELINES.md`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="P0 peer table export")
    parser.add_argument("--peer", type=Path, default=PEER_PROGRESS)
    parser.add_argument("--main", type=Path, default=MAIN_PROGRESS)
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument(
        "--experiment-id",
        default=DEFAULT_EXPERIMENT_ID,
        help="Supplement subfolder name (use peer_deepseek_24cond_probe_v2 for reruns)",
    )
    args = parser.parse_args()
    experiment_id = args.experiment_id

    if not args.peer.exists():
        raise SystemExit(f"Missing peer progress: {args.peer}")
    if not args.main.exists():
        raise SystemExit(f"Missing main progress: {args.main}")

    peer = json.loads(args.peer.read_text(encoding="utf-8"))
    main = json.loads(args.main.read_text(encoding="utf-8"))
    rows = build_rows(peer, main)
    report = summarize(rows)

    store = SupplementRunStore(args.out_root)
    store.write_json("p0", experiment_id, "report.json", report)
    store.write_text("p0", experiment_id, "table.md", to_markdown(report))

    print(f"P0 peer table → {store.experiment_dir('p0', experiment_id)}")
    s = report["stress18"]
    print(
        f"stress macro: bio={s['bio_04']['utility']*100:.1f}/{s['bio_04']['security']*100:.1f}% "
        f"TS={s['task_shield']['utility']*100:.1f}/{s['task_shield']['security']*100:.1f}% "
        f"MELON={s['melon']['utility']*100:.1f}/{s['melon']['security']*100:.1f}%"
    )


if __name__ == "__main__":
    main()
