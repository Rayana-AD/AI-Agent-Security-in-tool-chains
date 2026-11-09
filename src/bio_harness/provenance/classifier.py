"""Provenance classifiers: logistic regression and small MLP (numpy, no sklearn)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from bio_harness.provenance.embedding import (
    DEFAULT_PROJ_DIM,
    get_embedding_backend,
    make_projection_matrix,
)
from bio_harness.provenance.features import feature_dim, full_feature_dim


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


@dataclass
class ProvenanceModel:
    """Unified provenance scorer: logistic (v1) or MLP + embeddings (v2)."""

    model_type: str = "logistic"
    feature_dim: int = 24
    threshold: float = 0.5
    version: str = "v1"
    # logistic
    weights: np.ndarray | None = None
    bias: float = 0.0
    # mlp
    hidden_dim: int = 32
    w1: np.ndarray | None = None
    b1: np.ndarray | None = None
    w2: np.ndarray | None = None
    b2: float = 0.0
    # embedding config (mlp only)
    embed_backend: str = "hash"
    embed_proj: np.ndarray | None = None
    proj_dim: int = DEFAULT_PROJ_DIM
    handcrafted_dim: int = 24
    _backend: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.model_type == "logistic" and self.weights is None:
            self.weights = np.zeros(self.feature_dim, dtype=np.float64)

    @property
    def uses_embeddings(self) -> bool:
        return self.model_type == "mlp"

    def backend(self):
        if not self.uses_embeddings:
            return None
        if self._backend is None:
            self._backend = get_embedding_backend(self.embed_backend)
        return self._backend

    def _logit(self, x: np.ndarray) -> float:
        if self.model_type == "logistic":
            assert self.weights is not None
            return float(np.dot(self.weights, x) + self.bias)
        assert self.w1 is not None and self.b1 is not None and self.w2 is not None
        h = np.tanh(self.w1 @ x + self.b1)
        return float(self.w2 @ h + self.b2)

    def predict_proba(self, features: list[float] | np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64)
        if x.shape[0] != self.feature_dim:
            raise ValueError(f"Expected {self.feature_dim} features, got {x.shape[0]}")
        return float(_sigmoid(self._logit(x)))

    def predict_drift(self, features: list[float] | np.ndarray) -> bool:
        return self.predict_proba(features) >= self.threshold

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_type": self.model_type,
            "feature_dim": self.feature_dim,
            "threshold": self.threshold,
            "version": self.version,
        }
        if self.model_type == "logistic":
            payload["weights"] = self.weights.tolist() if self.weights is not None else []
            payload["bias"] = self.bias
        else:
            payload["hidden_dim"] = self.hidden_dim
            payload["w1"] = self.w1.tolist() if self.w1 is not None else []
            payload["b1"] = self.b1.tolist() if self.b1 is not None else []
            payload["w2"] = self.w2.tolist() if self.w2 is not None else []
            payload["b2"] = self.b2
            payload["embed_backend"] = self.embed_backend
            payload["proj_dim"] = self.proj_dim
            payload["handcrafted_dim"] = self.handcrafted_dim
            if self.embed_proj is not None:
                payload["embed_proj"] = self.embed_proj.tolist()
        return payload

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_payload(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> ProvenanceModel:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        model_type = str(data.get("model_type", "logistic"))
        if model_type == "mlp":
            proj_dim = int(data.get("proj_dim", DEFAULT_PROJ_DIM))
            embed_proj = data.get("embed_proj")
            return cls(
                model_type="mlp",
                feature_dim=int(data.get("feature_dim", full_feature_dim(proj_dim=proj_dim))),
                threshold=float(data.get("threshold", 0.5)),
                version=str(data.get("version", "v2_mlp")),
                hidden_dim=int(data.get("hidden_dim", 32)),
                w1=np.asarray(data["w1"], dtype=np.float64),
                b1=np.asarray(data["b1"], dtype=np.float64),
                w2=np.asarray(data["w2"], dtype=np.float64),
                b2=float(data["b2"]),
                embed_backend=str(data.get("embed_backend", "hash")),
                embed_proj=np.asarray(embed_proj, dtype=np.float64) if embed_proj else None,
                proj_dim=proj_dim,
                handcrafted_dim=int(data.get("handcrafted_dim", feature_dim())),
            )
        return cls(
            model_type="logistic",
            weights=np.asarray(data["weights"], dtype=np.float64),
            bias=float(data["bias"]),
            threshold=float(data.get("threshold", 0.5)),
            feature_dim=int(data.get("feature_dim", feature_dim())),
            version=str(data.get("version", "v1")),
        )


def _pick_threshold(probs: np.ndarray, y: np.ndarray, *, max_fpr: float = 0.08) -> float:
    best_t, best_rec = 0.5, -1.0
    for t in np.linspace(0.2, 0.95, 16):
        pred = (probs >= t).astype(np.float64)
        tp = float(np.sum((pred == 1) & (y == 1)))
        fp = float(np.sum((pred == 1) & (y == 0)))
        tn = float(np.sum((pred == 0) & (y == 0)))
        fn = float(np.sum((pred == 0) & (y == 1)))
        fpr = fp / max(fp + tn, 1e-9)
        rec = tp / max(tp + fn, 1e-9)
        if fpr <= max_fpr and rec > best_rec:
            best_rec, best_t = rec, float(t)
    if best_rec >= 0:
        return best_t
    best_t, best_f1 = 0.5, -1.0
    for t in np.linspace(0.25, 0.9, 14):
        pred = (probs >= t).astype(np.float64)
        tp = float(np.sum((pred == 1) & (y == 1)))
        fp = float(np.sum((pred == 1) & (y == 0)))
        fn = float(np.sum((pred == 0) & (y == 1)))
        prec = tp / max(tp + fp, 1e-9)
        rec = tp / max(tp + fn, 1e-9)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t


def train_logistic(
    X: np.ndarray,
    y: np.ndarray,
    *,
    lr: float = 0.15,
    epochs: int = 400,
    l2: float = 0.01,
) -> ProvenanceModel:
    """Binary logistic regression via gradient descent."""
    n, d = X.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    for _ in range(epochs):
        logits = np.clip(X @ w + b, -30, 30)
        preds = 1.0 / (1.0 + np.exp(-logits))
        err = preds - y
        grad_w = (X.T @ err) / n + l2 * w
        grad_b = float(np.mean(err))
        w -= lr * grad_w
        b -= lr * grad_b

    probs = 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -30, 30)))
    best_t = _pick_threshold(probs, y)
    return ProvenanceModel(
        model_type="logistic",
        weights=w,
        bias=b,
        threshold=best_t,
        feature_dim=d,
        version="v1",
    )


def train_mlp(
    X: np.ndarray,
    y: np.ndarray,
    *,
    hidden_dim: int = 32,
    lr: float = 0.08,
    epochs: int = 600,
    l2: float = 0.005,
    embed_backend: str = "hash",
    proj_dim: int = DEFAULT_PROJ_DIM,
) -> ProvenanceModel:
    """Two-layer tanh MLP with frozen embedding features precomputed in X."""
    n, d = X.shape
    rng = np.random.default_rng(7)
    w1 = rng.standard_normal((hidden_dim, d)) * 0.05
    b1 = np.zeros(hidden_dim, dtype=np.float64)
    w2 = rng.standard_normal(hidden_dim) * 0.05
    b2 = 0.0

    for _ in range(epochs):
        z1 = X @ w1.T + b1
        h = np.tanh(z1)
        logits = h @ w2 + b2
        preds = _sigmoid(logits)
        err = preds - y
        grad_logits = err / n
        grad_w2 = h.T @ grad_logits + l2 * w2
        grad_b2 = float(np.sum(grad_logits))
        grad_h = np.outer(grad_logits, w2)
        grad_z1 = grad_h * (1.0 - h**2)
        grad_w1 = grad_z1.T @ X + l2 * w1
        grad_b1 = np.sum(grad_z1, axis=0)
        w2 -= lr * grad_w2
        b2 -= lr * grad_b2
        w1 -= lr * grad_w1
        b1 -= lr * grad_b1

    z1 = X @ w1.T + b1
    h = np.tanh(z1)
    logits = h @ w2 + b2
    probs = _sigmoid(logits)
    best_t = _pick_threshold(probs, y)

    return ProvenanceModel(
        model_type="mlp",
        feature_dim=d,
        threshold=best_t,
        version="v2_mlp",
        hidden_dim=hidden_dim,
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        embed_backend=embed_backend,
        embed_proj=make_projection_matrix(proj_dim=proj_dim),
        proj_dim=proj_dim,
        handcrafted_dim=feature_dim(),
    )


def rule_bootstrap_weights() -> ProvenanceModel:
    """Untrained logistic prior aligned with hand rules."""
    d = feature_dim()
    w = np.zeros(d, dtype=np.float64)
    idx = {
        "has_info": 2,
        "entity_drift": 4,
        "reflection_cross": 5,
        "reflection_churn": 6,
        "reflection_intercept": 7,
        "send_money": 14,
        "invite_slack": 15,
        "secrets": 20,
    }
    w[idx["has_info"]] = 1.2
    w[idx["entity_drift"]] = 1.5
    w[idx["reflection_cross"]] = 1.1
    w[idx["reflection_churn"]] = 0.9
    w[idx["reflection_intercept"]] = 1.0
    w[1] = -1.2
    w[0] = -0.5
    return ProvenanceModel(
        model_type="logistic",
        weights=w,
        bias=-0.8,
        threshold=0.45,
        feature_dim=d,
        version="bootstrap",
    )


def rule_bootstrap_mlp(*, embed_backend: str = "hash", proj_dim: int = DEFAULT_PROJ_DIM) -> ProvenanceModel:
    """MLP initialized from logistic prior on handcrafted slice; random on embedding slice."""
    logistic = rule_bootstrap_weights()
    d = full_feature_dim(proj_dim=proj_dim)
    hidden = 32
    w1 = np.random.default_rng(11).standard_normal((hidden, d)) * 0.02
    b1 = np.zeros(hidden, dtype=np.float64)
    w2 = np.zeros(hidden, dtype=np.float64)
    w2[0] = 1.0
    b2 = logistic.bias
    w1[0, : feature_dim()] = logistic.weights * 0.5
    return ProvenanceModel(
        model_type="mlp",
        feature_dim=d,
        threshold=logistic.threshold,
        version="bootstrap_mlp",
        hidden_dim=hidden,
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        embed_backend=embed_backend,
        embed_proj=make_projection_matrix(proj_dim=proj_dim),
        proj_dim=proj_dim,
        handcrafted_dim=feature_dim(),
    )


def extract_model_features(
    ctx,
    model: ProvenanceModel,
    *,
    reflection_metrics: Any | None = None,
) -> list[float]:
    from bio_harness.provenance.features import extract_features, extract_full_features

    if model.uses_embeddings:
        assert model.embed_proj is not None
        return extract_full_features(
            ctx,
            backend=model.backend(),
            projector=model.embed_proj,
            reflection_metrics=reflection_metrics,
        )
    return extract_features(ctx, reflection_metrics=reflection_metrics)
