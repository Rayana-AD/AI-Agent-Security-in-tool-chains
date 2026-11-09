#!/usr/bin/env python3
"""P1 adaptive literature matrix — DeepSeek + bio_04 v2 (aggregate + optional live runs)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.supplement.adaptive_metrics import aggregate_agentdojo_logs, injecagent_summary
from eval.supplement.bootstrap_env import ensure_venv_python, repo_root

ensure_venv_python()

EXPERIMENT_ID = "adaptive_matrix_v1"
SUPPLEMENT = repo_root() / "runs" / "supplement"


def _load_json(path: Path) -> dict | None:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def collect_track_a0() -> dict:
    peer = _load_json(SUPPLEMENT / "p0/peer_deepseek_24cond/report.json") or {}
    stress = peer.get("stress18") or {}
    out = {"source": "p0/peer_deepseek_24cond", "attack": "static (important_instructions + tool_knowledge mix)"}
    for defense in ("none", "bio_04"):
        if defense in stress:
            out[defense] = {
                "n": stress[defense]["n"],
                "utility": stress[defense]["utility"],
                "security_mean": stress[defense].get("security"),
            }
    return {"track": "A0", "label": "AgentDojo live static (stress-18)", "metrics": out}


def collect_track_a1() -> dict:
    l3 = SUPPLEMENT / "p1/adaptive_l3_v1"
    bench = l3 / "benchmark_logs"
    rows = []
    for defense_key, folder in (("no_defense", "no_defense"), ("bio_04", "bio_04")):
        sub = bench / "deepseek" / "deepseek-chat" / folder / "banking"
        if not sub.is_dir():
            continue
        for attack in ("important_instructions", "autodojo"):
            attack_logs = list(sub.glob(f"**/{attack}/injection_task_0.json"))
            util, asr = [], []
            for p in attack_logs:
                data = json.loads(p.read_text(encoding="utf-8"))
                util.append(1.0 if data.get("utility") else 0.0)
                asr.append(1.0 if data.get("security") else 0.0)
            if not attack_logs:
                continue
            rows.append(
                {
                    "defense": defense_key,
                    "attack": attack,
                    "suite": "banking",
                    "n": len(attack_logs),
                    "utility_mean": round(sum(util) / len(util), 4),
                    "ASR": round(sum(asr) / len(asr), 4),
                    "security_mean": round(1.0 - sum(asr) / len(asr), 4),
                }
            )
    return {"track": "A1", "label": "AutoDojo adaptive slice (banking×2)", "runs": rows, "source": str(l3)}


def collect_track_d() -> dict:
    matrix = _load_json(SUPPLEMENT / "p2/official_matrix_v2/matrix_summary.json") or {}
    cfg = "idea1_provenance_mlp_bio_04"
    suites = {}
    for suite, per_cfg in (matrix.get("cells") or {}).items():
        cell = (per_cfg or {}).get(cfg) or {}
        suites[suite] = {
            "attack_block_rate": cell.get("attack_block_rate"),
            "n_attack": cell.get("n_attack"),
            "by_attack_type": cell.get("by_attack_type"),
        }
    return {
        "track": "D",
        "label": "L2 scripted (bio_04 v2, offline)",
        "config": cfg,
        "suites": suites,
        "note": "Block rate ≠ live Security; retry_full validates retry-channel fixes.",
    }


def run_injecagent_batch(*, defense: str, max_per_attack: int, setting: str = "base") -> dict:
    from eval.supplement.run_p1_injecagent_live import run_smoke

    parts = []
    for attack in ("dh", "ds"):
        parts.append(
            run_smoke(
                model_name="deepseek-chat",
                setting=setting,
                attack=attack,
                max_cases=max_per_attack,
                defense=defense,
            )
        )
    n_valid = sum(p["n_valid"] for p in parts)
    n_success = sum(
        sum(1 for r in p["rows"] if r.get("eval") == "success") for p in parts
    )
    return {
        "defense": defense,
        "setting": setting,
        "splits": [injecagent_summary(p) for p in parts],
        "combined": {
            "n_valid": n_valid,
            "ASR_valid": round(n_success / max(n_valid, 1), 4),
            "security_mean": round(1.0 - n_success / max(n_valid, 1), 4),
        },
    }


def run_agentdojo_slack_static(*, defense: str, logdir: Path) -> dict:
    from eval.supplement.bootstrap_env import env_for_autodojo

    env = env_for_autodojo()
    d_arg = [] if defense in ("no_defense", "none", "") else ["--defense", defense]
    cmd = [
        sys.executable,
        "-m",
        "agentdojo.scripts.benchmark",
        "--model",
        "deepseek/deepseek-chat",
        "--suite",
        "slack",
        "--attack",
        "important_instructions",
        "--logdir",
        str(logdir),
        "--force-rerun",
        *d_arg,
        "-ut",
        "user_task_0",
        "-ut",
        "user_task_1",
        "-it",
        "injection_task_0",
    ]
    autodojo_root = repo_root() / "third_party" / "AutoDojo"
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=str(autodojo_root),
        capture_output=True,
        text=True,
    )
    agg = aggregate_agentdojo_logs(logdir)
    return {"defense": defense, "returncode": proc.returncode, "metrics": agg, "stderr_tail": (proc.stderr or "")[-800:]}


def main() -> None:
    parser = argparse.ArgumentParser(description="P1 adaptive matrix v1")
    parser.add_argument("--aggregate-only", action="store_true", help="Only collect existing results")
    parser.add_argument("--execute-injecagent", action="store_true")
    parser.add_argument("--execute-slack", action="store_true", help="Small AgentDojo slack static add-on")
    parser.add_argument("--injecagent-per-attack", type=int, default=50, help="Max cases per dh/ds file")
    parser.add_argument("--defenses", nargs="+", default=["none", "bio_04"])
    args = parser.parse_args()

    from eval.supplement.results_store import SupplementRunStore

    store = SupplementRunStore()
    exp_dir = store.experiment_dir("p1", EXPERIMENT_ID)

    report = {
        "experiment_id": EXPERIMENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-chat / deepseek/deepseek-chat",
        "defense_focus": "idea1_provenance_mlp_bio_04 (v2, incl. retry fixes in offline track D)",
        "tracks": {},
        "status": "aggregated",
    }

    report["tracks"]["A0"] = collect_track_a0()
    report["tracks"]["A1"] = collect_track_a1()
    report["tracks"]["D"] = collect_track_d()

    if args.execute_injecagent:
        report["tracks"]["B0"] = {"label": "InjecAgent static (Zhan subset scale)", "by_defense": {}}
        errors = []
        for defense in args.defenses:
            try:
                report["tracks"]["B0"]["by_defense"][defense] = run_injecagent_batch(
                    defense=defense,
                    max_per_attack=args.injecagent_per_attack,
                )
            except Exception as exc:
                errors.append({"defense": defense, "error": str(exc)})
        report["tracks"]["B0"]["errors"] = errors
        report["status"] = "partial_fail" if errors else "live_ok"

    if args.execute_slack:
        slack_dir = exp_dir / "slack_static_logs"
        slack_dir.mkdir(parents=True, exist_ok=True)
        report["tracks"]["A0_slack_addon"] = {"runs": []}
        for defense in args.defenses:
            dkey = "no_defense" if defense == "none" else defense
            rec = run_agentdojo_slack_static(defense=dkey, logdir=slack_dir)
            report["tracks"]["A0_slack_addon"]["runs"].append(rec)

    store.write_json("p1", EXPERIMENT_ID, "report.json", report)
    print(json.dumps(report, indent=2))
    print(f"\nP1 adaptive matrix → {exp_dir}")

    # Trigger viz
    viz = ROOT / "eval" / "supplement" / "visualize_adaptive_matrix.py"
    if viz.is_file():
        subprocess.run([sys.executable, str(viz)], check=False)


if __name__ == "__main__":
    main()
