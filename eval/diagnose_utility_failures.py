"""Per-suite utility failure diagnosis from live benchmark logs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.paper_mechanism import scan_benchmark_dirs, summarize_mechanisms


def _load_progress(path: Path) -> tuple[list[Path], dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    completed = data.get("completed") or {}
    run_dirs = [Path(v["run_dir"]) for v in completed.values() if v.get("run_dir")]
    progress_keys = {k: v["run_dir"] for k, v in completed.items()}
    return run_dirs, progress_keys


def diagnose(
    *,
    progress_file: Path,
    defense: str,
    model_mode: str | None = None,
) -> dict:
    run_dirs, progress_keys = _load_progress(progress_file)
    episodes = scan_benchmark_dirs(
        run_dirs,
        model_mode=model_mode,
        progress_keys=progress_keys,
    )
    eps = [e for e in episodes if e.get("defense") == defense]
    fails = [e for e in eps if not e.get("utility")]

    by_suite: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "mechanisms": Counter(), "block_tools": Counter()}
    )
    for e in eps:
        suite = str(e.get("suite") or "unknown")
        key = "pass" if e.get("utility") else "fail"
        by_suite[suite][key] += 1
        if not e.get("utility"):
            by_suite[suite]["mechanisms"][e.get("dominant_mechanism") or "unknown"] += 1
            try:
                data = json.loads(Path(e["path"]).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for msg in data.get("messages") or []:
                content = msg.get("content")
                if not isinstance(content, str) or "blocked by bioharness" not in content.lower():
                    continue
                for part in content.split(";"):
                    if "(" not in part:
                        continue
                    name = part.split("(")[0].split(":")[-1].strip()
                    if name:
                        by_suite[suite]["block_tools"][name] += 1

    suite_report = {}
    for suite, stats in sorted(by_suite.items()):
        suite_report[suite] = {
            "pass": stats["pass"],
            "fail": stats["fail"],
            "utility_rate": stats["pass"] / max(1, stats["pass"] + stats["fail"]),
            "fail_mechanisms": dict(stats["mechanisms"]),
            "top_blocked_tools": stats["block_tools"].most_common(8),
        }

    return {
        "defense": defense,
        "model_mode": model_mode,
        "n_episodes": len(eps),
        "n_utility_fail": len(fails),
        "utility_rate": sum(1 for e in eps if e.get("utility")) / max(1, len(eps)),
        "mechanism_summary": summarize_mechanisms(eps),
        "by_suite": suite_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path("runs/paper_m1_live_progress.json"),
    )
    parser.add_argument(
        "--defense",
        default="bio_idea1_provenance_reflection_meta_full",
    )
    parser.add_argument("--model-mode", default="deepseek")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = diagnose(
        progress_file=args.progress_file,
        defense=args.defense,
        model_mode=args.model_mode or None,
    )
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
