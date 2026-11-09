#!/usr/bin/env python3
"""Supplementary benchmarks: citation (HalluLens/CiteCheck-style) + Idea2 v2 + real LLM."""

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
from eval.attacks.citation_agent_joint import write_joint_dataset
from eval.attacks.citation_hallucination import write_all as write_citation_all
from eval.citation_scripted_runner import run_literature_scripted
from eval.run_experiments import load_experiment_spec
from eval.run_idea2_suite import DATASET_FILES, load_spec, read_jsonl, run_one

DEFAULT_CONFIGS = ["citation_gate_only", "full_citation", "schema_only", "full"]


def load_agentdojo_cfg() -> dict:
    path = CONFIGS_DIR / "agentdojo.yaml"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_samples_for_dataset(dataset: str) -> list[dict]:
    if dataset == "citation_hallucination":
        write_citation_all()
        return read_jsonl(ROOT / "data" / "attacks" / "citation" / "citation_hallucination.jsonl")
    if dataset == "citation_agent_joint":
        write_joint_dataset()
        return read_jsonl(ROOT / "data" / "attacks" / "citation" / "citation_agent_joint.jsonl")
    if dataset == "idea2_v2_focus":
        samples: list[dict] = []
        for key in ("c3_tool_injection", "c5_subtle_deception", "c6_escalation"):
            samples.extend(read_jsonl(ROOT / "data" / "attacks" / "idea2" / DATASET_FILES[key]))
        return samples
    if dataset in DATASET_FILES:
        return read_jsonl(ROOT / "data" / "attacks" / "idea2" / DATASET_FILES[dataset])
    raise ValueError(f"Unknown dataset: {dataset}")


def run_citation_block(name: str, configs: list[str]) -> dict:
    spec = load_experiment_spec(name)
    dataset = spec.get("dataset", "citation_hallucination")
    samples = _load_samples_for_dataset(dataset)
    configs = configs or spec.get("configs", DEFAULT_CONFIGS)

    blocked = {c: {"blocked": 0, "false_allow": 0, "benign_ok": 0} for c in configs}
    attacks = [s for s in samples if not s.get("benign")]
    benign = [s for s in samples if s.get("benign")]

    for cfg_key in configs:
        runner = build_runner(cfg_key)
        for sample in tqdm(samples, desc=f"{name}/{cfg_key}"):
            hr = run_literature_scripted(runner, sample)
            expected_block = sample.get("expected_block", not sample.get("benign", False))
            if expected_block and hr.blocked:
                blocked[cfg_key]["blocked"] += 1
            if expected_block and not hr.blocked:
                blocked[cfg_key]["false_allow"] += 1
            if sample.get("benign") and not hr.blocked:
                blocked[cfg_key]["benign_ok"] += 1

    summary = {}
    for cfg_key, counts in blocked.items():
        summary[cfg_key] = {
            "n_samples": len(samples),
            "n_attacks": len(attacks),
            "n_benign": len(benign),
            "block_rate": round(counts["blocked"] / max(len(attacks), 1), 4),
            "attack_success_rate": round(counts["false_allow"] / max(len(attacks), 1), 4),
            "benign_utility": round(counts["benign_ok"] / max(len(benign), 1), 4),
        }
    return {"experiment": name, "dataset": dataset, "configs": summary}


def build_openrouter_llm(model_mode: str):
    """OpenRouter-backed LLMBackend for scripted harness runs with real generation."""
    import os

    from bio_harness.config import get_model_settings, load_yaml
    from bio_harness.llm.openai_backend import OpenAICompatibleBackend

    settings = get_model_settings()
    providers = load_yaml("model.yaml").get("providers") or {}
    pcfg = providers.get(model_mode) or {}
    key = (settings.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Missing openrouter_api_key in configs/secrets.yaml")
    return OpenAICompatibleBackend(
        model=pcfg.get("api_model", "meta-llama/llama-3.3-70b-instruct"),
        base_url=pcfg.get("base_url", "https://openrouter.ai/api/v1"),
        api_key=key,
        temperature=0.0,
        max_new_tokens=512,
    )


def main() -> None:
    ad_cfg = load_agentdojo_cfg()
    sup = ad_cfg.get("supplementary") or {}

    parser = argparse.ArgumentParser(description="Supplementary citation + Idea2 v2 benchmarks")
    parser.add_argument("--model-mode", default="openrouter_llama70")
    parser.add_argument("--skip-llm", action="store_true", help="Scripted only (no API calls)")
    parser.add_argument("--llm-limit", type=int, default=sup.get("llm_sample_limit", 20))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output or (ROOT / "runs" / f"supplementary_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "model_mode": args.model_mode,
        "timestamp": ts,
        "citation": {},
        "idea2_v2": {},
        "llm_scripted": {},
    }

    print("=== Citation hallucination (HalluLens/CiteCheck-style) ===", flush=True)
    report["citation"]["hallucination"] = run_citation_block("exp_citation_hallucination", sup.get("citation_configs") or DEFAULT_CONFIGS[:3])

    print("=== Agent + citation joint ===", flush=True)
    report["citation"]["agent_joint"] = run_citation_block(
        "exp_citation_agent_joint",
        sup.get("citation_configs") or DEFAULT_CONFIGS,
    )

    print("=== Idea2 v2 focus (scripted, C3/C5/C6) ===", flush=True)
    report["idea2_v2"]["scripted"] = run_one("exp_idea2_v2_focus", use_llm=False)

    if not args.skip_llm:
        print(f"=== Idea2 v2 + real LLM (limit={args.llm_limit}) ===", flush=True)
        shared_llm = build_openrouter_llm(args.model_mode)
        llm_reports = []
        for exp_name in sup.get("llm_experiments") or ["exp_c3_tool_injection", "exp_c5_subtle_deception"]:
            spec = load_spec(exp_name)
            samples = _load_samples_for_dataset(spec["dataset"])[: args.llm_limit]
            run_sub: dict = {"experiment": exp_name, "n_samples": len(samples), "summaries": []}
            for cfg in spec["configs"]:
                runner = build_runner(cfg, llm=shared_llm)
                records = []
                for sample in tqdm(samples, desc=f"llm/{exp_name}/{cfg}"):
                    result = runner.run(sample)
                    records.append(
                        {
                            "sample_id": sample.get("id"),
                            "blocked": result.blocked,
                            "harmful": result.harmful,
                            "attack_type": sample.get("attack_type"),
                        }
                    )
                n = len(records)
                run_sub["summaries"].append(
                    {
                        "config": cfg,
                        "block_rate": round(sum(1 for r in records if r["blocked"]) / max(n, 1), 4),
                        "asr": round(
                            sum(1 for r in records if r["harmful"] and not r["blocked"]) / max(n, 1), 4
                        ),
                    }
                )
            llm_reports.append(run_sub)
        report["llm_scripted"] = llm_reports

    report_path = out_dir / "report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nSupplementary report → {report_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "citation" or True}, indent=2)[:2000])


if __name__ == "__main__":
    main()
