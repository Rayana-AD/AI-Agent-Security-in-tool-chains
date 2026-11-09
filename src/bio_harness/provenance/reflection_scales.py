"""Empirical scales for hash-space reflection (Eq. 5 goal, Eq. 6 shift).

Shuffle uses fixed (τ_Δ, τ_max) anchored to τ_b — unchanged here.

Eq. 5:  norm_α = min(1, Δα / τ_α)
Eq. 6:  norm_δ = min(1, max(0, δ − δ₀) / τ_δ⁺)   — excess above benign baseline δ₀, not δ/τ on raw δ
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

PAPER_TAU_ALPHA = 0.45
# Benign typical inter-segment δ in hash space (~1.0–1.1); excess spread for fallback.
PAPER_DELTA_BASELINE = 1.05
PAPER_TAU_DELTA_EXCESS = 0.22

DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "reflection_scales.json"
DEFAULT_PROCESS_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / ".cache" / "reflection_scales_process.json"
)

StatKind = Literal["median", "mean", "p75", "p90", "p95"]
_EPS = 1e-9


@dataclass(frozen=True)
class ReflectionSaturationScales:
    """τ_α scales goal divergence; δ₀ + τ_δ⁺ scale representational *excess* shift."""

    tau_alpha: float
    tau_delta: float  # τ_δ⁺ on excess = max(0, δ − δ₀)
    delta_baseline: float = PAPER_DELTA_BASELINE  # δ₀
    stat: StatKind = "median"
    n_pairs: int = 0
    mean_alpha: float = 0.0
    mean_delta: float = 0.0
    median_alpha: float = 0.0
    median_delta: float = 0.0
    mean_delta_excess: float = 0.0
    source: str = "paper_fallback"

    def norm_alpha(self, delta_alpha: float) -> float:
        return float(min(1.0, delta_alpha / max(self.tau_alpha, _EPS)))

    def norm_shift(self, delta_refl: float) -> float:
        excess = max(0.0, delta_refl - self.delta_baseline)
        return float(min(1.0, excess / max(self.tau_delta, _EPS)))

    def step_fused(self, delta_alpha: float, delta_refl: float) -> float:
        """Eq. 7: min(1, α̂ + δ̂) — same Eq. 5/6 components, additive (not min-select)."""
        return float(
            min(1.0, self.norm_alpha(delta_alpha) + self.norm_shift(delta_refl))
        )

    def step_conjunctive(self, delta_alpha: float, delta_refl: float) -> float:
        """Legacy min-fuse; prefer step_fused for paper Eq. 7."""
        return float(min(1.0, self.norm_alpha(delta_alpha), self.norm_shift(delta_refl)))

    def as_dict(self) -> dict:
        return asdict(self)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def _stat(values: list[float], kind: StatKind) -> float:
    if not values:
        return 0.0
    if kind == "mean":
        return float(statistics.fmean(values))
    if kind == "p75":
        return _percentile(sorted(values), 75.0)
    if kind == "p90":
        return _percentile(sorted(values), 90.0)
    if kind == "p95":
        return _percentile(sorted(values), 95.0)
    return float(statistics.median(values))


def scales_from_pairs(
    pairs: Iterable[tuple[float, float]],
    *,
    stat: StatKind = "p75",
    source: str = "calibrated",
    min_tau_alpha: float = 0.02,
    min_tau_delta_excess: float = 0.05,
) -> ReflectionSaturationScales:
    """Build τ_α, δ₀, τ_δ⁺ from benign (Δα, δ) step pairs."""
    alphas: list[float] = []
    deltas: list[float] = []
    for da, dr in pairs:
        if da >= 0 and dr >= 0:
            alphas.append(float(da))
            deltas.append(float(dr))
    if not alphas:
        return ReflectionSaturationScales(
            tau_alpha=PAPER_TAU_ALPHA,
            tau_delta=PAPER_TAU_DELTA_EXCESS,
            delta_baseline=PAPER_DELTA_BASELINE,
            stat=stat,
            n_pairs=0,
            source="paper_fallback",
        )
    delta_baseline = float(statistics.median(deltas))
    excesses = [max(0.0, d - delta_baseline) for d in deltas]
    tau_a = max(min_tau_alpha, _stat(alphas, stat))
    tau_excess = max(min_tau_delta_excess, _stat(excesses, stat))
    return ReflectionSaturationScales(
        tau_alpha=tau_a,
        tau_delta=tau_excess,
        delta_baseline=delta_baseline,
        stat=stat,
        n_pairs=len(alphas),
        mean_alpha=float(statistics.fmean(alphas)),
        mean_delta=float(statistics.fmean(deltas)),
        median_alpha=float(statistics.median(alphas)),
        median_delta=delta_baseline,
        mean_delta_excess=float(statistics.fmean(excesses)),
        source=source,
    )


def save_scales(scales: ReflectionSaturationScales, path: Path | None = None) -> Path:
    out = path or DEFAULT_CACHE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scales.as_dict(), indent=2), encoding="utf-8")
    return out


def load_scales(path: Path | None = None) -> ReflectionSaturationScales | None:
    return _load_scales_file(path or DEFAULT_CACHE_PATH)


def load_process_scales(path: Path | None = None) -> ReflectionSaturationScales | None:
    return _load_scales_file(path or DEFAULT_PROCESS_CACHE_PATH)


def _load_scales_file(p: Path) -> ReflectionSaturationScales | None:
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    baseline = float(data.get("delta_baseline", data.get("median_delta", PAPER_DELTA_BASELINE)))
    return ReflectionSaturationScales(
        tau_alpha=float(data.get("tau_alpha", PAPER_TAU_ALPHA)),
        tau_delta=float(data.get("tau_delta", PAPER_TAU_DELTA_EXCESS)),
        delta_baseline=baseline,
        stat=str(data.get("stat", "median")),  # type: ignore[arg-type]
        n_pairs=int(data.get("n_pairs", 0)),
        mean_alpha=float(data.get("mean_alpha", 0.0)),
        mean_delta=float(data.get("mean_delta", 0.0)),
        median_alpha=float(data.get("median_alpha", 0.0)),
        median_delta=float(data.get("median_delta", baseline)),
        mean_delta_excess=float(data.get("mean_delta_excess", 0.0)),
        source=str(data.get("source", "calibrated")),
    )


def resolve_saturation_scales(
    config=None,
    *,
    path: Path | None = None,
) -> ReflectionSaturationScales:
    """Resolve scales: explicit config > cache file > paper defaults."""
    mode = "auto"
    stat: StatKind = "p75"
    explicit_a: float | None = None
    explicit_d: float | None = None
    scale_path: Path | None = path

    if config is not None:
        mode = str(getattr(config, "reflection_scale_mode", "auto") or "auto").lower()
        stat = str(getattr(config, "reflection_scale_stat", "p75") or "p75")  # type: ignore[assignment]
        if stat not in ("median", "mean", "p75", "p90", "p95"):
            stat = "p75"
        raw_a = getattr(config, "reflection_tau_alpha", None)
        raw_d = getattr(config, "reflection_tau_delta", None)
        if raw_a is not None:
            explicit_a = float(raw_a)
        if raw_d is not None:
            explicit_d = float(raw_d)
        cfg_path = getattr(config, "reflection_scale_path", None)
        if cfg_path:
            scale_path = Path(str(cfg_path))

    if mode == "fixed":
        return ReflectionSaturationScales(
            tau_alpha=explicit_a if explicit_a is not None else PAPER_TAU_ALPHA,
            tau_delta=explicit_d if explicit_d is not None else PAPER_TAU_DELTA_EXCESS,
            delta_baseline=PAPER_DELTA_BASELINE,
            stat=stat,
            source="fixed",
        )

    if explicit_a is not None and explicit_d is not None:
        return ReflectionSaturationScales(
            tau_alpha=explicit_a,
            tau_delta=explicit_d,
            delta_baseline=PAPER_DELTA_BASELINE,
            stat=stat,
            source="config",
        )

    cached = load_scales(scale_path)
    if cached is not None and mode in ("auto", "calibrated"):
        return cached

    return ReflectionSaturationScales(
        tau_alpha=PAPER_TAU_ALPHA,
        tau_delta=PAPER_TAU_DELTA_EXCESS,
        delta_baseline=PAPER_DELTA_BASELINE,
        stat=stat,
        source="paper_fallback",
    )
