#!/usr/bin/env python3
"""Cross-check main.tex headline numbers against merged progress JSON."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIED_WARNING_ONLY_SAFE = frozenset({"deepseek|direct|injection_task_0|slack"})
SUITE_EP = {"banking": 6, "slack": 2, "workspace": 1}


def load_gates(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["gate_results"]


def cond_macro(gates: dict, defense: str, *, stress_only: bool, audit_bio: bool = False) -> tuple[float, float, int]:
    rows_u, rows_s = [], []
    for key, gate in gates.items():
        if stress_only and not gate.get("stress_ok"):
            continue
        per = gate["metrics"]["per_defense"].get(defense)
        if not per:
            continue
        sec = per["security"]
        if audit_bio and defense == "bio_04" and key in VERIFIED_WARNING_ONLY_SAFE:
            sec = 1.0
        rows_u.append(per["utility"] * 100)
        rows_s.append(sec * 100)
    n = len(rows_u)
    return sum(rows_u) / n, sum(rows_s) / n, n


def ep_weighted_stress(gates: dict, defense: str) -> tuple[float, float, int]:
    num_u = num_s = den = 0
    for key, gate in gates.items():
        if not gate.get("stress_ok"):
            continue
        suite = key.split("|")[3]
        w = SUITE_EP[suite]
        per = gate["metrics"]["per_defense"][defense]
        num_u += w * per["utility"]
        num_s += w * per["security"]
        den += w
    return 100 * num_u / den, 100 * num_s / den, den


def attack_framing_bio(gates: dict, audit: bool) -> dict[str, tuple[float, float, int]]:
    by: dict[str, list[tuple[float, float]]] = {}
    for key, gate in gates.items():
        atk = key.split("|")[1]
        per = gate["metrics"]["per_defense"]["bio_04"]
        sec = per["security"]
        if audit and key in VERIFIED_WARNING_ONLY_SAFE:
            sec = 1.0
        by.setdefault(atk, []).append((per["utility"] * 100, sec * 100))
    return {a: (sum(x[0] for x in rs) / len(rs), sum(x[1] for x in rs) / len(rs), len(rs)) for a, rs in by.items()}


def suite_table_stress_ds(gates: dict) -> dict[str, dict[str, tuple[float, float]]]:
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for suite in ("workspace", "slack", "banking"):
        rows = [
            g["metrics"]["per_defense"]
            for k, g in gates.items()
            if g.get("stress_ok") and k.split("|")[3] == suite
        ]
        out[suite] = {}
        for d in ("none", "spotlighting_with_delimiting", "transformers_pi_detector", "bio_04"):
            u = sum(r[d]["utility"] for r in rows) / len(rows) * 100
            s = sum(r[d]["security"] for r in rows) / len(rows) * 100
            out[suite][d] = (u, s)
    return out


def r1(x: float) -> float:
    return round(x, 1)


def main() -> None:
    ds = load_gates(ROOT / "runs/table1_remeasure/merged_deepseek.json")
    ll = load_gates(ROOT / "runs/table1_remeasure/merged_llama.json")

    print("=== Table 1 bio_04 (paper uses audited S for DS unfilt) ===")
    for label, gates, audit in [("DS", ds, True), ("LL", ll, False)]:
        su, ss, n = cond_macro(gates, "bio_04", stress_only=True, audit_bio=audit)
        au, as_, na = cond_macro(gates, "bio_04", stress_only=False, audit_bio=audit)
        eu, es, eden = ep_weighted_stress(gates, "bio_04")
        raw_as = cond_macro(gates, "bio_04", stress_only=False, audit_bio=False)[1]
        print(f"  {label} stress n={n} U={r1(su)} S={r1(ss)}")
        print(f"  {label} unfilt n={na} U={r1(au)} S={r1(as_)} (raw S={r1(raw_as)})")
        print(f"  {label} ep-wt stress U={r1(eu)} S={r1(es)} den_ep={eden}")

    print("\n=== Table 1 all defenses DeepSeek (stress row spot check) ===")
    for d in ("none", "spotlighting_with_delimiting", "transformers_pi_detector", "bio_04"):
        su, ss, _ = cond_macro(ds, d, stress_only=True)
        print(f"  {d}: U={r1(su)} S={r1(ss)}")

    print("\n=== Fig 3 attack framing (audited DS) ===")
    for name, gates, audit in [("DS", ds, True), ("LL", ll, False)]:
        fr = attack_framing_bio(gates, audit)
        order = [
            "direct",
            "important_instructions",
            "important_instructions_education",
            "important_instructions_persona",
        ]
        for a in order:
            u, s, n = fr[a]
            print(f"  {name} {a}: n_cond={n} U={r1(u)} S={r1(s)} ep={n * (6 if True else 0)}")

    print("\n=== Table 2 stress DeepSeek ===")
    st = suite_table_stress_ds(ds)
    for suite, n in [("workspace", 4), ("slack", 6), ("banking", 8)]:
        print(f"  {suite} ({n} cond)")
        for short, d in [("None", "none"), ("Spot", "spotlighting_with_delimiting"), ("Det", "transformers_pi_detector"), ("Bio", "bio_04")]:
            u, s = st[suite][d]
            print(f"    {short}: {r1(u)}/{r1(s)}")

    print("\n=== Peer baselines ===")
    peer = json.loads((ROOT / "runs/paper_peer_baselines_deepseek_progress.json").read_text())["peer_metrics"]
    stress_keys = [k for k, g in ds.items() if g.get("stress_ok")]
    for d in ("task_shield", "melon"):
        su = [peer[k][d]["utility"] * 100 for k in stress_keys]
        ss = [peer[k][d]["security"] * 100 for k in stress_keys]
        au = [peer[k][d]["utility"] * 100 for k in peer]
        as_ = [peer[k][d]["security"] * 100 for k in peer]
        ws = [peer[k][d]["utility"] * 100 for k in stress_keys if k.split("|")[3] == "workspace"]
        print(f"  {d}: stress U={r1(sum(su)/len(su))} S={r1(sum(ss)/len(ss))} unfilt U={r1(sum(au)/len(au))} S={r1(sum(as_)/len(as_))} ws_stress_U={r1(sum(ws)/len(ws))}")

    print("\n=== Drop-one elastic ===")
    drop = load_gates(ROOT / "runs/paper_bio04_dropone_elastic_progress.json")
    for d in ("bio_04", "bio_04_minus_metadata_repair", "bio_04_minus_reflection"):
        rows = [g["metrics"]["per_defense"][d]["utility"] * 100 for g in drop.values() if d in g["metrics"]["per_defense"]]
        print(f"  {d}: U={r1(sum(rows)/len(rows))}")

    print("\n=== Llama banking bio stress ===")
    bank = [g for k, g in ll.items() if g.get("stress_ok") and k.split("|")[3] == "banking"]
    u = sum(g["metrics"]["per_defense"]["bio_04"]["utility"] for g in bank) / len(bank) * 100
    print(f"  banking n={len(bank)} bio U={r1(u)}")

    print("\n=== Stress condition counts ===")
    print(f"  DS stress cond: {sum(1 for g in ds.values() if g.get('stress_ok'))}")
    print(f"  LL stress cond: {sum(1 for g in ll.values() if g.get('stress_ok'))}")


if __name__ == "__main__":
    main()