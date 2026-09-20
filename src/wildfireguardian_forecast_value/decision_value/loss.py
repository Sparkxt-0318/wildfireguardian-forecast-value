"""The downstream loss ``J(a, omega)``.

``J`` maps an action ``a`` and a world ``omega`` to a real number that is
*smaller when things go better*.  Everything in this package -- decision
value, break-even frontiers, equivalence testing -- is defined relative to
``J``, and none of it is meaningful without one.

Loss-function arbitrariness
---------------------------
There is no correct ``J``.  The exchange rate between "evacuees spent an extra
20 minutes on the road" and "an evacuee was overrun by fire" is an ethical and
political choice, not a measurement.  This package takes three positions about
that, all of them deliberate:

1.  ``J`` is an **explicit, serialisable object**.  Every result frame and
    manifest carries the loss parameters that produced it.  A decision-value
    number quoted without its loss function is not a result.
2.  The headline quantity is **relative to a stated** ``J``, never absolute.
    Statements of the form "this forecast is worth using" are always
    "...under this loss".
3.  Sensitivity to ``J`` is a **first-class output**, not a robustness
    appendix.  :func:`loss_ratio_sweep` re-runs a comparison across a range of
    ``burnover_loss / time_cost`` ratios, and the toy study reports the range
    of ratios over which the sign of ``Delta J`` is stable.  A frontier that
    moves under a factor-of-two change in the loss ratio is a frontier about
    the analyst, not about the forecast.

``docs/DECISION_VALUE.md`` ("Loss-function arbitrariness") and
``docs/FAILURE_MODES.md`` (F-07) carry the full argument.

Units
-----
``J`` is reported in **hours of equivalent delay** so that the two terms are
commensurable: travel time enters directly, and a burnover enters as
``burnover_loss`` hours.  Nothing here is money.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from wildfireguardian_forecast_value.outcomes import Outcome

__all__ = ["Outcome", "LossModel", "RouteChoiceLoss", "loss_ratio_sweep"]


class LossModel:
    """Interface: ``loss(outcome) -> float``."""

    name = "loss"

    def loss(self, outcome: Outcome) -> float:  # pragma: no cover - interface
        raise NotImplementedError

    def losses(self, outcomes) -> np.ndarray:
        return np.array([self.loss(o) for o in outcomes], dtype=float)

    def to_dict(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class RouteChoiceLoss(LossModel):
    """``J = time_cost_per_hour * travel_time + burnover_loss * 1[overrun]``.

    Parameters
    ----------
    time_cost_per_hour:
        Weight on travel time.  Defaults to 1, which fixes the unit of ``J``
        as "hours of equivalent delay".
    burnover_loss:
        Hours-of-delay equivalent of being overrun.  This single number carries
        the whole ethical content of the study.
    near_miss_penalty, near_miss_margin:
        Optional convexity: an extra ``near_miss_penalty`` (scaled linearly to
        zero at ``near_miss_margin`` hours of slack) for clearing the route with very
        little margin.  Off by default.  It exists so that studies can check
        whether the frontier's shape depends on ``J`` being a step function;
        it usually does.
    """

    time_cost_per_hour: float = 1.0
    burnover_loss: float = 50.0
    near_miss_penalty: float = 0.0
    near_miss_margin: float = 0.0
    name: str = "route_choice_loss"

    def __post_init__(self) -> None:
        if self.burnover_loss < 0 or self.time_cost_per_hour < 0 or self.near_miss_penalty < 0:
            raise ValueError("loss weights must be non-negative")
        if self.near_miss_penalty > 0 and self.near_miss_margin <= 0:
            raise ValueError("near_miss_penalty requires a positive near_miss_margin")

    @property
    def loss_ratio(self) -> float:
        """``burnover_loss / time_cost_per_hour`` -- the only ratio that matters.

        ``J`` is invariant to a common rescaling of both weights (it scales
        ``J`` and every ``Delta J`` by the same factor, leaving every sign and
        every frontier unchanged), so the model has one effective parameter,
        not two.
        """
        return float("inf") if self.time_cost_per_hour == 0 else self.burnover_loss / self.time_cost_per_hour

    def loss(self, outcome: Outcome) -> float:
        j = self.time_cost_per_hour * float(outcome.travel_time)
        if outcome.burned_over:
            return j + self.burnover_loss
        if self.near_miss_penalty > 0 and np.isfinite(outcome.safety_margin):
            slack = max(0.0, min(float(outcome.safety_margin), self.near_miss_margin))
            j += self.near_miss_penalty * (1.0 - slack / self.near_miss_margin)
        return float(j)

    def with_ratio(self, ratio: float) -> "RouteChoiceLoss":
        """Same loss with ``burnover_loss / time_cost_per_hour`` set to ``ratio``."""
        return RouteChoiceLoss(
            time_cost_per_hour=self.time_cost_per_hour,
            burnover_loss=float(ratio) * self.time_cost_per_hour,
            near_miss_penalty=self.near_miss_penalty,
            near_miss_margin=self.near_miss_margin,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["loss_ratio"] = self.loss_ratio
        return d


def loss_ratio_sweep(base: RouteChoiceLoss, ratios) -> list[RouteChoiceLoss]:
    """Family of losses spanning a range of burnover/time ratios.

    Use with the world-level machinery to answer "over what range of the
    ethical exchange rate does the sign of ``Delta J`` survive?".
    """
    return [base.with_ratio(float(r)) for r in np.asarray(ratios, dtype=float)]
