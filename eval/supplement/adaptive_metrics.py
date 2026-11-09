"""Unified metrics for P1 adaptive matrix (paper Security = 1 − ASR)."""

from __future__ import annotations

import json
from pathlib import Path


def agentdojo_log_injection_success(log: dict) -> bool | None:
    """Raw AgentDojo JSON: security=True means injection goal succeeded (ASR cell)."""
    if "security" not in log:
        return None
    return bool(log["security"])


def aggregate_agentdojo_logs(logdir: Path, *, pipeline_prefix: str = "deepseek") -> dict:
    """Scan benchmark_logs for injection_task_*.json; return macro U/S in paper convention."""
    logs = sorted(logdir.glob(f"**/{pipeline_prefix}/**/injection_task_*.json"))
    if not logs:
        logs = sorted(logdir.glob("**/injection_task_*.json"))
    util: list[float] = []
    asr: list[float] = []
    cells: list[dict] = []
    for p in logs:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        u = data.get("utility")
        inj_ok = agentdojo_log_injection_success(data)
        if u is None or inj_ok is None:
            continue
        util.append(1.0 if u else 0.0)
        asr.append(1.0 if inj_ok else 0.0)
        parts = p.parts
        cells.append(
            {
                "path": str(p.relative_to(logdir) if logdir in p.parents else p),
                "utility": bool(u),
                "injection_success": bool(inj_ok),
                "defense_security": 1.0 - float(inj_ok),
            }
        )
    n = max(len(util), len(asr))
    if not n:
        return {"n_logs": 0, "cells": []}
    return {
        "n_logs": n,
        "utility_mean": round(sum(util) / len(util), 4),
        "ASR": round(sum(asr) / len(asr), 4),
        "security_mean": round(1.0 - sum(asr) / len(asr), 4),
        "cells": cells,
    }


def injecagent_summary(report_smoke: dict) -> dict:
    s = report_smoke
    return {
        "n_cases": s.get("n_cases", 0),
        "n_valid": s.get("n_valid", 0),
        "ASR_valid": s.get("asr_valid"),
        "defense_security_valid": round(1.0 - (s.get("asr_valid") or 0), 4),
        "defense": s.get("defense"),
        "attack_file": s.get("attack_file"),
        "setting": s.get("setting"),
    }
