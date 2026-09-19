"""Equivalence and non-inferiority for decision value.

"The forecast did not significantly improve the decision" is not evidence that
it made no difference; it is compatible with a large improvement that the
study was too small to resolve.  The question a protective agency actually
asks has the opposite shape:

    *Is this forecast's decision value close enough to the incumbent's that
    switching is not worth it?*  (equivalence)

    *Is it at least not materially worse?*  (non-inferiority)

Both require a **margin** ``m``: how much decision value, in hours of
equivalent delay, counts as "material".  The margin is a policy input, not a
statistical one, and this module refuses to default it.  It must be stated,
and it is recorded in every result.

Tests
-----
:func:`tost` -- two one-sided tests.  Equivalence at margin ``m`` is declared
when the ``(1 - 2*alpha)`` confidence interval for the mean paired difference
lies entirely inside ``(-m, +m)``.  The interval-inclusion form is used
rather than two ``p`` values because it is the same object the rest of the
package reports and cannot be misread as a claim about a point null.

:func:`non_inferiority` -- one-sided.  Declared when the lower confidence
bound exceeds ``-m``.

Both come in a Student-t flavour and a cluster-bootstrap flavour.  The
bootstrap is the default: ``Delta J`` is typically a spike at zero plus a
heavy positive tail, and the t interval's symmetry is wrong in exactly the
region where the decision is close.

Interpretation trap
-------------------
Failing to declare equivalence is **not** evidence of a difference, and
declaring equivalence at a margin of 5 hours says nothing about a margin of
0.5.  Every result carries its margin so the claim cannot travel without it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats

from wildfireguardian_forecast_value.statistics.bootstrap import bootstrap_ci

__all__ = ["EquivalenceResult", "tost", "non_inferiority"]


@dataclass(frozen=True)
class EquivalenceResult:
    kind: str
    margin: float
    alpha: float
    n_worlds: int
    mean: float
    ci_low: float
    ci_high: float
    ci_level: float
    decision: str
    method: str
    p_lower: float = float("nan")
    p_upper: float = float("nan")

    @property
    def is_equivalent(self) -> bool:
        return self.decision == "equivalent"

    @property
    def is_non_inferior(self) -> bool:
        return self.decision == "non_inferior"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["is_equivalent"] = self.is_equivalent
        d["is_non_inferior"] = self.is_non_inferior
        return d


def _interval(d: np.ndarray, level: float, method: str, n_boot: int, seed: int):
    if method == "t":
        n = d.size
        mean = float(d.mean())
        se = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        if se == 0:
            return mean, mean, mean
        crit = float(stats.t.ppf(0.5 + level / 2.0, df=n - 1))
        return mean, mean - crit * se, mean + crit * se
    if method == "bootstrap":
        r = bootstrap_ci(d, np.mean, n_boot=n_boot, confidence=level, seed=seed)
        return r.estimate, r.ci_low, r.ci_high
    raise ValueError(f"method must be 't' or 'bootstrap', got {method!r}")


def tost(
    delta,
    margin: float,
    alpha: float = 0.05,
    method: str = "bootstrap",
    n_boot: int = 2000,
    seed: int = 0,
) -> EquivalenceResult:
    """Two one-sided tests for equivalence of decision value within ``+-margin``.

    ``margin`` is in the units of ``J`` (hours of equivalent delay) and must be
    strictly positive: an equivalence claim at margin zero is a claim of exact
    equality, which no finite sample supports.
    """
    d = np.asarray(delta, dtype=float).ravel()
    if d.size < 2:
        raise ValueError("equivalence testing needs at least two worlds")
    if not (margin > 0):
        raise ValueError("margin must be > 0; equivalence at margin 0 is not testable")
    level = 1.0 - 2.0 * alpha
    mean, lo, hi = _interval(d, level, method, n_boot, seed)
    decision = "equivalent" if (lo > -margin and hi < margin) else "not_shown"
    p_lo = p_hi = float("nan")
    if method == "t" and d.size > 1:
        se = float(d.std(ddof=1) / np.sqrt(d.size))
        if se > 0:
            df = d.size - 1
            p_lo = float(stats.t.sf((mean + margin) / se, df))      # H0: mu <= -margin
            p_hi = float(stats.t.cdf((mean - margin) / se, df))     # H0: mu >= +margin
    return EquivalenceResult(
        kind="tost", margin=float(margin), alpha=float(alpha), n_worlds=int(d.size),
        mean=float(mean), ci_low=float(lo), ci_high=float(hi), ci_level=float(level),
        decision=decision, method=method, p_lower=p_lo, p_upper=p_hi,
    )


def non_inferiority(
    delta,
    margin: float,
    alpha: float = 0.05,
    method: str = "bootstrap",
    n_boot: int = 2000,
    seed: int = 0,
) -> EquivalenceResult:
    """One-sided: is the mean paired difference above ``-margin``?

    Use for "the cheaper/faster product is not materially worse than the
    incumbent".  ``delta`` should be oriented so that positive means the
    product under test is better.
    """
    d = np.asarray(delta, dtype=float).ravel()
    if d.size < 2:
        raise ValueError("non-inferiority testing needs at least two worlds")
    if not (margin > 0):
        raise ValueError("margin must be > 0")
    level = 1.0 - 2.0 * alpha  # one-sided alpha from a two-sided interval
    mean, lo, hi = _interval(d, level, method, n_boot, seed)
    decision = "non_inferior" if lo > -margin else "not_shown"
    p = float("nan")
    if method == "t":
        se = float(d.std(ddof=1) / np.sqrt(d.size))
        if se > 0:
            p = float(stats.t.sf((mean + margin) / se, df=d.size - 1))
    return EquivalenceResult(
        kind="non_inferiority", margin=float(margin), alpha=float(alpha),
        n_worlds=int(d.size), mean=float(mean), ci_low=float(lo), ci_high=float(hi),
        ci_level=float(level), decision=decision, method=method, p_lower=p,
    )
