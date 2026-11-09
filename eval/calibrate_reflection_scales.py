#!/usr/bin/env python3
"""Estimate reflection saturation τ_α, τ_δ from benign (Δα, δ) pairs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bio_harness.provenance.reflection_probe import (  # noqa: E402
    DotKeyProjector,
    _path_overlap,
    householder_reflect,
    split_process_segments,
)
from bio_harness.provenance.reflection_scales import (  # noqa: E402
    DEFAULT_CACHE_PATH,
    save_scales,
    scales_from_pairs,
)
from eval.agentdojo.context_builder import parse_tool_call, safe_message_text  # noqa: E402


def step_pair(proj: DotKeyProjector, goal: str, text_a: str, text_b: str) -> tuple[float, float]:
    import numpy as np

    q = proj.project(goal)
    ka = proj.project(text_a)
    kb = proj.project(text_b)
    da = abs(proj.score(q, kb) - proj.score(q, ka))
    dr = float(np.linalg.norm(householder_reflect(kb, q) - householder_reflect(ka, q)))
    return da, dr


def collect_from_agentdojo(log_root: Path, proj: DotKeyProjector, *, max_files: int = 800) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []

    files = sorted(log_root.glob("**/none/**/*.json"))[:max_files]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        msgs = data.get("messages") or []
        goal = ""
        for m in msgs:
            if m.get("role") == "user":
                goal = safe_message_text(m.get("content"))
                break
        if not goal.strip():
            continue
        prev_assistant = ""
        for m in msgs:
            if m.get("role") == "assistant":
                text = safe_message_text(m.get("content"))
                if text and "tool call blocked" not in text.lower():
                    if prev_assistant:
                        da, dr = step_pair(proj, goal, prev_assistant, text)
                        pairs.append((da, dr))
                    prev_assistant = text or prev_assistant
                for tc in m.get("tool_calls") or []:
                    fn, args = parse_tool_call(tc)
                    if not fn:
                        continue
                    tc_json = json.dumps({"tool": fn, "args": args})
                    rev = text or prev_assistant or goal[:120]
                    if _path_overlap(goal, tc_json) < 0.08:
                        continue
                    da, dr = step_pair(proj, goal, rev, tc_json)
                    pairs.append((da, dr))
            elif m.get("role") == "tool":
                pass
    return pairs


def collect_from_scripted(proj: DotKeyProjector) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    benign_path = ROOT / "data/benign/agent_tasks.jsonl"
    if benign_path.is_file():
        for line in benign_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            goal = row.get("user_goal") or row.get("goal") or ""
            outs = row.get("scripted_outputs") or {}
            rev = str(outs.get("review") or "")
            tc = str(outs.get("tool_call") or "")
            if goal and rev and tc:
                pairs.append(step_pair(proj, goal, rev, tc))
    return pairs


def collect_process_benign(
    proj: DotKeyProjector, log_root: Path | None = None, *, max_files: int = 800
) -> list[tuple[float, float]]:
    """Intra-process segment steps (same split as analyze_process) for process scales."""
    pairs: list[tuple[float, float]] = []
    if log_root and log_root.is_dir():
        for f in sorted(log_root.glob("**/none/**/*.json"))[:max_files]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            msgs = data.get("messages") or []
            goal = ""
            for m in msgs:
                if m.get("role") == "user":
                    goal = safe_message_text(m.get("content"))
                    break
            if not goal.strip():
                continue
            for m in msgs:
                if m.get("role") != "assistant":
                    continue
                text = safe_message_text(m.get("content"))
                if not text or "tool call blocked" in text.lower():
                    continue
                segs = split_process_segments(text)
                for i in range(1, len(segs)):
                    pairs.append(step_pair(proj, goal, segs[i - 1], segs[i]))
    proc_path = ROOT / "data/attacks/reflection_process_samples.jsonl"
    if proc_path.is_file():
        for line in proc_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("expect_block"):
                continue
            goal = row.get("goal") or ""
            proc = row.get("process_text") or ""
            if goal and proc:
                segs = split_process_segments(proc)
                for i in range(1, len(segs)):
                    pairs.append(step_pair(proj, goal, segs[i - 1], segs[i]))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate reflection τ_α, τ_δ from benign pairs")
    parser.add_argument(
        "--stat",
        choices=("median", "mean", "p75", "p90"),
        default="p90",
        help="Benign (Δα,δ) scale; p90 recommended so most benign stay below saturation (default: p90)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--agentdojo-root", type=Path, default=ROOT / "runs/agentdojo_upstream")
    parser.add_argument("--max-log-files", type=int, default=800)
    args = parser.parse_args()

    proj = DotKeyProjector(dim=64)
    cross_pairs: list[tuple[float, float]] = []
    cross_pairs.extend(collect_from_scripted(proj))
    if args.agentdojo_root.is_dir():
        cross_pairs.extend(
            collect_from_agentdojo(args.agentdojo_root, proj, max_files=args.max_log_files)
        )

    scales = scales_from_pairs(
        cross_pairs, stat=args.stat, source=f"calibrated_cross:{args.stat}"
    )
    out = save_scales(scales, args.out)

    proc_pairs = collect_process_benign(
        proj, args.agentdojo_root if args.agentdojo_root.is_dir() else None, max_files=args.max_log_files
    )
    if proc_pairs:
        proc_scales = scales_from_pairs(
            proc_pairs, stat=args.stat, source=f"calibrated_process:{args.stat}"
        )
        proc_out = args.out.with_name("reflection_scales_process.json")
        save_scales(proc_scales, proc_out)
        print(
            f"Wrote process scales {proc_out} "
            f"τ_α={proc_scales.tau_alpha:.4f} δ₀={proc_scales.delta_baseline:.4f} "
            f"τ_δ⁺={proc_scales.tau_delta:.4f}"
        )
    print(f"Wrote {out}")
    print(
        f"τ_α={scales.tau_alpha:.4f} δ₀={scales.delta_baseline:.4f} τ_δ⁺={scales.tau_delta:.4f} "
        f"(n={scales.n_pairs}, median_α={scales.median_alpha:.4f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
