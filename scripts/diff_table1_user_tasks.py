#!/usr/bin/env python3
"""Per user_task utility/security: reference (e.g. July) vs candidate remeasure bench."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from eval.paper_mechanism import analyze_log


def collect(bench: Path, defense: str) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    if not bench.is_dir():
        return out
    for p in bench.rglob("injection_task_*.json"):
        parts = p.parts
        if "logs" not in parts:
            continue
        log_indices = [i for i, p in enumerate(parts) if p == "logs"]
        if not log_indices:
            continue
        i = log_indices[-1]
        if i + 2 >= len(parts) or parts[i + 2] != defense:
            continue
        ut = next((x for x in parts if x.startswith("user_task_")), None)
        if not ut:
            continue
        suite = parts[parts.index(ut) - 1]
        inj = p.stem
        key = (suite, ut)
        try:
            ep = analyze_log(p)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            ep = {"utility": None, "error": str(e)}
        out[key] = {
            "injection": inj,
            "utility": ep.get("utility"),
            "security": ep.get("security"),
            "mechanism": ep.get("dominant_mechanism"),
            "log": str(p),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-bench", type=Path, required=True)
    ap.add_argument("--candidate-bench", type=Path, required=True)
    ap.add_argument("--reference-defense", default="bio_04")
    ap.add_argument("--candidate-defense", default="bio_remeasure")
    ap.add_argument("--suite", default="", help="Optional filter, e.g. banking")
    args = ap.parse_args()

    ref = collect(args.reference_bench, args.reference_defense)
    cand = collect(args.candidate_bench, args.candidate_defense)
    keys = sorted(set(ref) | set(cand))
    if args.suite:
        keys = [k for k in keys if k[0] == args.suite]

    print(f"reference: {args.reference_bench} [{args.reference_defense}]")
    print(f"candidate: {args.candidate_bench} [{args.candidate_defense}]")
    print(f"{'suite':<12} {'task':<14} {'ref_U':>6} {'cand_U':>7} {'ref_mech':<22} {'cand_mech'}")
    print("-" * 90)
    regressions = 0
    for suite, ut in keys:
        r = ref.get((suite, ut), {})
        c = cand.get((suite, ut), {})
        ru, cu = r.get("utility"), c.get("utility")
        flag = ""
        if ru is True and cu is False:
            flag = " *** REGRESSION"
            regressions += 1
        elif ru is False and cu is True:
            flag = " (improved)"
        print(
            f"{suite:<12} {ut:<14} {str(ru):>6} {str(cu):>7} "
            f"{str(r.get('mechanism','')):<22} {c.get('mechanism','')}{flag}"
        )
    print("-" * 90)
    print(f"regressions (ref pass -> cand fail): {regressions}")


if __name__ == "__main__":
    main()
