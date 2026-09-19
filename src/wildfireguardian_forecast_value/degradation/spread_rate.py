"""Spread-rate error.

Definition
----------
Multiplicative, applied per source:

    r' = r * (1 + eps_r)

Exact behaviour and constraints -- these are load-bearing, not incidental:

* **Domain.** ``eps_r > -1`` strictly.  ``eps_r = -1`` gives a zero spread
  rate, which is not a fire that spreads slowly but a fire that never moves;
  the arrival-time field would be ``+inf`` everywhere except the origin and
  ``FireSource`` rejects it.  Values ``<= -1`` are handled by ``on_domain_error``.
* **Asymmetry.** The map is multiplicative, so ``eps_r = +0.5`` and
  ``eps_r = -0.5`` are *not* mirror images: they give ``1.5r`` and ``0.5r``,
  whose arrival times are ``d/(1.5r)`` and ``d/(0.5r)`` -- a 33% early error
  and a 100% late error.  Any sweep that treats ``+eps`` and ``-eps`` as
  equally sized errors is measuring the wrong thing.  Use
  :func:`log_ratio_error` if you want a symmetric error coordinate.
* **Monotonicity.** Arrival time is monotone decreasing in ``eps_r`` at every
  point *inside the wedge*, but the burned footprint at a fixed time is
  monotone **increasing** in ``eps_r`` only in the wedge; outside it, nothing
  changes at all.  Decision value is monotone in neither.  See
  ``docs/FORECAST_ERROR_MODEL.md``, section "Monotonicity".
* **Clipping.** With ``clip_to`` set, the resulting *rate* (not ``eps_r``) is
  clipped into the given interval.  Clipping makes the operator non-injective
  and flattens the frontier; it is off by default and recorded in manifests
  when on.
"""

from __future__ import annotations

import numpy as np

from wildfireguardian_forecast_value.degradation.base import DegradationOperator, SourceSelector
from wildfireguardian_forecast_value.fields.front import FireSource

__all__ = ["SpreadRateError", "log_ratio_error"]

_MIN_EPS = -1.0 + 1e-9


class SpreadRateError(DegradationOperator):
    """``r -> r (1 + eps_r)``.

    Parameters
    ----------
    selector:
        Which sources to degrade.  Default: every source, including spots --
        a rate bias in a forecast is usually a property of the fuel/wind
        model, not of one ignition.
    clip_to:
        Optional ``(lo, hi)`` bound on the resulting rate in km/h.
    on_domain_error:
        ``"raise"`` (default) or ``"clip"``.  With ``"clip"``, ``eps_r`` is
        clipped up to just above ``-1`` instead of raising.
    """

    name = "spread_rate_error"
    param_names = ("eps_r",)

    def __init__(
        self,
        selector: SourceSelector | None = None,
        clip_to: tuple[float, float] | None = None,
        on_domain_error: str = "raise",
    ) -> None:
        super().__init__(selector)
        if clip_to is not None:
            lo, hi = float(clip_to[0]), float(clip_to[1])
            if not (0.0 < lo < hi):
                raise ValueError(f"clip_to must satisfy 0 < lo < hi, got {clip_to!r}")
            clip_to = (lo, hi)
        self.clip_to = clip_to
        if on_domain_error not in ("raise", "clip"):
            raise ValueError("on_domain_error must be 'raise' or 'clip'")
        self.on_domain_error = on_domain_error

    def identity_params(self) -> dict[str, float]:
        return {"eps_r": 0.0}

    def _apply_to_source(self, source: FireSource, values) -> FireSource:
        eps = float(values["eps_r"])
        if not np.isfinite(eps) or eps <= -1.0:
            if self.on_domain_error == "raise":
                raise ValueError(
                    f"eps_r must be finite and > -1 (a rate of zero is not a slow fire); got {eps!r}"
                )
            eps = max(eps, _MIN_EPS) if np.isfinite(eps) else _MIN_EPS
        rate = source.spread_rate * (1.0 + eps)
        if self.clip_to is not None:
            rate = float(np.clip(rate, self.clip_to[0], self.clip_to[1]))
        return source.with_(spread_rate=rate)

    def _config(self) -> dict:
        return {"clip_to": list(self.clip_to) if self.clip_to else None,
                "on_domain_error": self.on_domain_error}


def log_ratio_error(forecast_rate, truth_rate):
    """Symmetric spread-rate error coordinate ``log(r_hat / r)``.

    Under this coordinate a factor-of-two overprediction and a factor-of-two
    underprediction have equal magnitude, which ``eps_r`` does not.  Reported
    alongside ``eps_r`` by the skill metrics so that sweeps can be read either
    way.
    """
    f = np.asarray(forecast_rate, dtype=float)
    t = np.asarray(truth_rate, dtype=float)
    if np.any(f <= 0) or np.any(t <= 0):
        raise ValueError("log-ratio error requires strictly positive rates")
    return np.log(f / t)
