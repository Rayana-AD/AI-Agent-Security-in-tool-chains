"""Mechanism taxonomy from AgentDojo benchmark logs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BLOCK_RE = re.compile(
    r"BioHarness (?:filtered blocked tool\(s\)|blocked tool calls|blocked tool output)[^:]*:\s*"
    r"([^(\n]+)\(([^)]+)\)",
    re.I,
)
SIMPLE_BLOCK_RE = re.compile(r"Tool call blocked by BioHarness:\s*([^\n]+)", re.I)
INFO_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content") or block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def classify_block_reason(reason: str) -> str:
    r = (reason or "").lower()
    if "withheld" in r or "withhold" in r:
        return "output_withhold"
    if "metadata_strip" in r:
        return "metadata_strip"
    if "unified_risk" in r:
        return "unified_risk"
    if "reflection" in r or "provenance_reflection" in r:
        return "reflection"
    if "feature_shuffle" in r:
        return "feature_shuffle"
    if "provenance_drift" in r or "gate" in r:
        return "gate_drift"
    if "channel_escalation" in r or "sensitive" in r:
        return "channel_escalation"
    if "harmful" in r:
        return "harmful_pattern"
    return "other_block"


def analyze_log(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    messages = data.get("messages") or []
    mechanisms: list[str] = []
    block_reasons: list[str] = []
    withheld = 0
    tool_info = 0

    for msg in messages:
        text = _message_text(msg.get("content"))
        if "withheld by bioharness" in text.lower():
            withheld += 1
            mechanisms.append("output_withhold")
        if msg.get("role") == "tool" and INFO_RE.search(text):
            tool_info += 1
        if "blocked by bioharness" in text.lower():
            for m in BLOCK_RE.finditer(text):
                block_reasons.append(m.group(2).strip())
                mechanisms.append(classify_block_reason(m.group(2)))
            if not block_reasons:
                sm = SIMPLE_BLOCK_RE.search(text)
                if sm:
                    detail = sm.group(1)
                    for part in detail.split(";"):
                        if "(" in part and ")" in part:
                            reason = part.split("(", 1)[1].rsplit(")", 1)[0]
                            block_reasons.append(reason.strip())
                            mechanisms.append(classify_block_reason(reason))

    attack_success = bool(data.get("security", False))
    dominant = "success" if data.get("utility") and not attack_success else ""
    if attack_success:
        dominant = "attack_success"
    elif mechanisms:
        from collections import Counter

        dominant = Counter(mechanisms).most_common(1)[0][0]
    elif not data.get("utility"):
        dominant = "task_incomplete"

    parsed = _parse_log_path(path)
    return {
        "path": str(path),
        "suite": data.get("suite_name", "") or parsed["suite"],
        "user_task_id": data.get("user_task_id", "") or parsed["user_task"],
        "injection_task_id": data.get("injection_task_id", "") or parsed["injection_task"],
        "attack": parsed["attack"],
        "defense": parsed["defense"] or _defense_from_path(path),
        "utility": bool(data.get("utility", False)),
        "attack_success": attack_success,
        "security_pass": not attack_success,
        "withheld_events": withheld,
        "injection_in_tool_output": tool_info > 0,
        "dominant_mechanism": dominant,
        "mechanisms": mechanisms,
        "block_reasons": block_reasons[:8],
    }


def _parse_log_path(path: Path) -> dict[str, str]:
    """Extract attack/defense/suite from AgentDojo log layout."""
    parts = path.parts
    out = {"attack": "", "defense": "", "suite": "", "user_task": "", "injection_task": path.stem}
    for i, p in enumerate(parts):
        if p == "logs" and i + 3 < len(parts):
            out["attack"] = parts[i + 1]
            out["defense"] = parts[i + 2]
            out["suite"] = parts[i + 3]
            break
        if p.startswith("user_task_"):
            out["user_task"] = p
    return out


def _defense_from_path(path: Path) -> str:
    parsed = _parse_log_path(path)
    if parsed["defense"]:
        return parsed["defense"]
    for p in path.parts:
        if p.startswith("bio_") or p in (
            "none",
            "tool_filter",
            "spotlighting_with_delimiting",
            "repeat_user_prompt",
            "transformers_pi_detector",
        ):
            return p
    return "unknown"


def scan_logdir(logdir: Path, *, pattern: str = "**/user_task_*/**/*.json") -> list[dict[str, Any]]:
    rows = []
    for path in sorted(logdir.glob(pattern)):
        if "injection_task_" not in str(path) and "user_task_" not in str(path):
            continue
        try:
            rows.append(analyze_log(path))
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return rows


def scan_benchmark_dirs(
    benchmark_dirs: list[Path],
    *,
    curated_tasks: list[dict] | None = None,
    model_mode: str | None = None,
    progress_keys: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Scan multiple benchmark_* trees (e.g. from live progress checkpoints)."""
    task_lookup = {(t["suite"], t["user_task"]): t for t in (curated_tasks or [])}
    rows: list[dict[str, Any]] = []
    for bdir in benchmark_dirs:
        if not bdir.is_dir():
            continue
        bench_key = ""
        if progress_keys:
            bench_key = next((k for k, v in progress_keys.items() if v == str(bdir.resolve())), "")
        for ep in scan_logdir(bdir):
            if model_mode and bench_key and not bench_key.startswith(model_mode):
                continue
            ut = ep.get("user_task_id", "")
            suite = ep.get("suite", "")
            meta = task_lookup.get((suite, ut), {})
            ep["task_type"] = meta.get("task_type", f"{suite}_general")
            ep["benchmark_dir"] = str(bdir)
            ep["benchmark_key"] = bench_key
            if bench_key and "|" in bench_key:
                model, attack, injection, b_suite = (bench_key.split("|") + ["", "", "", ""])[:4]
                ep.setdefault("model_mode", model)
                ep.setdefault("attack", attack or ep.get("attack"))
                ep.setdefault("injection_task", injection or ep.get("injection_task_id"))
                ep.setdefault("batch_suite", b_suite)
            rows.append(ep)
    return rows


def summarize_mechanisms(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    overall = Counter(ep.get("dominant_mechanism") or "unknown" for ep in episodes)
    by_defense: dict[str, dict[str, int]] = {}
    by_suite: dict[str, dict[str, int]] = {}
    by_task_type: dict[str, dict[str, int]] = {}
    bio_eps = [ep for ep in episodes if str(ep.get("defense", "")).startswith("bio_")]

    for ep in episodes:
        mech = ep.get("dominant_mechanism") or "unknown"
        by_defense.setdefault(str(ep.get("defense")), Counter())[mech] += 1
        by_suite.setdefault(str(ep.get("suite")), Counter())[mech] += 1
        by_task_type.setdefault(str(ep.get("task_type")), Counter())[mech] += 1

    def _to_dict(counter_map: dict[str, Counter]) -> dict[str, dict[str, int]]:
        return {k: dict(v) for k, v in counter_map.items()}

    sec_rate = {}
    for defense, ctr in by_defense.items():
        defs_eps = [e for e in episodes if e.get("defense") == defense]
        if defs_eps:
            sec_rate[defense] = sum(1 for e in defs_eps if e.get("security_pass")) / len(defs_eps)

    return {
        "n_episodes": len(episodes),
        "n_bio_episodes": len(bio_eps),
        "by_mechanism": dict(overall),
        "by_defense": _to_dict(by_defense),
        "by_suite": _to_dict(by_suite),
        "by_task_type": _to_dict(by_task_type),
        "security_rate_by_defense": sec_rate,
    }
