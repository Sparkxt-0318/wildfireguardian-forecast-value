"""Fire front representation and the arrival-time field.

The fire model is deliberately the simplest thing that can still make a
protective decision flip.  A fire state is a *set of sources*; each source
spreads as a circular **wedge** -- constant rate ``r``, centred on ``heading``,
with angular half-width ``half_angle`` -- from its origin, starting at its
ignition time.  The arrival time at a point is the minimum over sources.

For one source with origin ``o``, ignition time ``t0``, rate ``r``, heading
``h`` and half-angle ``phi``, the arrival time at point ``p`` is

    d      = |p - o|
    alpha  = wrap(heading_of(p - o) - h)
    t(p)   = t0 + d / r        if |alpha| <= phi
           = +inf              otherwise            ("never burns")

Why a wedge and not an ellipse: the wedge is exactly hand-solvable (a distance
and one angle comparison), which is what the independent-validation tests in
``tests/test_hand_checkable.py`` rely on.  Its hard angular edge is a feature
rather than a defect for this package -- it is the mechanism by which a *small*
heading error can flip a decision while barely moving an RMSE, which is the
whole point of Case 2 in ``docs/DECISION_VALUE.md``.  It is also the model's
most important limitation, and is recorded as such in
``docs/ASSUMPTIONS.md`` and ``docs/FAILURE_MODES.md``.

``+inf`` arrival times are load-bearing.  They mean "this point does not burn
within this fire state", not "this point burns very late", and every consumer
(skill metrics, route overrun, plotting) has to handle them explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

import numpy as np

from wildfireguardian_forecast_value.fields.geometry import heading_of, wrap_to_pi

__all__ = ["FireSource", "FireState", "NEVER"]

#: Arrival time assigned to points a fire state never reaches.
NEVER = np.inf

# Points sitting exactly on the wedge edge are treated as inside.  Without a
# tolerance, "exactly on the edge" is decided by floating-point noise, which
# would make hand-checked fixtures fragile.
_ANGLE_TOL = 1e-12


def _dir(angle: float) -> np.ndarray:
    return np.array([np.cos(angle), np.sin(angle)], dtype=float)


def _point_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from points ``p`` (..., 2) to the segment ``[a, b]``."""
    ab = b - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return np.linalg.norm(p - a, axis=-1)
    t = np.clip(((p - a) @ ab) / denom, 0.0, 1.0)
    proj = a + t[..., None] * ab
    return np.linalg.norm(p - proj, axis=-1)


