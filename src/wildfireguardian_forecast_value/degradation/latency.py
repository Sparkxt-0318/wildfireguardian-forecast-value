"""Temporal latency -- modelled as *availability*, not as a score penalty.

This module is the reason the package exists in the shape it does, so the
semantics are spelled out in full.

Three clocks
------------
``s``   **information time.**  The forecast is built from knowledge of the
        world up to and including ``s``.  Anything that happens after ``s`` --
        a spot ignition at ``s + 0.1`` h, say -- is *unknowable* to it.  This
        is enforced by
        :func:`~wildfireguardian_forecast_value.fields.front.known_at`.

``delta`` **latency.**  Production, transmission and ingest delay.  The
        forecast built at ``s`` is not in the decision maker's hands until
        ``a = s + delta``.

``t_d`` **decision time.**  When the protective action must be chosen.

The decision maker's information set at ``t_d`` contains a release **iff**
``a <= t_d``, i.e. ``s + delta <= t_d``.

What this is not
----------------
Latency is *not* implemented as ``J -> J + c * delta`` or as an extra term in a
skill score.  A penalty term would make a late forecast merely *worse*; in
reality a late forecast is **absent**, and absence sends the decision maker
back to whatever policy they had without it.  That distinction produces a
behaviour a penalty term cannot reproduce:

    increasing forecast accuracy while increasing latency can strictly
    *decrease* decision value, discontinuously, at the moment
    ``s + delta`` crosses ``t_d``.

That is Case 4 in ``docs/DECISION_VALUE.md`` and the reason the primary
demonstration figure has latency on one axis.

Staleness
---------
When a release *is* available, what degrades the decision is not ``delta`` but
the **age of information** ``t_d - s``, which satisfies ``t_d - s >= delta``.
A low-latency forecast issued from stale observations can be worse than a
high-latency forecast issued from fresh ones.  :attr:`ForecastRelease.age_at`
reports the age; nothing in this package conflates it with ``delta``.

Ties
----
``a <= t_d`` is inclusive: a forecast landing exactly at the decision instant
is usable.  The opposite convention is defensible; it is recorded in
``docs/ASSUMPTIONS.md`` (A-07) because it changes results exactly on the
frontier, which is the region the package is built to study.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from wildfireguardian_forecast_value.fields.front import FireState, known_at

__all__ = ["ForecastRelease", "ForecastStream", "LatencySpec", "make_release", "issue_times"]


@dataclass(frozen=True)
class ForecastRelease:
    """One forecast product, with its two timestamps."""

    state: FireState
    information_time: float
    latency: float
    label: str = "forecast"

    def __post_init__(self) -> None:
        if not np.isfinite(self.information_time):
            raise ValueError("information_time must be finite")
        if not np.isfinite(self.latency) or self.latency < 0.0:
            raise ValueError(
                f"latency must be finite and >= 0 (a negative latency is a forecast that "
                f"arrives before it was made); got {self.latency!r}"
            )
        object.__setattr__(self, "information_time", float(self.information_time))
        object.__setattr__(self, "latency", float(self.latency))

    @property
    def availability_time(self) -> float:
        """``s + delta``: the first instant this release can be acted on."""
        return self.information_time + self.latency

    def is_available_at(self, t: float) -> bool:
        """Inclusive availability test ``s + delta <= t``."""
        return self.availability_time <= float(t)

    def age_at(self, t: float) -> float:
        """Age of the information at time ``t``: ``t - s``.  May be negative if unused."""
        return float(t) - self.information_time

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "information_time": self.information_time,
            "latency": self.latency,
            "availability_time": self.availability_time,
            "state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class LatencySpec:
    """Configuration for how a forecast product is issued.

    ``information_time`` is when the forecast "sees" the world; ``latency`` is
    the delay before it can be used.  Both are hours on the scenario clock.
    """

    information_time: float
    latency: float

    def release(self, state: FireState, label: str = "forecast") -> ForecastRelease:
        return ForecastRelease(state, self.information_time, self.latency, label)

    def to_dict(self) -> dict:
        return {"information_time": self.information_time, "latency": self.latency}


class ForecastStream:
    """A time-ordered set of releases; answers "what did I have at ``t``?"."""

    def __init__(self, releases: Iterable[ForecastRelease] = ()) -> None:
        self.releases: tuple[ForecastRelease, ...] = tuple(
            sorted(releases, key=lambda r: (r.availability_time, r.information_time))
        )

    def __len__(self) -> int:
        return len(self.releases)

    def __iter__(self):
        return iter(self.releases)

    def available_at(self, t: float) -> ForecastRelease | None:
        """Most *informative* release available at ``t``, or ``None``.

        "Most informative" means largest ``information_time`` among available
        releases -- not simply the last one to arrive.  A slow high-quality
        product and a fast low-quality one can arrive out of order, and
        picking by arrival time would silently discard the fresher of the two.
        Ties in information time are broken by earlier availability.
        """
        usable = [r for r in self.releases if r.is_available_at(t)]
        if not usable:
            return None
        return max(usable, key=lambda r: (r.information_time, -r.availability_time))

    def all_available_at(self, t: float) -> tuple[ForecastRelease, ...]:
        return tuple(r for r in self.releases if r.is_available_at(t))

    def to_dict(self) -> dict:
        return {"releases": [r.to_dict() for r in self.releases]}


def make_release(
    truth: FireState,
    information_time: float,
    latency: float,
    pipeline=None,
    params=None,
    label: str = "forecast",
    enforce_conditional_on_information_time: bool = True,
) -> ForecastRelease:
    """Build a release from truth: restrict to what is knowable, then degrade.

    The order matters and is not negotiable.  Restricting *after* degrading
    would let a degradation operator move an unknowable source into the
    forecast; restricting first makes "the forecast could not have known"
    structural rather than a property of the operator chain.

    With ``enforce_conditional_on_information_time=False`` the result is a
    ``FUTURE_ORACLE`` (see
    :mod:`wildfireguardian_forecast_value.forecast_classes`), not a forecast,
    and
    :func:`...validation.invariants.check_conditional_on_information_time`
    will reject it.  The escape hatch exists so that the invariant itself can
    be tested.
    """
    base = (known_at(truth, information_time)
            if enforce_conditional_on_information_time else truth)
    state = pipeline.apply(base, params) if pipeline is not None else base
    return ForecastRelease(state, information_time, latency, label)


def issue_times(first: float, cadence: float, count: int) -> list[float]:
    """Information times for a regularly-issued product."""
    if cadence <= 0 or count < 1:
        raise ValueError("cadence must be > 0 and count >= 1")
    return [float(first + k * cadence) for k in range(int(count))]
