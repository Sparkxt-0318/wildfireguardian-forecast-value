"""What physically happened -- deliberately separate from what it is worth.

:class:`Outcome` lives at the package root, depending on nothing, because both
the physics layer (:mod:`~wildfireguardian_forecast_value.synthetic_decisions.routes`,
which produces outcomes) and the valuation layer
(:mod:`~wildfireguardian_forecast_value.decision_value.loss`, which prices
them) need it, and neither should depend on the other.  That independence is
not tidiness: it is what lets a study re-value a fixed set of outcomes under a
whole family of loss functions without re-running the fire model, which is how
the sensitivity analysis in ``docs/DECISION_VALUE.md`` is done.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

__all__ = ["Outcome"]


@dataclass(frozen=True)
class Outcome:
    """What happened to one receptor under one action in one world."""

    action: str
    travel_time: float
    burned_over: bool
    #: Hours of slack at the tightest point: ``min_k (t_fire(p_k) - t_receptor(p_k))``.
    #: ``<= 0`` means overrun; ``+inf`` means the fire never reaches the path.
    safety_margin: float
    receptor_id: int = 0

    def as_dict(self) -> dict:
        return asdict(self)

    def _replace_id(self, receptor_id: int) -> "Outcome":
        return replace(self, receptor_id=int(receptor_id))
