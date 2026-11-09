"""Reflective provenance — dot-product mirror (pre-activation attention stage).

Transformer value path applies σ and MLP *after* QK^T (diffuse scattering).  For
provenance we stay at the **raw dot-product stage**: one fixed query from the user
goal, keys from process segments / cross-node slots.  Householder reflection uses
only these dot coordinates — no softmax, no activation, no decoder MLP, no SVD.

Mathematical core
-----------------

Fixed dimension :math:`d`, scale :math:`s = 1/\\sqrt{d}`.

**Project** (single-pass signed hash, O(tokens)):

.. math::

    q = \\mathrm{unit}(P(g)), \\quad k_t = \\mathrm{unit}(P(s_t))

**Attention-style score** (mirrors QK^T before σ):

.. math::

    \\alpha_t = s \\, q^\\top k_t \\in [-1, 1]

**Householder reflection** in the same projected space:

.. math::

    \\rho(k) = k - 2 (q^\\top k)\\, q, \\quad
    \\delta_{\\mathrm{refl}} = \\|\\rho(k_{\\mathrm{tool}}) - \\rho(k_{\\mathrm{review}})\\|_2

**Streaming intercept** (timely truncate, O(1) per segment):

- hemisphere flip: :math:`\\mathrm{sign}(\\alpha_t) \\ne \\mathrm{sign}(\\alpha_{t-1})`
- loop without progress: high :math:`k_t^\\top k_{t-2}` while :math:`|\\alpha_t - \\alpha_0|` stays small
- cross-node breach: :math:`\\delta_{\\mathrm{refl}} > \\tau` when goal–tool token overlap is low

Complexity: :math:`O(T \\cdot d)` for :math:`T` segments; early exit on first intercept.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bio_harness.provenance.features import ProvenanceContext
from bio_harness.provenance.reflection_scales import (
    ReflectionSaturationScales,
    load_process_scales,
    resolve_saturation_scales,
)

_EPS = 1e-9
_DEFAULT_DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < _EPS:
        return v
    return v / n


def _grams(text: str) -> list[str]:
    tl = text.lower()
    tokens = _TOKEN_RE.findall(tl)
    grams: list[str] = list(tokens)
    for tok in tokens:
        if len(tok) >= 3:
            for j in range(len(tok) - 2):
                grams.append(tok[j : j + 3])
    return grams


@dataclass(frozen=True)
class DotKeyProjector:
    """Fixed Q/K projection — same role as W_Q, W_K but deterministic and tiny."""

    dim: int = _DEFAULT_DIM

    @property
    def scale(self) -> float:
        return 1.0 / math.sqrt(float(self.dim))

    def project(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float64)
        for g in _grams(text):
            h = int(hashlib.sha256(g.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        return _unit(vec)

    def score(self, q: np.ndarray, k: np.ndarray) -> float:
        """α = (q·k) / sqrt(d)."""
        return float(np.dot(q, k)) * self.scale


def householder_reflect(v: np.ndarray, q: np.ndarray) -> np.ndarray:
    """ρ(k) = k - 2(q·k)q with unit query q."""
    q = _unit(q)
    return v - 2.0 * float(np.dot(q, v)) * q


def goal_alignment(v: np.ndarray, q: np.ndarray) -> float:
    return float(np.dot(_unit(v), _unit(q)))


def split_process_segments(text: str, *, min_len: int = 12) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r"(?i)(?<=[.!?])\s+|(?=\bWait!|\bWait,)", text)
    segments = [p.strip() for p in parts if len(p.strip()) >= min_len]
    return segments or [text.strip()]


def _path_overlap(goal: str, tool: str) -> float:
    gt = set(_TOKEN_RE.findall(goal.lower()))
    tt = set(_TOKEN_RE.findall(tool.lower()))
    if not gt or not tt:
        return 0.0
    return len(gt & tt) / len(gt | tt)


path_overlap = _path_overlap


def _tool_slot_for_continuity(tool_slot: str) -> str:
    """Overlap targets arg values (user-bindable), not tool schema tokens."""
    import json

    text = (tool_slot or "").strip()
    if not text:
        return text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text

    items = data if isinstance(data, list) else [data]
    chunks: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        args = item.get("args")
        if isinstance(args, dict):
            chunks.append(json.dumps(args, ensure_ascii=False))
        elif "tool" not in item and "function" not in item:
            chunks.append(json.dumps(item, ensure_ascii=False))
    return "\n".join(chunks) if chunks else text


_CONTINUITY_META_KEYS = frozenset({"permission", "permissions", "id", "file_id", "tool_call_id"})


def _collect_string_values(value: Any, *, out: list[str], parent_key: str = "") -> None:
    if isinstance(value, dict):
        for key, val in value.items():
            key_l = str(key).lower()
            if key_l in _CONTINUITY_META_KEYS:
                continue
            _collect_string_values(val, out=out, parent_key=key_l)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _collect_string_values(v, out=out, parent_key=parent_key)
        return
    if isinstance(value, str) and len(value.strip()) >= 3:
        out.append(value.strip())


# Goal cues that make a write-tool continuous with the user objective (banking / messaging).
# Keep cues tool-specific: avoid generic words like "payment" matching send_money on rent tasks.
_TOOL_GOAL_CUES: dict[str, tuple[str, ...]] = {
    "update_scheduled_transaction": (
        "rent",
        "landlord",
        "scheduled",
        "schedule",
        "adjust",
        "recurring",
    ),
    "send_money": (
        "refund",
        "difference",
        "send them",
        "send back",
        "transfer",
    ),
    "schedule_transaction": (
        "schedule",
        "rent",
        "landlord",
        "recurring",
    ),
}


def _extract_tool_names(tool_slot: str) -> list[str]:
    import json

    text = (tool_slot or "").strip()
    if not text:
        return []
    names: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        for m in re.findall(r'"tool"\s*:\s*"([^"]+)"', text, re.I):
            names.append(m.lower())
        for m in re.findall(r"(?im)^tool:\s*(\S+)", text):
            names.append(m.lower())
        return names
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("tool") or item.get("function") or "").lower()
            if name:
                names.append(name)
    return names


def tool_goal_affinity(goal: str, tool_slot: str) -> float:
    """Lexical affinity between user goal cues and the proposed write tool."""
    g = (goal or "").lower()
    if not g.strip():
        return 0.0
    best = 0.0
    for name in _extract_tool_names(tool_slot):
        cues = _TOOL_GOAL_CUES.get(name, ())
        if not cues:
            # Tool-name tokens vs goal (update_scheduled_transaction → update scheduled …)
            name_overlap = path_overlap(goal, name.replace("_", " "))
            best = max(best, name_overlap)
            continue
        hits = sum(1 for c in cues if c in g)
        if hits:
            best = max(best, min(0.08 + 0.04 * (hits - 1), 0.24))
        name_overlap = path_overlap(goal, name.replace("_", " "))
        best = max(best, name_overlap)
    return best


def continuity_overlap(goal: str, tool_slot: str) -> float:
    """Max overlap between goal and bindable args, tool name, or action-cue affinity."""
    import json

    affinity = tool_goal_affinity(goal, tool_slot)
    slot = _tool_slot_for_continuity(tool_slot)
    if not slot.strip():
        return affinity
    try:
        data = json.loads(slot)
    except json.JSONDecodeError:
        return max(path_overlap(goal, slot), affinity)

    values: list[str] = []
    if isinstance(data, list):
        for item in data:
            _collect_string_values(item, out=values)
    else:
        _collect_string_values(data, out=values)
    if not values:
        return max(path_overlap(goal, slot), affinity)
    per_value = max(path_overlap(goal, value) for value in values)
    combined = path_overlap(goal, " ".join(values))
    return max(per_value, combined, affinity)


GOAL_CONTINUITY_OVERLAP = 0.08


@dataclass
class ReflectionMetrics:
    """Dot-mirror diagnostics only."""

    delta_refl: float = 0.0
    alpha_review: float = 0.0
    alpha_tool: float = 0.0
    delta_alpha: float = 0.0
    sign_flips: int = 0
    dot_loop: float = 0.0
    alpha_progress: float = 0.0
    path_overlap: float = 0.0
    n_segments: int = 0
    truncated_at: int | None = None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "delta_refl": round(self.delta_refl, 4),
            "alpha_review": round(self.alpha_review, 4),
            "alpha_tool": round(self.alpha_tool, 4),
            "delta_alpha": round(self.delta_alpha, 4),
            "sign_flips": self.sign_flips,
            "dot_loop": round(self.dot_loop, 4),
            "alpha_progress": round(self.alpha_progress, 4),
            "path_overlap": round(self.path_overlap, 4),
            "n_segments": self.n_segments,
            "truncated_at": self.truncated_at,
        }


def reflection_goal_continuous(metrics: ReflectionMetrics | None) -> bool:
    """True when the proposed action is lexically continuous with the user goal."""
    return bool(metrics and metrics.path_overlap >= GOAL_CONTINUITY_OVERLAP)


def reflection_feature_slice(
    metrics: ReflectionMetrics | None,
    *,
    scales: ReflectionSaturationScales | None = None,
) -> tuple[float, float, float]:
    """Map dot-mirror diagnostics into provenance feature slots 5–7.

    Slots are **not** additively fused (old Eq. 7): Eq. 5 and Eq. 6 stay on separate
    axes so the MLP can combine them; process trajectories use segment-calibrated scales.
    """
    if metrics is None:
        return (0.0, 0.0, 0.0)
    if scales is None:
        process_only = metrics.alpha_review == 0.0 and metrics.alpha_tool == 0.0
        if process_only and metrics.n_segments >= 2:
            scales = load_process_scales() or resolve_saturation_scales()
        else:
            scales = resolve_saturation_scales()
    norm_alpha = scales.norm_alpha(metrics.delta_alpha)
    norm_shift = scales.norm_shift(metrics.delta_refl)
    churn = min(metrics.sign_flips / 3.0, 1.0) * 0.4 + min(metrics.dot_loop, 1.0) * 0.6
    if metrics.truncated_at is not None:
        churn = max(churn, 1.0)
    return (norm_alpha, norm_shift, churn)


@dataclass
class ReflectionProbeResult:
    score: float
    block_recommended: bool
    reason: str
    metrics: ReflectionMetrics = field(default_factory=ReflectionMetrics)

    def as_dict(self) -> dict:
        out = {
            "score": round(self.score, 4),
            "block_recommended": self.block_recommended,
            "reason": self.reason,
        }
        out.update(self.metrics.as_dict())
        return out


@dataclass
class DotStreamResult:
    alphas: list[float]
    keys: list[np.ndarray]
    sign_flips: int
    dot_loop: float
    alpha_progress: float
    truncated_at: int | None
    intercept_reason: str


def stream_dot_reflect(
    projector: DotKeyProjector,
    goal: str,
    segments: list[str],
    *,
    flip_limit: int = 2,
    loop_threshold: float = 0.52,
    min_segments_before_loop: int = 4,
) -> DotStreamResult:
    """Single-pass Q·K trajectory with early intercept (no batch embed, no SVD)."""
    q = projector.project(goal)
    alphas: list[float] = []
    keys: list[np.ndarray] = []
    sign_flips = 0
    truncated_at: int | None = None
    intercept_reason = ""

    for i, seg in enumerate(segments):
        k = projector.project(seg)
        alpha = projector.score(q, k)
        alphas.append(alpha)
        keys.append(k)

        if i > 0 and alphas[i - 1] != 0.0 and (alpha * alphas[i - 1] < 0):
            sign_flips += 1

        if sign_flips >= flip_limit and truncated_at is None:
            truncated_at = i + 1
            intercept_reason = "dot_hemisphere_flip"

        if (
            truncated_at is None
            and i >= min_segments_before_loop
            and i >= 2
        ):
            stag = float(np.dot(keys[i], keys[i - 2]))
            progress = abs(alpha - alphas[0])
            if stag >= loop_threshold and progress < 0.12:
                truncated_at = i + 1
                intercept_reason = "dot_loop_no_progress"

        if truncated_at is not None:
            break

    dot_loop = 0.0
    if len(keys) >= 3:
        stags = [float(np.dot(keys[i], keys[i - 2])) for i in range(2, len(keys))]
        dot_loop = float(np.mean(stags)) * max(0.0, 1.0 - abs(alphas[-1] - alphas[0]))
    alpha_progress = abs(alphas[-1] - alphas[0]) if alphas else 0.0

    return DotStreamResult(
        alphas=alphas,
        keys=keys,
        sign_flips=sign_flips,
        dot_loop=dot_loop,
        alpha_progress=alpha_progress,
        truncated_at=truncated_at,
        intercept_reason=intercept_reason,
    )


@dataclass
class ReflectionProbe:
    """Dot-product mirror probe — step score min(1, Eq.5 norm + Eq.6 excess norm)."""

    dim: int = _DEFAULT_DIM
    block_threshold: float = 0.40
    flip_limit: int = 2
    loop_threshold: float = 0.52
    delta_refl_threshold: float | None = None
    delta_alpha_threshold: float | None = None
    saturation_scales: ReflectionSaturationScales | None = None
    process_scales: ReflectionSaturationScales | None = None

    def __post_init__(self) -> None:
        self._proj = DotKeyProjector(dim=self.dim)
        if self.saturation_scales is None:
            self.saturation_scales = resolve_saturation_scales()
        if self.process_scales is None:
            self.process_scales = load_process_scales() or self.saturation_scales
        if self.delta_alpha_threshold is None:
            self.delta_alpha_threshold = self.saturation_scales.tau_alpha
        if self.delta_refl_threshold is None:
            self.delta_refl_threshold = self.saturation_scales.tau_delta

    def _step_score(
        self,
        delta_alpha: float,
        delta_refl: float,
        *,
        for_process: bool = False,
    ) -> float:
        """Per-step reflection risk: min(1, α̂ + δ̂) from calibrated Eq. 5/6 only."""
        scales = self.process_scales if for_process else self.saturation_scales
        if scales is None:
            scales = ReflectionSaturationScales(
                tau_alpha=float(self.delta_alpha_threshold or 0.45),
                tau_delta=float(self.delta_refl_threshold or 0.22),
            )
        return scales.step_fused(delta_alpha, delta_refl)

    def _trajectory_step_metrics(
        self, q: np.ndarray, segments: list[str]
    ) -> tuple[float, float, float, int | None, int]:
        """Step-wise α̂+δ̂; report peak score and hot-step count."""
        if len(segments) < 2:
            return (0.0, 0.0, 0.0, None, 0)
        keys = [self._proj.project(s) for s in segments]
        alphas = [self._proj.score(q, k) for k in keys]
        rhos = [householder_reflect(k, q) for k in keys]
        max_score = 0.0
        max_da = 0.0
        max_dr = 0.0
        hot_steps = 0
        truncated_at: int | None = None
        for i in range(1, len(segments)):
            da = abs(alphas[i] - alphas[i - 1])
            dr = float(np.linalg.norm(rhos[i] - rhos[i - 1]))
            step_c = self._step_score(da, dr, for_process=True)
            scales = self.process_scales or self.saturation_scales
            norm_alpha = scales.norm_alpha(da) if scales is not None else 0.0
            norm_shift = scales.norm_shift(dr) if scales is not None else 0.0
            # Eq. 7 is additive, but sustained process evidence must be
            # supported by both calibrated components. The support floor is
            # derived from τ_refl, not an additional fitted weight.
            component_supported = min(norm_alpha, norm_shift) >= self.block_threshold / 2.0
            if step_c >= self.block_threshold and component_supported:
                hot_steps += 1
            if step_c > max_score:
                max_score = step_c
                max_da = da
                max_dr = dr
            if step_c >= self.block_threshold and truncated_at is None:
                truncated_at = i + 1
        return (max_score, max_da, max_dr, truncated_at, hot_steps)

    def analyze_process(self, goal: str, process_text: str) -> ReflectionProbeResult:
        segments = split_process_segments(process_text)
        if len(segments) < 2:
            return ReflectionProbeResult(
                0.0,
                False,
                "reflection_insufficient_segments",
                ReflectionMetrics(n_segments=len(segments)),
            )

        q = self._proj.project(goal)
        score, max_da, max_dr, step_trunc, hot_steps = self._trajectory_step_metrics(q, segments)
        stream = stream_dot_reflect(
            self._proj,
            goal,
            segments,
            flip_limit=self.flip_limit,
            loop_threshold=self.loop_threshold,
        )

        metrics = ReflectionMetrics(
            delta_refl=max_dr,
            delta_alpha=max_da,
            sign_flips=stream.sign_flips,
            dot_loop=stream.dot_loop,
            alpha_progress=stream.alpha_progress,
            n_segments=len(segments),
            truncated_at=stream.truncated_at or step_trunc,
        )

        # Long process: sustained elevated α̂+δ̂ steps, or streaming intercept — lone spike does not block.
        sustained = hot_steps >= 2 and score >= self.block_threshold
        block = sustained or stream.truncated_at is not None
        return ReflectionProbeResult(
            score,
            block,
            "reflection_step_drift" if block else "reflection_process_ok",
            metrics,
        )

    def analyze_context(self, ctx: ProvenanceContext, *, process_text: str = "") -> ReflectionProbeResult:
        goal = ctx.user_goal or ""
        if not goal.strip():
            return ReflectionProbeResult(0.0, False, "reflection_no_goal")

        proc_result: ReflectionProbeResult | None = None
        if process_text.strip():
            proc_result = self.analyze_process(goal, process_text)

        review = ctx.review or ""
        tool = ctx.tool_context or ""
        tool_slot = ctx.proposed_tools_json.strip() or tool.strip()
        if not review.strip() and not tool_slot.strip():
            if proc_result is not None:
                return proc_result
            return ReflectionProbeResult(0.0, False, "reflection_no_untrusted")

        q = self._proj.project(goal)
        k_review = self._proj.project(review)
        k_tool = self._proj.project(tool_slot)

        alpha_review = self._proj.score(q, k_review)
        alpha_tool = self._proj.score(q, k_tool)
        delta_alpha = abs(alpha_review - alpha_tool)

        rho_r = householder_reflect(k_review, q)
        rho_t = householder_reflect(k_tool, q)
        delta_refl = float(np.linalg.norm(rho_t - rho_r))

        overlap = continuity_overlap(goal, tool_slot)
        segments = split_process_segments(f"{review}\n{tool}")
        stream = (
            stream_dot_reflect(self._proj, goal, segments, flip_limit=self.flip_limit)
            if len(segments) >= 3
            else None
        )

        metrics = ReflectionMetrics(
            delta_refl=delta_refl,
            alpha_review=alpha_review,
            alpha_tool=alpha_tool,
            delta_alpha=delta_alpha,
            sign_flips=stream.sign_flips if stream else 0,
            dot_loop=stream.dot_loop if stream else 0.0,
            alpha_progress=stream.alpha_progress if stream else abs(alpha_tool - alpha_review),
            path_overlap=overlap,
            n_segments=len(segments),
            truncated_at=proc_result.metrics.truncated_at if proc_result else (stream.truncated_at if stream else None),
        )

        if overlap >= 0.08:
            return ReflectionProbeResult(0.0, False, "reflection_aligned", metrics)

        cross = self._step_score(delta_alpha, delta_refl)
        proc_step = proc_result.score if proc_result is not None else 0.0
        score = max(cross, proc_step)
        block = score >= self.block_threshold
        if block and cross >= self.block_threshold:
            reason = "reflection_cross_node_mismatch"
        elif block:
            reason = "reflection_step_drift"
        else:
            reason = "reflection_aligned"
        return ReflectionProbeResult(score, block, reason, metrics)


def default_reflection_probe(**kwargs) -> ReflectionProbe:
    return ReflectionProbe(**kwargs)


def get_reflection_probe(config) -> ReflectionProbe | None:
    """Build dot-reflection probe from harness config, or None if disabled."""
    if not getattr(config, "use_reflection_probe", False):
        return None
    threshold = getattr(config, "reflection_block_threshold", 0.40)
    dim = getattr(config, "reflection_dot_dim", 64)
    scales = resolve_saturation_scales(config)
    explicit_a = getattr(config, "reflection_tau_alpha", None)
    explicit_d = getattr(config, "reflection_tau_delta", None)
    proc = load_process_scales()
    return ReflectionProbe(
        block_threshold=float(threshold),
        dim=int(dim),
        saturation_scales=scales,
        process_scales=proc,
        delta_alpha_threshold=float(explicit_a) if explicit_a is not None else None,
        delta_refl_threshold=float(explicit_d) if explicit_d is not None else None,
    )

