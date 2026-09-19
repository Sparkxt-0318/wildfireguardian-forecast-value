"""Direction (heading) error.

Definition
----------
Additive on the circle, applied per source:

    theta' = wrap(theta + eps_theta)

Exact behaviour and constraints:

* **Circularity.** ``eps_theta`` is added then wrapped to ``(-pi, pi]``.  The
  parameter itself is *not* wrapped before use, so ``eps_theta = 3*pi`` is a
  legal way to write ``pi``; but a *sweep* over ``eps_theta`` beyond ``+-pi``
  revisits headings it has already visited, which makes any frontier estimated
  on such a grid periodic and any "monotone in eps_theta" claim false by
  construction.  Sweeps should stay in ``[-pi, pi]``.
* **Isotropic sources are invariant.**  A source with ``half_angle = pi``
  burns in all directions, so rotating its heading changes nothing.  Applying
  direction error to a spot fire (isotropic by default) is therefore a no-op --
  intentionally.  ``rotate_isotropic=False`` skips them explicitly so this is
  visible in manifests rather than being a silent identity.
* **Non-monotonicity.**  This is the operator most likely to produce a
  non-monotone decision-value response.  A wedge boundary sweeping across an
  asset produces a *step* in loss; sweeping further can move the boundary back
  off a second asset.  Nothing in this package assumes ``|eps_theta|`` orders
  decision value.  See ``docs/DECISION_VALUE.md``, "Why the frontier is not
  assumed monotone".
* **Half-angle is untouched.**  Heading error and front-width error are
  different physical failures; widening a forecast wedge is *hedging*, not
  error, and is modelled separately (``WidenFront``).
"""

from __future__ import annotations

import numpy as np

from wildfireguardian_forecast_value.degradation.base import DegradationOperator, SourceSelector
from wildfireguardian_forecast_value.fields.front import FireSource
from wildfireguardian_forecast_value.fields.geometry import wrap_to_pi

__all__ = ["DirectionError", "WidenFront"]


class DirectionError(DegradationOperator):
    """``theta -> wrap(theta + eps_theta)``."""

    name = "direction_error"
    param_names = ("eps_theta",)

    def __init__(
        self,
        selector: SourceSelector | None = None,
        rotate_isotropic: bool = False,
    ) -> None:
        super().__init__(selector if selector is not None else SourceSelector.primary())
        self.rotate_isotropic = bool(rotate_isotropic)

    def identity_params(self) -> dict[str, float]:
        return {"eps_theta": 0.0}

    def _apply_to_source(self, source: FireSource, values) -> FireSource:
        if source.is_isotropic and not self.rotate_isotropic:
            return source
        eps = float(values["eps_theta"])
        if not np.isfinite(eps):
            raise ValueError(f"eps_theta must be finite, got {eps!r}")
        return source.with_(heading=float(wrap_to_pi(source.heading + eps)))

    def _config(self) -> dict:
        return {"rotate_isotropic": self.rotate_isotropic}


class WidenFront(DegradationOperator):
    """``phi -> clip(phi + eps_phi, (0, pi])`` -- front-width error / hedging.

    Included because it is the natural confound for direction error: a forecast
    that widens its wedge covers the truth heading more often and so scores
    better on categorical skill, while telling the decision maker less.  It is
    *not* part of the default pipeline.
    """

    name = "widen_front"
    param_names = ("eps_phi",)

    def __init__(self, selector: SourceSelector | None = None) -> None:
        super().__init__(selector if selector is not None else SourceSelector.primary())

    def identity_params(self) -> dict[str, float]:
        return {"eps_phi": 0.0}

    def _apply_to_source(self, source: FireSource, values) -> FireSource:
        eps = float(values["eps_phi"])
        if not np.isfinite(eps):
            raise ValueError(f"eps_phi must be finite, got {eps!r}")
        phi = float(np.clip(source.half_angle + eps, 1e-6, np.pi))
        return source.with_(half_angle=phi)
