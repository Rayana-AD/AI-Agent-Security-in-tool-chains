#!/usr/bin/env python3
"""Offline injection-depth analysis from AgentDojo benchmark logs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _injection_markers() -> tuple[str, ...]:
    return ("<INFORMATION>", "important message from me", "Before you can solve the task")


def _tool_index_at_first_injection(messages: list[dict]) -> int | None:
    tool_idx = 0
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        tool_idx += 1
        content = msg.get("content")
        if isinstance(content, list):
            text = " ".join(
                str(c.get("content", c)) if isinstance(c, dict) else str(c) for c in content
            )
        else:
            text = str(content or "")
        if any(m.lower() in text.lower() for m in _injection_markers()):
            return tool_idx
    return None


def analyze_logs(log_glob: str, *, defense: str | None = None) -> dict:
    paths = sorted(Path(p) for p in Path().glob(log_glob) if Path(p).is_file())
    if not paths:
        # allow absolute glob from caller cwd
        import glob

        paths = sorted(Path(p) for p in glob.glob(log_glob))

    rows: list[dict] = []
    for path in paths:
        if path.name == "none.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if defense and defense not in path.parts:
            continue
        depth = _tool_index_at_first_injection(data.get("messages") or [])
        rows.append(
            {
                "path": str(path),
                "suite": data.get("suite_name"),
                "user_task_id": data.get("user_task_id"),
                "injection_task_id": data.get("injection_task_id"),
                "attack_type": data.get("attack_type"),
                "utility": bool(data.get("utility")),
                "attack_success": bool(data.get("security")),
                "injection_depth": depth,
            }
        )

    by_depth: dict[int | str, list[dict]] = defaultdict(list)
    for row in rows:
        key = row["injection_depth"] if row["injection_depth"] is not None else "none"
        by_depth[key].append(row)

    summary = {}
    for depth, items in sorted(by_depth.items(), key=lambda x: (999 if x[0] == "none" else int(x[0]))):
        n = len(items)
        asr = sum(1 for x in items if x["attack_success"]) / max(n, 1)
        util = sum(1 for x in items if x["utility"]) / max(n, 1)
        summary[str(depth)] = {
            "n": n,
            "ASR": round(asr, 4),
            "utility": round(util, 4),
        }

    return {"n_logs": len(rows), "by_injection_depth": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-glob",
        required=True,
        help="Glob for injection_task JSON logs, e.g. runs/.../spotlighting/**/injection_task_1.json",
    )
    parser.add_argument("--defense", default=None, help="Filter path component, e.g. spotlighting_with_delimiting")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON summary here")
    args = parser.parse_args()

    report = analyze_logs(args.log_glob, defense=args.defense)
    text = json.dumps(report["by_injection_depth"], indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
