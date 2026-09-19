"""Uncertainty bands around an estimated break-even frontier.

Procedure
---------
1.  Resample world indices with replacement -- **one index vector per
    replicate, applied to every grid cell**.  This preserves the common-random-
    number structure of the sweep (:mod:`~.grid`); resampling each cell
    independently would break the correlation between neighbouring cells and
    produce bands that are far too narrow where the surface is flat and too
    wide where it is steep.
2.  Recompute the mean-``Delta J`` surface for the replicate.
3.  Re-extract the frontier from that surface.
4.  Take pointwise quantiles of the crossing position per column.

What the band is
----------------
A **pointwise** band over the world distribution: at each x it covers the
crossing position in the stated fraction of replicates.  It is not a
simultaneous band for the whole curve, and it says nothing about grid
resolution, model error or the choice of loss.

Columns that do not cross
-------------------------
A replicate may fail to cross zero in a column that the point estimate
crosses, or vice versa.  Those replicates are counted
(:attr:`FrontierBand.crossing_rate`) and excluded from the quantile, and the
crossing rate is reported alongside the band.  A column whose crossing rate is
0.6 does not have a frontier with a 95% interval -- it has a frontier that
exists in 60% of resamples, and reporting the interval without the rate would
be a lie about the estimate's stability.  The plotting module fades such
columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from wildfireguardian_forecast_value.frontiers.estimate import frontier_from_grid
from wildfireguardian_forecast_value.rng import make_generator

__all__ = ["FrontierBand", "bootstrap_frontier_band", "surface_band"]


@dataclass
class FrontierBand:
    """Pointwise bootstrap band for a frontier expressed as ``y`` versus ``x``."""

    x_values: np.ndarray
    estimate: np.ndarray            # point-estimate crossing per column (nan where none)
    lower: np.ndarray
    upper: np.ndarray
    crossing_rate: np.ndarray       # fraction of replicates with a crossing in the column
    multi_crossing_rate: np.ndarray  # fraction of replicates with >1 crossing
    confidence: float
    n_boot: int
    n_worlds: int
    replicate_positions: np.ndarray = field(repr=False, default_factory=lambda: np.zeros((0, 0)))

    def as_dict(self) -> dict:
        return {
            "x_values": self.x_values.tolist(),
            "estimate": self.estimate.tolist(),
            "lower": self.lower.tolist(),
            "upper": self.upper.tolist(),
            "crossing_rate": self.crossing_rate.tolist(),
            "multi_crossing_rate": self.multi_crossing_rate.tolist(),
            "confidence": self.confidence,
            "n_boot": self.n_boot,
            "n_worlds": self.n_worlds,
        }


def bootstrap_frontier_band(
    grid,
    n_boot: int = 400,
    confidence: float = 0.95,
    seed: int = 0,
    which: str = "first",
) -> FrontierBand:
    """Bootstrap band for the frontier of ``grid``.

    ``which`` selects which crossing to track in columns with several:
    ``"first"`` (lowest y), ``"last"`` (highest y).  Tracking a single
    crossing in a multi-valued column is a reporting compromise; the
    ``multi_crossing_rate`` output is what stops it from being a silent one.
    """
    if which not in ("first", "last"):
        raise ValueError("which must be 'first' or 'last'")
    rng = make_generator(seed)
    nw = grid.n_worlds
    xs = np.asarray(grid.x_axis.values, dtype=float)
    nx = xs.size

    def _pick(cols):
        pos = np.full(nx, np.nan)
        multi = np.zeros(nx, dtype=bool)
        for i, c in enumerate(cols):
            if c.n_crossings:
                pos[i] = c.crossings[0].position if which == "first" else c.crossings[-1].position
                multi[i] = c.n_crossings > 1
        return pos, multi

    est, _ = _pick(frontier_from_grid(grid))

    reps = np.full((int(n_boot), nx), np.nan)
    multi = np.zeros((int(n_boot), nx), dtype=bool)
    for b in range(int(n_boot)):
        idx = rng.integers(0, nw, size=nw)
        surface = grid.mean_from_indices(idx)
        pos, m = _pick(frontier_from_grid(grid, surface))
        reps[b], multi[b] = pos, m

    alpha = 1.0 - confidence
    lower = np.full(nx, np.nan)
    upper = np.full(nx, np.nan)
    rate = np.zeros(nx)
    for i in range(nx):
        col = reps[:, i]
        ok = np.isfinite(col)
        rate[i] = float(ok.mean())
        if ok.sum() >= 2:
            lower[i], upper[i] = np.percentile(col[ok], [100 * alpha / 2.0, 100 * (1 - alpha / 2.0)])

    return FrontierBand(
        x_values=xs, estimate=est, lower=lower, upper=upper,
        crossing_rate=rate, multi_crossing_rate=multi.mean(axis=0),
        confidence=float(confidence), n_boot=int(n_boot), n_worlds=int(nw),
        replicate_positions=reps,
    )


def surface_band(grid, n_boot: int = 400, confidence: float = 0.95, seed: int = 0):
    """Pointwise bootstrap interval for the mean-``Delta J`` surface itself.

    Complementary to the frontier band: where the surface interval straddles
    zero, the sign of the decision-value difference is not resolved by this
    many worlds, and no frontier drawn through that region should be believed.
    Returns ``(lower, upper)``, each ``(ny, nx)``.
    """
    rng = make_generator(seed)
    nw = grid.n_worlds
    reps = np.empty((int(n_boot), *grid.shape))
    for b in range(int(n_boot)):
        reps[b] = grid.mean_from_indices(rng.integers(0, nw, size=nw))
    alpha = 1.0 - confidence
    return (np.percentile(reps, 100 * alpha / 2.0, axis=0),
            np.percentile(reps, 100 * (1 - alpha / 2.0), axis=0))
