"""World-level (cluster) bootstrap.

Resampling unit
---------------
Worlds, with replacement, whole.  When a world is drawn its entire receptor
block comes with it.  Resampling receptors -- or worse, resampling
receptor-level rows across worlds -- destroys exactly the dependence structure
the bootstrap is supposed to preserve and reproduces the error that
:mod:`~.paired` exists to prevent.  :func:`cluster_bootstrap` therefore takes
values **indexed by world** and never sees a receptor.

Intervals
---------
Percentile and BCa are both provided.  BCa corrects for bias and skew and is
the default, because ``Delta J`` here is strongly skewed (most worlds give
exactly zero, a few give tens of hours) and the percentile interval is
noticeably off-centre in that regime.  BCa's acceleration is estimated by
jackknife over worlds.

Degenerate replicates
---------------------
When every world has the same ``Delta J`` (common in a frontier corner where
the action never changes) every replicate is identical, the interval collapses
to a point, and BCa's ``z0`` is undefined.  That is reported as a
zero-width interval with ``degenerate=True`` rather than as ``nan``: the
estimate really is exact under this world distribution, and calling it
"undefined" would be less informative than saying so.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np
from scipy import stats

from wildfireguardian_forecast_value.rng import make_generator

__all__ = ["BootstrapResult", "cluster_bootstrap", "bootstrap_ci", "paired_bootstrap_difference"]


@dataclass(frozen=True)
class BootstrapResult:
    estimate: float
    ci_low: float
    ci_high: float
    confidence: float
    n_boot: int
    n_worlds: int
    method: str
    se: float
    degenerate: bool
    #: Fraction of replicates at or below zero -- a bootstrap "p-value"-ish
    #: quantity, reported for transparency, not for thresholding.
    prop_le_zero: float

    def as_dict(self) -> dict:
        return asdict(self)


def cluster_bootstrap(
    world_values,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 2000,
    seed: int = 0,
) -> np.ndarray:
    """Bootstrap replicates of ``statistic`` over worlds resampled with replacement."""
    v = np.asarray(world_values, dtype=float).ravel()
    n = v.size
    if n < 2:
        raise ValueError("cluster bootstrap needs at least two worlds")
    rng = make_generator(seed)
    idx = rng.integers(0, n, size=(int(n_boot), n))
    return np.array([float(statistic(v[row])) for row in idx], dtype=float)


def _jackknife(v: np.ndarray, statistic) -> np.ndarray:
    n = v.size
    return np.array([float(statistic(np.delete(v, i))) for i in range(n)], dtype=float)


def bootstrap_ci(
    world_values,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
    method: str = "bca",
) -> BootstrapResult:
    """Cluster-bootstrap confidence interval for a world-level statistic."""
    v = np.asarray(world_values, dtype=float).ravel()
    if method not in ("percentile", "bca"):
        raise ValueError(f"method must be 'percentile' or 'bca', got {method!r}")
    est = float(statistic(v))
    reps = cluster_bootstrap(v, statistic, n_boot=n_boot, seed=seed)
    alpha = 1.0 - confidence
    degenerate = bool(np.ptp(reps) == 0.0)

    if degenerate:
        lo = hi = est
    elif method == "percentile":
        lo, hi = np.percentile(reps, [100 * alpha / 2.0, 100 * (1.0 - alpha / 2.0)])
    else:
        prop_less = float(np.mean(reps < est))
        prop_less = min(max(prop_less, 1.0 / (2 * len(reps))), 1.0 - 1.0 / (2 * len(reps)))
        z0 = float(stats.norm.ppf(prop_less))
        jk = _jackknife(v, statistic)
        jk_mean = jk.mean()
        num = float(np.sum((jk_mean - jk) ** 3))
        den = float(6.0 * (np.sum((jk_mean - jk) ** 2) ** 1.5))
        a = num / den if den != 0 else 0.0
        z_lo, z_hi = stats.norm.ppf(alpha / 2.0), stats.norm.ppf(1.0 - alpha / 2.0)

        def _adj(z):
            denom = 1.0 - a * (z0 + z)
            if denom == 0:
                return float("nan")
            return float(stats.norm.cdf(z0 + (z0 + z) / denom))

        p_lo, p_hi = _adj(z_lo), _adj(z_hi)
        if not (np.isfinite(p_lo) and np.isfinite(p_hi)):
            lo, hi = np.percentile(reps, [100 * alpha / 2.0, 100 * (1.0 - alpha / 2.0)])
            method = "percentile (bca undefined)"
        else:
            lo, hi = np.percentile(reps, [100 * p_lo, 100 * p_hi])

    return BootstrapResult(
        estimate=est, ci_low=float(lo), ci_high=float(hi), confidence=float(confidence),
        n_boot=int(n_boot), n_worlds=int(v.size), method=method,
        se=float(reps.std(ddof=1)) if not degenerate else 0.0,
        degenerate=degenerate, prop_le_zero=float(np.mean(reps <= 0.0)),
    )


def paired_bootstrap_difference(
    values_a,
    values_b,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
    method: str = "bca",
) -> BootstrapResult:
    """Bootstrap the mean of ``a - b`` over **paired** worlds.

    The same resampled world index is used for both arms, which is what
    "paired" means here; bootstrapping the two arms independently would
    reintroduce the between-world variance that pairing removes.
    """
    a = np.asarray(values_a, dtype=float).ravel()
    b = np.asarray(values_b, dtype=float).ravel()
    if a.shape != b.shape:
        raise ValueError(f"paired arms must have equal length, got {a.shape} and {b.shape}")
    return bootstrap_ci(a - b, np.mean, n_boot=n_boot, confidence=confidence, seed=seed, method=method)
