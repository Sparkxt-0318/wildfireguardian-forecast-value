"""Categorical and probabilistic forecast-skill metrics.

Contingency table for "burned by time ``T``":

                    truth burned   truth unburned
    fc burned            a (hit)        b (false alarm)
    fc unburned          c (miss)       d (correct negative)

POD = a/(a+c), FAR = b/(a+b), CSI = a/(a+b+c), bias ratio = (a+b)/(a+c).

Domain dependence
-----------------
``d`` -- and therefore every metric that uses it -- depends on how much
unburnt land the analyst put in the grid.  CSI avoids ``d`` and is preferred
here for that reason, but CSI still moves when the grid is refined, because
refining the grid changes the area weighting of the boundary cells.  Grids are
explicit objects (:class:`~wildfireguardian_forecast_value.fields.grids.RasterGrid`)
and every metric returned by this module carries the cell count it was
computed on.  ``docs/FAILURE_MODES.md`` (F-04).

Probabilistic forecasts
-----------------------
This package's forecasts are deterministic fire states, so the Brier score is
computed against a forecast probability the caller supplies (e.g. from an
ensemble of degraded states).  :func:`ensemble_burn_probability` builds that
probability from a set of states, which is how the toy studies produce one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

__all__ = [
    "ContingencyTable",
    "contingency_table",
    "categorical_scores",
    "brier_score",
    "brier_skill_score",
    "ensemble_burn_probability",
]


@dataclass(frozen=True)
class ContingencyTable:
    hits: int
    false_alarms: int
    misses: int
    correct_negatives: int

    @property
    def n(self) -> int:
        return self.hits + self.false_alarms + self.misses + self.correct_negatives

    def as_dict(self) -> dict:
        return asdict(self)


def contingency_table(truth_burned, forecast_burned) -> ContingencyTable:
    t = np.asarray(truth_burned, dtype=bool).ravel()
    f = np.asarray(forecast_burned, dtype=bool).ravel()
    if t.shape != f.shape:
        raise ValueError(f"shape mismatch: truth {t.shape} vs forecast {f.shape}")
    return ContingencyTable(
        hits=int(np.sum(t & f)),
        false_alarms=int(np.sum(~t & f)),
        misses=int(np.sum(t & ~f)),
        correct_negatives=int(np.sum(~t & ~f)),
    )


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den > 0 else float("nan")


def categorical_scores(truth_burned, forecast_burned) -> dict[str, float]:
    """POD, FAR, CSI, frequency bias, plus the raw table and its size.

    Undefined ratios return ``nan`` rather than 0: a FAR of ``nan`` ("the
    forecast never said burned, so the false-alarm *rate* has no denominator")
    is different information from a FAR of 0 ("it said burned and was always
    right"), and collapsing the two flatters degenerate forecasts.
    """
    tbl = contingency_table(truth_burned, forecast_burned)
    a, b, c, d = tbl.hits, tbl.false_alarms, tbl.misses, tbl.correct_negatives
    return {
        "hits": a, "false_alarms": b, "misses": c, "correct_negatives": d,
        "n_cells": tbl.n,
        "pod": _safe_div(a, a + c),
        "far": _safe_div(b, a + b),
        "csi": _safe_div(a, a + b + c),
        "frequency_bias": _safe_div(a + b, a + c),
        "accuracy": _safe_div(a + d, tbl.n),
    }


def brier_score(forecast_prob, truth_binary) -> float:
    """Mean squared error of a probability forecast of a binary event."""
    p = np.asarray(forecast_prob, dtype=float).ravel()
    y = np.asarray(truth_binary, dtype=float).ravel()
    if p.shape != y.shape:
        raise ValueError(f"shape mismatch: prob {p.shape} vs truth {y.shape}")
    if np.any(p < 0) or np.any(p > 1):
        raise ValueError("forecast probabilities must lie in [0, 1]")
    return float(np.mean((p - y) ** 2))


def brier_skill_score(forecast_prob, truth_binary, reference_prob=None) -> float:
    """Brier skill against a reference; default reference is the sample base rate.

    Returns ``nan`` when the reference score is zero (a degenerate outcome
    field), rather than ``+-inf``.
    """
    y = np.asarray(truth_binary, dtype=float).ravel()
    ref = np.full(y.shape, float(y.mean())) if reference_prob is None else np.asarray(reference_prob, dtype=float).ravel()
    bs = brier_score(forecast_prob, y)
    bs_ref = brier_score(ref, y)
    return float("nan") if bs_ref == 0 else 1.0 - bs / bs_ref


def ensemble_burn_probability(states, points, time: float) -> np.ndarray:
    """Fraction of ``states`` in which each point has burned by ``time``.

    The ensemble is treated as equally weighted, which is an assumption
    (A-09 in ``docs/ASSUMPTIONS.md``), not a fact about the ensemble.
    """
    states = list(states)
    if not states:
        raise ValueError("need at least one state to form an ensemble probability")
    masks = np.stack([s.burned_mask(points, time) for s in states], axis=0)
    return masks.mean(axis=0)
