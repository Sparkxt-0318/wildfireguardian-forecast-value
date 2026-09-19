"""Continuous forecast-skill metrics.

These are the *traditional* metrics.  They are computed here so the package
can show, quantitatively, that they move without decision value moving and
vice versa.  None of them is used to choose an action anywhere in this
package; that separation is structural.

Censoring
---------
Arrival times can be ``+inf`` ("never burns within this fire state").  An
``inf`` is not a large number and must not enter a mean.  Every arrival-time
metric therefore reports:

``n_both``      points burned in truth and forecast -- the only points the
                error statistic is computed on;
``n_miss``      burned in truth, not in forecast (forecast says never);
``n_false``     burned in forecast, not in truth;
``n_neither``   burned in neither.

A forecast can improve its arrival-time RMSE simply by predicting "never" at
the points it would have got wrong, because those points leave the ``n_both``
set.  Reporting RMSE without the companion counts is therefore not merely
incomplete, it is gameable; ``docs/FAILURE_MODES.md`` (F-05) records this and
:func:`arrival_time_metrics` refuses to return a bare scalar.

An optional ``horizon`` censors both fields at a finite time first, which is
the honest way to compare over a fixed forecast window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from wildfireguardian_forecast_value.fields.geometry import wrap_to_pi

__all__ = [
    "ArrivalTimeMetrics",
    "arrival_time_metrics",
    "angular_error",
    "circular_mae",
    "rate_metrics",
]


@dataclass(frozen=True)
class ArrivalTimeMetrics:
    """Arrival-time error summary with its censoring bookkeeping."""

    mae: float
    rmse: float
    bias: float
    median_absolute_error: float
    n_both: int
    n_miss: int
    n_false: int
    n_neither: int
    n_points: int
    horizon: float | None

    @property
    def coverage(self) -> float:
        """Fraction of points on which the error statistics were computable."""
        return self.n_both / self.n_points if self.n_points else float("nan")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["coverage"] = self.coverage
        return d


def _censor(t, horizon):
    t = np.asarray(t, dtype=float)
    if horizon is None:
        return t
    return np.where(t <= float(horizon), t, np.inf)


def arrival_time_metrics(truth_times, forecast_times, horizon: float | None = None) -> ArrivalTimeMetrics:
    """Arrival-time error on the points burned by both fields.

    ``bias`` is ``mean(forecast - truth)``: positive means the forecast is
    *late* (predicts arrival after it happens), which is the dangerous sign.
    """
    a = _censor(truth_times, horizon).ravel()
    b = _censor(forecast_times, horizon).ravel()
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: truth {a.shape} vs forecast {b.shape}")
    n = a.size
    ta, tb = np.isfinite(a), np.isfinite(b)
    both = ta & tb
    if both.any():
        d = b[both] - a[both]
        mae = float(np.mean(np.abs(d)))
        rmse = float(np.sqrt(np.mean(d**2)))
        bias = float(np.mean(d))
        med = float(np.median(np.abs(d)))
    else:
        mae = rmse = bias = med = float("nan")
    return ArrivalTimeMetrics(
        mae=mae, rmse=rmse, bias=bias, median_absolute_error=med,
        n_both=int(both.sum()),
        n_miss=int((ta & ~tb).sum()),
        n_false=int((~ta & tb).sum()),
        n_neither=int((~ta & ~tb).sum()),
        n_points=int(n),
        horizon=None if horizon is None else float(horizon),
    )


def angular_error(forecast_heading, truth_heading):
    """Signed heading error wrapped to ``(-pi, pi]``.

    Wrapping is not cosmetic: the unwrapped difference between headings of
    ``+179`` and ``-179`` degrees is 358 degrees, and an RMSE built on that
    number reports a catastrophic error where the truth is a 2-degree one.
    """
    return wrap_to_pi(np.asarray(forecast_heading, dtype=float) - np.asarray(truth_heading, dtype=float))


def circular_mae(forecast_heading, truth_heading) -> float:
    """Mean absolute wrapped heading error, radians."""
    return float(np.mean(np.abs(angular_error(forecast_heading, truth_heading))))


def rate_metrics(forecast_rate, truth_rate) -> dict[str, float]:
    """Spread-rate error in three coordinates.

    ``mean_relative_error`` is ``mean(r_hat/r - 1)`` -- the ``eps_r`` of the
    degradation operator -- and ``mean_log_ratio`` is ``mean(log(r_hat/r))``,
    which is symmetric under inversion.  Both are reported because a sweep
    that is linear in one is not linear in the other, and the shape of a
    frontier depends on which axis it was drawn against
    (``docs/FORECAST_ERROR_MODEL.md``, "Choice of error coordinate").
    """
    f = np.asarray(forecast_rate, dtype=float)
    t = np.asarray(truth_rate, dtype=float)
    if np.any(t <= 0) or np.any(f <= 0):
        raise ValueError("rate metrics require strictly positive rates")
    rel = f / t - 1.0
    return {
        "mae": float(np.mean(np.abs(f - t))),
        "rmse": float(np.sqrt(np.mean((f - t) ** 2))),
        "bias": float(np.mean(f - t)),
        "mean_relative_error": float(np.mean(rel)),
        "mean_absolute_relative_error": float(np.mean(np.abs(rel))),
        "mean_log_ratio": float(np.mean(np.log(f / t))),
        "rmse_log_ratio": float(np.sqrt(np.mean(np.log(f / t) ** 2))),
    }
