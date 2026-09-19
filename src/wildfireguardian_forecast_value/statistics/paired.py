"""Paired, world-level comparison.

The unit of analysis
--------------------
**A world is one observation.  A resident is not.**

A study of 500 synthetic fires with 40 residents each has ``n = 500``, not
``n = 20 000``.  Residents inside a world share the fire, share the route
choice, and therefore share their fate almost entirely: their outcomes are not
20 000 draws from anything.  Treating them as independent shrinks every
standard error by roughly ``sqrt(design effect)`` -- in this package's default
scenario that factor is large -- and manufactures significance out of nothing.

This module makes that error hard to commit and easy to quantify:

* every inference function takes **world-level** values and says so in its
  signature;
* :func:`aggregate_to_worlds` is the only supported way in;
* :func:`clustering_diagnostics` reports the ICC, the design effect and the
  ratio between the naive receptor-level standard error and the correct
  world-level one, so a study can state the size of the error it avoided.

Pairing
-------
``Delta J`` is a *paired* difference: the same world under two information
sets.  All inference is on the vector of ``Delta J``, never on ``J_baseline``
and ``J_forecast`` as two samples.  Unpaired comparison of these two would be
valid but hopelessly inefficient -- between-world variance dwarfs the effect.

What the interval means
-----------------------
A confidence interval here is over the **world distribution the scenario
defines**, and nothing else.  It does not cover uncertainty in the fire model,
the loss function, the policy class, or the choice of scenario, all of which
are larger (``docs/STATISTICAL_PROTOCOL.md``, "What the intervals do not
cover").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats

__all__ = [
    "PairedSummary",
    "paired_summary",
    "aggregate_to_worlds",
    "clustering_diagnostics",
    "ClusteringDiagnostics",
]


@dataclass(frozen=True)
class PairedSummary:
    """Point estimate and Student-t interval for a mean paired difference."""

    n_worlds: int
    mean: float
    sd: float
    se: float
    ci_low: float
    ci_high: float
    confidence: float
    median: float
    n_positive: int
    n_negative: int
    n_zero: int
    t_stat: float
    p_value: float

    @property
    def win_rate(self) -> float:
        """Fraction of worlds in which the forecast strictly helped."""
        return self.n_positive / self.n_worlds if self.n_worlds else float("nan")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["win_rate"] = self.win_rate
        return d


def _as_world_vector(delta) -> np.ndarray:
    d = np.asarray(delta, dtype=float).ravel()
    if d.size == 0:
        raise ValueError("no worlds to summarise")
    if not np.all(np.isfinite(d)):
        raise ValueError(
            "world-level differences must be finite; an infinite Delta J means a loss "
            "model returned +-inf, which no interval can summarise"
        )
    return d


def paired_summary(delta, confidence: float = 0.95) -> PairedSummary:
    """Summarise world-level paired differences ``Delta J``.

    The Student-t interval is reported because it is the conventional default
    and cheap; it assumes approximate normality of the *mean*, which is
    strained here because ``Delta J`` is close to a two-point distribution
    (the action either flipped or it did not).  The bootstrap interval in
    :mod:`~.bootstrap` does not need that assumption and is the one the CLI
    reports by default; the two are shown side by side so their disagreement,
    where it exists, is visible rather than hidden.
    """
    d = _as_world_vector(delta)
    n = d.size
    mean = float(d.mean())
    sd = float(d.std(ddof=1)) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else 0.0
    if n > 1 and se > 0:
        crit = float(stats.t.ppf(0.5 + confidence / 2.0, df=n - 1))
        t_stat = mean / se
        p = float(2.0 * stats.t.sf(abs(t_stat), df=n - 1))
        half = crit * se
    elif n > 1:
        # Every world gave the same difference. The interval is the point, not
        # nan: under this world distribution the estimate really is exact, and
        # "undefined" would be less informative than saying so. The t statistic
        # remains undefined, which is correct -- there is no scale to divide by.
        t_stat = p = float("nan")
        half = 0.0
    else:
        t_stat = p = float("nan")
        half = float("nan")
    return PairedSummary(
        n_worlds=int(n), mean=mean, sd=sd, se=float(se),
        ci_low=float(mean - half), ci_high=float(mean + half),
        confidence=float(confidence), median=float(np.median(d)),
        n_positive=int(np.sum(d > 0)), n_negative=int(np.sum(d < 0)),
        n_zero=int(np.sum(d == 0)), t_stat=float(t_stat), p_value=float(p),
    )


def aggregate_to_worlds(values, world_ids, how: str = "mean") -> tuple[np.ndarray, np.ndarray]:
    """Collapse receptor-level values to one value per world.

    Returns ``(world_ids_sorted, world_values)``.  This is the only sanctioned
    route from receptor-level data into the inference functions: it makes the
    collapse a visible step rather than something that either happened or did
    not.
    """
    v = np.asarray(values, dtype=float).ravel()
    w = np.asarray(world_ids).ravel()
    if v.shape != w.shape:
        raise ValueError(f"values {v.shape} and world_ids {w.shape} must match")
    uniq = np.unique(w)
    fn = {"mean": np.mean, "sum": np.sum, "median": np.median, "max": np.max}.get(how)
    if fn is None:
        raise ValueError(f"unknown aggregation {how!r}; expected mean/sum/median/max")
    return uniq, np.array([fn(v[w == u]) for u in uniq], dtype=float)


@dataclass(frozen=True)
class ClusteringDiagnostics:
    """How much a naive receptor-level analysis would have overstated precision."""

    n_worlds: int
    n_receptors_total: int
    mean_cluster_size: float
    icc: float
    design_effect: float
    naive_se: float
    correct_se: float
    se_understatement_factor: float
    effective_sample_size: float

    def as_dict(self) -> dict:
        return asdict(self)


def clustering_diagnostics(receptor_values, world_ids) -> ClusteringDiagnostics:
    """ICC, design effect, and the standard-error ratio, from receptor-level data.

    ``ICC`` is the one-way random-effects intraclass correlation,

        ICC = (MSB - MSW) / (MSB + (m - 1) MSW),

    with ``m`` the (average) cluster size.  ``design effect = 1 + (m-1) ICC``
    is the factor by which the variance of the naive mean is understated, and
    ``effective sample size = N / design effect`` is how many independent
    observations the data actually contain.

    A negative ICC estimate (possible when between-world variance is smaller
    than within-world) is reported as estimated, **not** clipped to zero:
    clipping would hide a scenario in which the world structure is not doing
    what the analyst thinks it is.  ``design_effect`` is floored at 1 for the
    ratio, since a design cannot supply more independent information than
    ``N``.
    """
    v = np.asarray(receptor_values, dtype=float).ravel()
    w = np.asarray(world_ids).ravel()
    if v.shape != w.shape:
        raise ValueError(f"values {v.shape} and world_ids {w.shape} must match")
    uniq = np.unique(w)
    k, N = uniq.size, v.size
    if k < 2:
        raise ValueError("clustering diagnostics need at least two worlds")
    groups = [v[w == u] for u in uniq]
    sizes = np.array([g.size for g in groups], dtype=float)
    m = float(sizes.mean())
    grand = float(v.mean())
    means = np.array([g.mean() for g in groups], dtype=float)

    msb = float(np.sum(sizes * (means - grand) ** 2) / (k - 1))
    within_ss = float(sum(float(np.sum((g - g.mean()) ** 2)) for g in groups))
    msw = within_ss / (N - k) if N > k else 0.0

    denom = msb + (m - 1.0) * msw
    icc = float((msb - msw) / denom) if denom > 0 else float("nan")
    deff = 1.0 + (m - 1.0) * icc if np.isfinite(icc) else float("nan")

    naive_se = float(v.std(ddof=1) / np.sqrt(N)) if N > 1 else float("nan")
    correct_se = float(means.std(ddof=1) / np.sqrt(k)) if k > 1 else float("nan")
    ratio = float(correct_se / naive_se) if naive_se and naive_se > 0 else float("nan")
    deff_floor = max(1.0, deff) if np.isfinite(deff) else float("nan")
    ess = float(N / deff_floor) if np.isfinite(deff_floor) else float("nan")

    return ClusteringDiagnostics(
        n_worlds=int(k), n_receptors_total=int(N), mean_cluster_size=m,
        icc=icc, design_effect=float(deff), naive_se=naive_se,
        correct_se=correct_se, se_understatement_factor=ratio,
        effective_sample_size=ess,
    )
