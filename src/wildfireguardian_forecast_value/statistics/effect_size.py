"""Effect sizes for paired world-level differences.

Reporting a ``p`` value for ``Delta J`` answers a question nobody asked
("could the mean be exactly zero?") while leaving the one that matters ("how
much does it move, and how often?") untouched.  With enough synthetic worlds
any non-zero effect is significant, so significance here is a statement about
the compute budget, not about the forecast.  Three effect sizes are reported
instead.

``cohens_dz``
    Standardised mean paired difference, ``mean(d) / sd(d)``.  Convenient and
    conventional; also the most misleading of the three here, because ``d`` is
    close to a two-point distribution and its ``sd`` is not a natural scale.
    Hedges' small-sample correction is applied and reported separately.

``probability_of_superiority``
    ``P(d > 0) + 0.5 P(d = 0)``: the fraction of worlds in which the forecast
    made the decision better, ties split.  Assumption-free, directly
    interpretable, and the right headline for a quantity whose distribution is
    mostly a spike at zero.  Ties are common and are **not** dropped -- a world
    where the forecast changed nothing is evidence about the forecast, not a
    missing observation.

``mean_ratio_to_vpi``
    Mean realised fraction of the value of perfect information, over worlds
    where perfect information was worth something.  This is the scale-free
    number a decision maker actually wants: "this forecast captures 62% of
    what a perfect one would be worth".

All three come with cluster-bootstrap intervals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from wildfireguardian_forecast_value.statistics.bootstrap import bootstrap_ci

__all__ = [
    "EffectSizes",
    "cohens_dz",
    "hedges_correction",
    "probability_of_superiority",
    "effect_sizes",
    "value_fraction_summary",
]


def cohens_dz(delta) -> float:
    """``mean(d) / sd(d)`` for paired differences.  ``nan`` when ``sd`` is zero."""
    d = np.asarray(delta, dtype=float).ravel()
    if d.size < 2:
        return float("nan")
    sd = float(d.std(ddof=1))
    return float(d.mean() / sd) if sd > 0 else float("nan")


def hedges_correction(n: int) -> float:
    """Small-sample bias correction factor ``J`` for a standardised mean difference."""
    if n < 3:
        return float("nan")
    df = n - 1
    return float(1.0 - 3.0 / (4.0 * df - 1.0))


def probability_of_superiority(delta) -> float:
    """``P(d > 0) + 0.5 P(d = 0)`` -- ties split, never dropped."""
    d = np.asarray(delta, dtype=float).ravel()
    if d.size == 0:
        return float("nan")
    return float((np.sum(d > 0) + 0.5 * np.sum(d == 0)) / d.size)


@dataclass(frozen=True)
class EffectSizes:
    n_worlds: int
    mean_delta: float
    mean_delta_ci: tuple[float, float]
    cohens_dz: float
    hedges_g: float
    dz_ci: tuple[float, float]
    probability_of_superiority: float
    pos_ci: tuple[float, float]
    fraction_worlds_action_changed: float

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("mean_delta_ci", "dz_ci", "pos_ci"):
            lo, hi = d.pop(k)
            d[f"{k}_low"], d[f"{k}_high"] = lo, hi
        return d


def effect_sizes(
    delta,
    action_changed=None,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> EffectSizes:
    """All three effect sizes with cluster-bootstrap intervals."""
    d = np.asarray(delta, dtype=float).ravel()
    n = d.size
    mean_ci = bootstrap_ci(d, np.mean, n_boot=n_boot, confidence=confidence, seed=seed)
    dz_ci = bootstrap_ci(d, cohens_dz, n_boot=n_boot, confidence=confidence, seed=seed + 1)
    pos_ci = bootstrap_ci(d, probability_of_superiority, n_boot=n_boot,
                          confidence=confidence, seed=seed + 2)
    g = cohens_dz(d) * hedges_correction(n) if n >= 3 else float("nan")
    changed = (float(np.mean(np.asarray(action_changed, dtype=bool)))
               if action_changed is not None else float("nan"))
    return EffectSizes(
        n_worlds=int(n),
        mean_delta=float(d.mean()) if n else float("nan"),
        mean_delta_ci=(mean_ci.ci_low, mean_ci.ci_high),
        cohens_dz=cohens_dz(d),
        hedges_g=float(g),
        dz_ci=(dz_ci.ci_low, dz_ci.ci_high),
        probability_of_superiority=probability_of_superiority(d),
        pos_ci=(pos_ci.ci_low, pos_ci.ci_high),
        fraction_worlds_action_changed=changed,
    )


def value_fraction_summary(
    value_fraction,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> dict:
    """Mean realised fraction of VPI, over worlds where VPI was positive.

    Worlds with ``nan`` (perfect information worth nothing) are excluded from
    the mean and **counted separately**.  A study in which most worlds are
    excluded is a study whose scenario rarely poses a decision, and the count
    is what tells you so.
    """
    f = np.asarray(value_fraction, dtype=float).ravel()
    usable = f[np.isfinite(f)]
    out = {
        "n_worlds": int(f.size),
        "n_worlds_with_positive_vpi": int(usable.size),
        "n_worlds_undecidable": int(f.size - usable.size),
    }
    if usable.size < 2:
        out.update(mean_value_fraction=float(usable.mean()) if usable.size else float("nan"),
                   ci_low=float("nan"), ci_high=float("nan"))
        return out
    ci = bootstrap_ci(usable, np.mean, n_boot=n_boot, confidence=confidence, seed=seed)
    out.update(mean_value_fraction=float(usable.mean()), ci_low=ci.ci_low, ci_high=ci.ci_high)
    return out