@dataclass(frozen=True)
class FireSource:
    """One spreading wedge.

    Parameters
    ----------
    origin:
        ``(x, y)`` in km.
    ignition_time:
        Hours on the scenario clock at which this source starts spreading.
    spread_rate:
        km/h, strictly positive.
    heading:
        Radians CCW from east (see :mod:`~.geometry`).
    half_angle:
        Angular half-width in radians, in ``(0, pi]``.  ``pi`` is an isotropic
        (circular) source, which is what spot ignitions use by default.
    label:
        Stable identifier.  Degradation operators address sources by label,
        so labels must be unique within a :class:`FireState`.
    kind:
        ``"primary"`` or ``"spot"``.  Spotting operators act on ``"spot"``
        sources only; this keeps "drop the spot fire" from silently deleting
        the main fire.
    """

    origin: tuple[float, float]
    ignition_time: float
    spread_rate: float
    heading: float
    half_angle: float = float(np.pi)
    label: str = "main"
    kind: str = "primary"

    def __post_init__(self) -> None:
        o = np.asarray(self.origin, dtype=float)
        if o.shape != (2,):
            raise ValueError(f"origin must be a 2-vector, got shape {o.shape}")
        if not np.all(np.isfinite(o)):
            raise ValueError(f"origin must be finite, got {self.origin!r}")
        object.__setattr__(self, "origin", (float(o[0]), float(o[1])))
        if not np.isfinite(self.ignition_time):
            raise ValueError("ignition_time must be finite")
        object.__setattr__(self, "ignition_time", float(self.ignition_time))
        if not (self.spread_rate > 0.0) or not np.isfinite(self.spread_rate):
            raise ValueError(f"spread_rate must be finite and > 0, got {self.spread_rate!r}")
        object.__setattr__(self, "spread_rate", float(self.spread_rate))
        object.__setattr__(self, "heading", float(wrap_to_pi(self.heading)))
        if not (0.0 < self.half_angle <= np.pi + 1e-12):
            raise ValueError(f"half_angle must be in (0, pi], got {self.half_angle!r}")
        object.__setattr__(self, "half_angle", float(min(self.half_angle, np.pi)))
        if self.kind not in ("primary", "spot"):
            raise ValueError(f"kind must be 'primary' or 'spot', got {self.kind!r}")

    @property
    def is_isotropic(self) -> bool:
        return self.half_angle >= np.pi - 1e-12

    def arrival_time(self, points) -> np.ndarray:
        """Arrival time (hours) at ``points``, shape ``(..., 2)`` -> ``(...)``.

        Points outside the wedge get :data:`NEVER`.
        """
        p = np.atleast_2d(np.asarray(points, dtype=float))
        if p.shape[-1] != 2:
            raise ValueError(f"points must have trailing dimension 2, got {p.shape}")
        u = p - np.asarray(self.origin, dtype=float)
        dist = np.linalg.norm(u, axis=-1)

        t = self.ignition_time + dist / self.spread_rate
        if not self.is_isotropic:
            with np.errstate(invalid="ignore"):
                alpha = wrap_to_pi(heading_of(u) - self.heading)
            inside = np.abs(alpha) <= self.half_angle + _ANGLE_TOL
            # The origin itself is always inside: its displacement has no
            # defined heading, and the fire is by definition there at t0.
            inside = inside | (dist == 0.0)
            t = np.where(inside, t, NEVER)
        return t


    def burned_radius(self, time: float) -> float:
        """Radius of the burned wedge at ``time``; ``0`` before ignition."""
        return max(0.0, (float(time) - self.ignition_time) * self.spread_rate)

    def distance_to_burned(self, points, time: float) -> np.ndarray:
        """Euclidean distance from ``points`` to the burned region at ``time``.

        Exact for the wedge model.  Returns ``0`` for points already burned and
        :data:`NEVER` before the source has ignited (there is no burned set to
        be near).

        This is what a *forecast-free* trigger policy is allowed to look at:
        where the fire is **now**, with no extrapolation.  Keeping it on the
        fire state -- rather than letting a policy extrapolate an arrival time
        and call it an observation -- is what stops the "baseline" from
        quietly becoming a forecast.

        Geometry: for a point angularly inside the wedge the nearest burned
        point lies along the same ray, at distance ``max(0, d - R)``.  For a
        point outside, the nearest burned point lies on one of the two straight
        wedge edges (the arc is angularly further away than its own endpoints),
        so the distance is the smaller of the two point-to-segment distances.
        """
        p = np.atleast_2d(np.asarray(points, dtype=float))
        t = float(time)
        if t < self.ignition_time:
            return np.full(p.shape[:-1], NEVER)
        R = self.burned_radius(t)
        o = np.asarray(self.origin, dtype=float)
        u = p - o
        dist = np.linalg.norm(u, axis=-1)
        radial = np.maximum(0.0, dist - R)
        if self.is_isotropic:
            return radial
        with np.errstate(invalid="ignore"):
            alpha = wrap_to_pi(heading_of(u) - self.heading)
        inside = (np.abs(alpha) <= self.half_angle + _ANGLE_TOL) | (dist == 0.0)
        edge = np.minimum(
            _point_segment_distance(p, o, o + R * _dir(self.heading + self.half_angle)),
            _point_segment_distance(p, o, o + R * _dir(self.heading - self.half_angle)),
        )
        return np.where(inside, radial, edge)

    def with_(self, **changes) -> "FireSource":
        """Return a copy with fields replaced (validation re-runs)."""
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return {
            "origin": list(self.origin),
            "ignition_time": self.ignition_time,
            "spread_rate": self.spread_rate,
            "heading": self.heading,
            "half_angle": self.half_angle,
            "label": self.label,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FireSource":
        d = dict(d)
        d["origin"] = tuple(float(v) for v in d["origin"])
        return cls(**d)


@dataclass(frozen=True)
class FireState:
    """A set of sources, interpreted as one fire.

    A :class:`FireState` is used for three different things and the difference
    matters:

    * the **truth** state of a synthetic world,
    * a **forecast** of that state (possibly degraded),
    * the **observation** available to a baseline policy.

    Nothing in the type distinguishes them; the surrounding code does.
    """

    sources: tuple[FireSource, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        srcs = tuple(self.sources)
        labels = [s.label for s in srcs]
        if len(set(labels)) != len(labels):
            raise ValueError(f"source labels must be unique, got {labels}")
        object.__setattr__(self, "sources", srcs)

    def __len__(self) -> int:
        return len(self.sources)

    def __iter__(self):
        return iter(self.sources)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(s.label for s in self.sources)

    def by_label(self, label: str) -> FireSource:
        for s in self.sources:
            if s.label == label:
                return s
        raise KeyError(f"no source labelled {label!r}; have {self.labels}")

    def of_kind(self, kind: str) -> tuple[FireSource, ...]:
        return tuple(s for s in self.sources if s.kind == kind)

    def arrival_time(self, points) -> np.ndarray:
        """Earliest arrival time over all sources.  Empty state -> all :data:`NEVER`."""
        p = np.atleast_2d(np.asarray(points, dtype=float))
        if not self.sources:
            return np.full(p.shape[:-1], NEVER)
        per_source = np.stack([s.arrival_time(p) for s in self.sources], axis=0)
        return per_source.min(axis=0)

    def burned_mask(self, points, time: float) -> np.ndarray:
        """Boolean "has burned by ``time``" (arrival time <= ``time``)."""
        return self.arrival_time(points) <= float(time)

    def distance_to_burned(self, points, time: float) -> np.ndarray:
        """Distance to the nearest burned point over all sources at ``time``."""
        p = np.atleast_2d(np.asarray(points, dtype=float))
        if not self.sources:
            return np.full(p.shape[:-1], NEVER)
        return np.stack([s.distance_to_burned(p, time) for s in self.sources], axis=0).min(axis=0)

    def map_sources(self, fn) -> "FireState":
        """Return a new state with ``fn`` applied to every source."""
        return FireState(tuple(fn(s) for s in self.sources))

    def replace_source(self, label: str, new_source: FireSource | None) -> "FireState":
        """Replace (or, with ``None``, drop) the source called ``label``."""
        if label not in self.labels:
            raise KeyError(f"no source labelled {label!r}; have {self.labels}")
        out = [s for s in self.sources if s.label != label]
        if new_source is not None:
            out.append(new_source)
        # Preserve original ordering for the sources that remain.
        order = {lab: i for i, lab in enumerate(self.labels)}
        out.sort(key=lambda s: order.get(s.label, len(order)))
        return FireState(tuple(out))

    def add_source(self, source: FireSource) -> "FireState":
        return FireState(self.sources + (source,))

    def to_dict(self) -> dict:
        return {"sources": [s.to_dict() for s in self.sources]}

    @classmethod
    def from_dict(cls, d: dict) -> "FireState":
        return cls(tuple(FireSource.from_dict(s) for s in d.get("sources", ())))

    @classmethod
    def single(cls, **kwargs) -> "FireState":
        """Convenience constructor for a one-source state."""
        return cls((FireSource(**kwargs),))


def known_at(state: FireState, information_time: float) -> FireState:
    """Restrict ``state`` to what an observer at ``information_time`` could know.

    Sources whose ignition time is strictly **after** ``information_time`` have
    not happened yet and therefore cannot be in any honest forecast built from
    observations at that time.  This is the *information* half of latency
    semantics; the *availability* half lives in
    :mod:`~wildfireguardian_forecast_value.degradation.latency`.

    A forecast that retains such a source is clairvoyant, and
    :func:`~wildfireguardian_forecast_value.validation.invariants.check_no_clairvoyance`
    exists to catch that.
    """
    return FireState(tuple(s for s in state.sources if s.ignition_time <= float(information_time)))
