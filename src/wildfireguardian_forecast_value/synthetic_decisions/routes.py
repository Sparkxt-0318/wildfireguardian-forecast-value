"""Evacuation routes and the traversal/overrun calculation.

A :class:`Route` is a polyline travelled at constant speed.  A receptor who
departs at time ``t_0`` is at arc length ``l`` at time ``t_0 + l / v``.  The
route is **overrun** if the fire reaches any point of the path at or before
the receptor passes it:

    margin(route, state, t_0) = min_k [ t_fire(p_k) - (t_0 + l_k / v) ]
    overrun                   <=>  margin <= 0

The margin is the headline quantity rather than the boolean, because it is
continuous where the boolean is a step, which makes hand-checking, debugging
and near-miss analysis possible.  The boolean is what enters ``J``.

Discretisation
--------------
The minimum is taken over *sampled* points at spacing ``sample_spacing`` km.
This is an approximation with a known direction of error: sampling can only
*miss* an exposure between samples, so the computed margin is an upper bound
on the true margin and overrun is under-detected.  The error is bounded by
roughly ``spacing * (1/v + 1/r)`` hours for a fire of rate ``r`` crossing the
path.  ``sample_spacing`` is an explicit parameter, defaults to 0.05 km, and
is recorded in manifests (``docs/ASSUMPTIONS.md``, A-05).

Ties
----
``margin <= 0`` counts as overrun: arriving exactly as the fire does is not a
clear passage.  Like the latency tie convention this matters only on a measure-zero
set, which is exactly the set the frontier lives on (``docs/ASSUMPTIONS.md``, A-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from wildfireguardian_forecast_value.outcomes import Outcome

__all__ = ["Route", "RouteSet", "traverse", "traverse_all"]


@lru_cache(maxsize=512)
def _segment_lengths(waypoints: tuple) -> np.ndarray:
    w = np.asarray(waypoints, dtype=float)
    out = np.linalg.norm(np.diff(w, axis=0), axis=1)
    out.flags.writeable = False
    return out


@lru_cache(maxsize=512)
def _route_samples(waypoints: tuple, spacing: float) -> tuple[np.ndarray, np.ndarray]:
    w = np.asarray(waypoints, dtype=float)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(w, axis=0), axis=1))])
    total = float(cum[-1])
    n = max(2, int(np.ceil(total / spacing)) + 1)
    s = np.linspace(0.0, total, n)
    pts = np.empty((n, 2), dtype=float)
    for d in (0, 1):
        pts[:, d] = np.interp(s, cum, w[:, d])
    pts.flags.writeable = False
    s.flags.writeable = False
    return pts, s


@dataclass(frozen=True)
class Route:
    """A polyline evacuation route traversed at constant speed."""

    name: str
    waypoints: tuple[tuple[float, float], ...]
    speed: float
    sample_spacing: float = 0.05

    def __post_init__(self) -> None:
        w = np.asarray(self.waypoints, dtype=float)
        if w.ndim != 2 or w.shape[1] != 2 or w.shape[0] < 2:
            raise ValueError(f"route {self.name!r} needs >= 2 waypoints of shape (n, 2)")
        if not np.all(np.isfinite(w)):
            raise ValueError(f"route {self.name!r} has non-finite waypoints")
        if self.speed <= 0:
            raise ValueError(f"route {self.name!r} needs speed > 0")
        if self.sample_spacing <= 0:
            raise ValueError(f"route {self.name!r} needs sample_spacing > 0")
        object.__setattr__(self, "waypoints", tuple((float(a), float(b)) for a, b in w))

    @property
    def _array(self) -> np.ndarray:
        return np.asarray(self.waypoints, dtype=float)

    @property
    def segment_lengths(self) -> np.ndarray:
        return _segment_lengths(self.waypoints)

    @property
    def length(self) -> float:
        """Total path length in km."""
        return float(self.segment_lengths.sum())

    @property
    def travel_time(self) -> float:
        """Hours end to end."""
        return self.length / self.speed

    @property
    def samples(self) -> tuple[np.ndarray, np.ndarray]:
        """``(points (m, 2), arc_length (m,))`` along the path, endpoints included.

        Memoised on the route's defining values.  Routes are frozen and
        hashable, and a sweep re-derives the same route tens of thousands of
        times; recomputing the sample array each time dominated the runtime of
        a frontier sweep before this cache existed.
        """
        return _route_samples(self.waypoints, self.sample_spacing)

    def passage_times(self, departure_time: float) -> np.ndarray:
        """Time at which a receptor departing at ``departure_time`` reaches each sample."""
        _, s = self.samples
        return float(departure_time) + s / self.speed

    def margins(self, state, departure_times) -> np.ndarray:
        """Safety margin for each of several departure times, vectorised.

        The fire's arrival-time field along the path does not depend on when
        anyone leaves, so it is evaluated **once** and reused across receptors.
        This is not only an optimisation: computing it per receptor invites a
        subtle bug in which a policy passes a different state per receptor and
        nobody notices.
        """
        pts, s = self.samples
        fire = state.arrival_time(pts)
        t0 = np.atleast_1d(np.asarray(departure_times, dtype=float))
        passage = t0[:, None] + s[None, :] / self.speed
        with np.errstate(invalid="ignore"):
            gap = fire[None, :] - passage
        return np.min(gap, axis=1)

    def margin(self, state, departure_time: float) -> float:
        """Smallest gap between fire arrival and receptor passage, in hours."""
        return float(self.margins(state, [departure_time])[0])

    def is_overrun(self, state, departure_time: float) -> bool:
        return bool(self.margin(state, departure_time) <= 0.0)

    def distance_to_burned(self, state, time: float) -> float:
        """Closest approach of the *currently burned* area to this route."""
        pts, _ = self.samples
        return float(np.min(state.distance_to_burned(pts, time)))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "waypoints": [list(w) for w in self.waypoints],
            "speed": self.speed,
            "sample_spacing": self.sample_spacing,
            "length_km": self.length,
            "travel_time_h": self.travel_time,
        }

    @classmethod
    def from_dict(cls, d) -> "Route":
        return cls(
            name=d["name"],
            waypoints=tuple(tuple(float(v) for v in w) for w in d["waypoints"]),
            speed=float(d["speed"]),
            sample_spacing=float(d.get("sample_spacing", 0.05)),
        )


def traverse(route: Route, state, departure_time: float, receptor_id: int = 0) -> Outcome:
    """Evaluate one receptor taking one route through one fire state."""
    return traverse_all(route, state, [departure_time])[int(receptor_id) if False else 0]._replace_id(receptor_id)


def traverse_all(route: Route, state, departure_times) -> list[Outcome]:
    """Evaluate a whole community taking one route through one fire state."""
    margins = route.margins(state, departure_times)
    tt = route.travel_time
    return [
        Outcome(action=route.name, travel_time=tt, burned_over=bool(m <= 0.0),
                safety_margin=float(m), receptor_id=i)
        for i, m in enumerate(margins)
    ]


@dataclass(frozen=True)
class RouteSet:
    """The action set: the routes a decision maker may choose between."""

    routes: tuple[Route, ...]

    def __post_init__(self) -> None:
        names = [r.name for r in self.routes]
        if len(set(names)) != len(names):
            raise ValueError(f"route names must be unique, got {names}")
        if len(names) < 2:
            raise ValueError("a decision problem needs at least two actions")

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(r.name for r in self.routes)

    def __iter__(self):
        return iter(self.routes)

    def __len__(self) -> int:
        return len(self.routes)

    def __getitem__(self, name: str) -> Route:
        for r in self.routes:
            if r.name == name:
                return r
        raise KeyError(f"no route named {name!r}; have {self.actions}")

    def to_dict(self) -> dict:
        return {"routes": [r.to_dict() for r in self.routes]}

    @classmethod
    def from_dict(cls, d) -> "RouteSet":
        return cls(tuple(Route.from_dict(r) for r in d["routes"]))
