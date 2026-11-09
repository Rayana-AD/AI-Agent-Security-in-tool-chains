#!/usr/bin/env python3
"""Train provenance drift classifier (logistic v1 or embedding+MLP v2)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np

from bio_harness.provenance.classifier import (
    ProvenanceModel,
    extract_model_features,
    rule_bootstrap_mlp,
    rule_bootstrap_weights,
    train_logistic,
    train_mlp,
)
from bio_harness.provenance.embedding import DEFAULT_PROJ_DIM, get_embedding_backend, make_projection_matrix
from bio_harness.provenance.features import ProvenanceContext, extract_features, extract_full_features
from eval.agentdojo.context_builder import build_agentdojo_node_outputs

DEFAULT_LOGDIR = ROOT / "runs/agentdojo_upstream/benchmark_20260629_224640/logs"
DEFAULT_OUT_V1 = ROOT / "models/provenance_tagger_v1.json"
DEFAULT_OUT_V2 = ROOT / "models/provenance_tagger_v2_mlp.json"
CASE_STUDY_CSV = ROOT / "runs/agentdojo_upstream/case_study_20260702/paired_episodes.csv"


def _message_text(content) -> str:
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
    return str(content or "")


def _ctx_from_row(row: dict, *, node: str, review_text: str = "", tool_text: str = "", proposed: str = "") -> ProvenanceContext:
    outs = row.get("scripted_outputs") or {}
    goal = row.get("goal", "")
    return ProvenanceContext(
        user_goal=goal,
        review=review_text or outs.get("review", outs.get("plan", "")),
        tool_context=tool_text or outs.get("tool_call", ""),
        proposed_tools_json=proposed or outs.get("tool_call", ""),
        node=node,
    )


def features_for_ctx(ctx: ProvenanceContext, *, mlp: bool, backend, projector) -> list[float]:
    if mlp:
        return extract_full_features(ctx, backend=backend, projector=projector)
    return extract_features(ctx)


def features_from_agentdojo_log(path: Path, *, mlp: bool, backend, projector) -> list[float] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    messages = data.get("messages") or []
    if not messages:
        return None
    query = ""
    for m in messages:
        if m.get("role") == "user":
            query = _message_text(m.get("content"))
            break
    tool_text = ""
    proposed = []
    for m in reversed(messages):
        if m.get("role") == "tool" and not tool_text:
            tool_text = _message_text(m.get("content"))
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    proposed.append({"tool": tc.get("function"), "args": tc.get("args")})
                else:
                    proposed.append({"tool": tc.function, "args": tc.args})
            break
    node_outputs = build_agentdojo_node_outputs(query, messages, current_tool_text=tool_text)
    ctx = ProvenanceContext(
        user_goal=query,
        review=node_outputs.get("review", ""),
        tool_context=f"{node_outputs.get('tool_call', '')}\n{tool_text}",
        proposed_tools_json=json.dumps(proposed, ensure_ascii=False),
        node="tool_call",
    )
    return features_for_ctx(ctx, mlp=mlp, backend=backend, projector=projector)


def load_benign_scripted(root: Path, limit: int = 200, *, mlp: bool, backend, projector) -> tuple[list[list[float]], list[int]]:
    path = root / "data/benign/agent_tasks.jsonl"
    if not path.exists():
        return [], []
    X, y = [], []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            row = json.loads(line)
            ctx = _ctx_from_row(row, node="tool_call")
            X.append(features_for_ctx(ctx, mlp=mlp, backend=backend, projector=projector))
            y.append(0)
    return X, y


def load_scripted_subtle(root: Path, *, mlp: bool, backend, projector) -> tuple[list[list[float]], list[int]]:
    from eval.attacks.idea1_subtle_pollution import write_dataset

    write_dataset()
    path = root / "data/attacks/idea1_subtle_pollution.jsonl"
    X, y = [], []
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            outs = row.get("scripted_outputs", {})
            review = outs.get("review", "")
            plan = outs.get("plan", "")
            tool = outs.get("tool_call", "")
            for node, review_text, tool_text, proposed in (
                ("review", review, "", ""),
                ("tool_call", review, tool, tool),
            ):
                ctx = ProvenanceContext(
                    user_goal=row.get("goal", ""),
                    review=review_text or plan,
                    tool_context=tool_text,
                    proposed_tools_json=proposed,
                    node=node,
                )
                X.append(features_for_ctx(ctx, mlp=mlp, backend=backend, projector=projector))
                y.append(1)
    return X, y


def load_agentdojo_pairs(logdir: Path, csv_path: Path, *, mlp: bool, backend, projector) -> tuple[list[list[float]], list[int]]:
    if not csv_path.exists():
        return [], []
    X: list[list[float]] = []
    y: list[int] = []
    seen: set[str] = set()

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("eval_mode") != "paired":
                continue
            defense = row["defense"]
            if defense not in ("none", "bio_idea1", "bio_full", "repeat_user_prompt"):
                continue
            task_key = row["task_key"]
            dedupe = f"{task_key}::{defense}"
            if dedupe in seen:
                continue
            seen.add(dedupe)

            log_rel = row.get("log_path", "")
            log_path = logdir / defense / log_rel
            if not log_path.exists():
                suite, ut, it = task_key.split("/")
                hits = list((logdir / defense).rglob(f"{ut}/tool_knowledge/{it}.json"))
                log_path = hits[0] if hits else None
            if log_path is None or not Path(log_path).exists():
                continue

            feats = features_from_agentdojo_log(Path(log_path), mlp=mlp, backend=backend, projector=projector)
            if feats is None:
                continue
            X.append(feats)
            if defense == "none" and row["attack_success"] == "True":
                y.append(1)
            else:
                y.append(0)
    return X, y


def main() -> None:
    parser = argparse.ArgumentParser(description="Train provenance drift classifier")
    parser.add_argument("--logdir", type=Path, default=DEFAULT_LOGDIR)
    parser.add_argument("--csv", type=Path, default=CASE_STUDY_CSV)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--bootstrap-only", action="store_true")
    parser.add_argument("--mlp", action="store_true", help="Train embedding+MLP v2 model")
    parser.add_argument(
        "--embed-backend",
        default="hash",
        choices=["hash", "minilm"],
        help="Frozen embedder for MLP features (hash=deterministic, minilm=MiniLM)",
    )
    parser.add_argument("--proj-dim", type=int, default=DEFAULT_PROJ_DIM)
    args = parser.parse_args()

    out_path = args.out or (DEFAULT_OUT_V2 if args.mlp else DEFAULT_OUT_V1)

    if args.bootstrap_only:
        model = rule_bootstrap_mlp(embed_backend=args.embed_backend, proj_dim=args.proj_dim) if args.mlp else rule_bootstrap_weights()
        model.save(out_path)
        print(f"Saved bootstrap model → {out_path}")
        return

    backend = get_embedding_backend(args.embed_backend) if args.mlp else None
    projector = make_projection_matrix(proj_dim=args.proj_dim) if args.mlp else None

    X_list, y_list = load_agentdojo_pairs(args.logdir, args.csv, mlp=args.mlp, backend=backend, projector=projector)
    sx, sy = load_scripted_subtle(ROOT, mlp=args.mlp, backend=backend, projector=projector)
    bx, by = load_benign_scripted(ROOT, mlp=args.mlp, backend=backend, projector=projector)
    X_list.extend(sx + bx)
    y_list.extend(sy + by)

    if len(X_list) < 10:
        print(f"Only {len(X_list)} samples — saving bootstrap model")
        model = rule_bootstrap_mlp(embed_backend=args.embed_backend, proj_dim=args.proj_dim) if args.mlp else rule_bootstrap_weights()
        model.save(out_path)
        return

    X = np.asarray(X_list, dtype=np.float64)
    y = np.asarray(y_list, dtype=np.float64)
    if args.mlp:
        model = train_mlp(
            X,
            y,
            epochs=args.epochs,
            embed_backend=args.embed_backend,
            proj_dim=args.proj_dim,
        )
        model.embed_proj = projector
    else:
        model = train_logistic(X, y, epochs=args.epochs)

    probs = np.array([model.predict_proba(x) for x in X_list])
    pred = (probs >= model.threshold).astype(int)
    acc = float(np.mean(pred == y))
    print(
        f"Train n={len(y)} pos={int(y.sum())} acc={acc:.3f} "
        f"threshold={model.threshold:.3f} type={model.model_type}"
    )

    model.save(out_path)
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
