"""Sweeping decision value over a grid of forecast-quality parameters.

A **break-even frontier** is the set where ``Delta J = 0``: the forecast and
the forecast-free baseline are worth the same.  On one side the forecast
deserves to change the decision; on the other the trigger should be left
alone.  The primary figure of this repository is that frontier in the
(direction error, latency) plane.

Common random numbers
---------------------
Every grid cell is evaluated on the **same** worlds, drawn once from the same
seed.  This is not an optimisation, it is what makes the surface smooth enough
to find a zero crossing in: with independent worlds per cell, cell-to-cell
Monte-Carlo noise would swamp the signal near the frontier, which is precisely
where the differences are smallest.

The cost is that cells are *correlated*, so their uncertainties may not be
treated as independent either.  The bootstrap in :mod:`~.bands` therefore
resamples worlds **jointly across the whole grid**: one resampled world index
vector is applied to every cell, preserving the common-random-number structure
in the replicates.  Bootstrapping cells independently would give bands that
are far too narrow near the frontier and wrongly shaped away from it.

Axes
----
An axis is a named parameter and a set of values.  Three kinds:

``"degradation"``  a pipeline parameter (``eps_theta``, ``eps_r``, ...)
``"latency"``      the release delay ``delta``
``"information_time"``  the forecast's information time ``s``

Latency and information time are separate axes on purpose: they are different
clocks (:mod:`~wildfireguardian_forecast_value.degradation.latency`) and
collapsing them would hide the difference between a stale forecast and a slow
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.decision_value.value import default_policies, evaluate_world

__all__ = ["SweepAxis", "FrontierGrid", "sweep_grid"]

_KINDS = ("degradation", "latency", "information_time")


@dataclass(frozen=True)
class SweepAxis:
    """One axis of a frontier sweep."""

    name: str
    values: tuple[float, ...]
    kind: str = "degradation"
    label: str | None = None
    #: Optional display transform, e.g. radians -> degrees for a heading axis.
    display_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"axis kind must be one of {_KINDS}, got {self.kind!r}")
        v = np.asarray(self.values, dtype=float).ravel()
        if v.size < 2:
            raise ValueError(f"axis {self.name!r} needs at least two values")
        if not np.all(np.diff(v) > 0):
            raise ValueError(
                f"axis {self.name!r} values must be strictly increasing; the frontier "
                "estimator interpolates between neighbouring values and an unsorted "
                "axis would interpolate across unrelated points"
            )
        object.__setattr__(self, "values", tuple(float(x) for x in v))

    @property
    def display_values(self) -> np.ndarray:
        return np.asarray(self.values, dtype=float) * self.display_scale

    @property
    def display_label(self) -> str:
        return self.label if self.label else self.name

    def to_dict(self) -> dict:
        return {"name": self.name, "values": list(self.values), "kind": self.kind,
                "label": self.label, "display_scale": self.display_scale}


@dataclass
class FrontierGrid:
    """Mean ``Delta J`` on a 2-D parameter grid, with the per-world detail kept.

    ``delta`` has shape ``(ny, nx, n_worlds)`` and holds the paired per-world
    differences for every cell.  Keeping it (rather than only the mean) is what
    makes the joint bootstrap in :mod:`~.bands` possible at all.
    """

    x_axis: SweepAxis
    y_axis: SweepAxis
    delta: np.ndarray                      # (ny, nx, n_worlds)
    value_fraction: np.ndarray             # (ny, nx, n_worlds), may contain nan
    action_changed: np.ndarray             # (ny, nx, n_worlds) bool
    available: np.ndarray                  # (ny, nx, n_worlds) bool
    skill: dict = field(default_factory=dict)   # name -> (ny, nx) mean skill metric
    meta: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.delta.shape[0], self.delta.shape[1]

    @property
    def n_worlds(self) -> int:
        return self.delta.shape[2]

    @property
    def mean_delta(self) -> np.ndarray:
        """``(ny, nx)`` mean paired ``Delta J``.  This is the surface whose zero set is the frontier."""
        return self.delta.mean(axis=2)

    def mean_from_indices(self, idx: np.ndarray) -> np.ndarray:
        """Mean surface computed on a resampled set of world indices."""
        return self.delta[:, :, idx].mean(axis=2)

    def to_long_frame(self) -> pd.DataFrame:
        """One row per (cell, world) -- the tidy form written to parquet."""
        ny, nx, nw = self.delta.shape
        yy, xx, ww = np.meshgrid(np.arange(ny), np.arange(nx), np.arange(nw), indexing="ij")
        df = pd.DataFrame({
            "y_index": yy.ravel(), "x_index": xx.ravel(), "world_id": ww.ravel(),
            self.x_axis.name: np.asarray(self.x_axis.values)[xx.ravel()],
            self.y_axis.name: np.asarray(self.y_axis.values)[yy.ravel()],
            "delta_j": self.delta.ravel(),
            "value_fraction": self.value_fraction.ravel(),
            "action_changed": self.action_changed.ravel(),
            "forecast_available": self.available.ravel(),
        })
        df.attrs["x_axis"] = self.x_axis.to_dict()
        df.attrs["y_axis"] = self.y_axis.to_dict()
        df.attrs["unit_of_analysis"] = "world"
        return df


def _apply_axis(axis: SweepAxis, value: float, params: dict, lat: dict) -> None:
    if axis.kind == "degradation":
        params[axis.name] = float(value)
    elif axis.kind == "latency":
        lat["latency"] = float(value)
    else:
        lat["information_time"] = float(value)


def sweep_grid(
    scenario,
    x_axis: SweepAxis,
    y_axis: SweepAxis,
    n_worlds: int,
    seed: int,
    pipeline,
    base_params: dict | None = None,
    base_latency: LatencySpec | None = None,
    policies=None,
    loss=None,
    skill_keys: tuple[str, ...] = ("csi", "arrival_rmse", "heading_error_deg"),
    progress=None,
) -> FrontierGrid:
    """Evaluate ``Delta J`` at every cell of ``y_axis x x_axis`` on common worlds."""
    worlds = scenario.sample_worlds(n_worlds, seed)
    pols = policies if policies is not None else default_policies(scenario)
    base_lat = base_latency if base_latency is not None else LatencySpec(scenario.decision_time, 0.0)

    ny, nx = len(y_axis.values), len(x_axis.values)
    delta = np.zeros((ny, nx, n_worlds))
    frac = np.zeros((ny, nx, n_worlds))
    changed = np.zeros((ny, nx, n_worlds), dtype=bool)
    avail = np.zeros((ny, nx, n_worlds), dtype=bool)
    skill = {k: np.zeros((ny, nx)) for k in skill_keys}

    for iy, yv in enumerate(y_axis.values):
        for ix, xv in enumerate(x_axis.values):
            params = dict(base_params or {})
            lat = {"information_time": base_lat.information_time, "latency": base_lat.latency}
            _apply_axis(x_axis, xv, params, lat)
            _apply_axis(y_axis, yv, params, lat)
            spec = LatencySpec(**lat)
            acc = {k: [] for k in skill_keys}
            for iw, w in enumerate(worlds):
                r = evaluate_world(scenario, w, pipeline, params, spec, policies=pols,
                                   loss=loss, compute_skill=bool(skill_keys))
                delta[iy, ix, iw] = r.delta_j
                frac[iy, ix, iw] = r.value_fraction
                changed[iy, ix, iw] = r.action_changed
                avail[iy, ix, iw] = r.forecast_available
                for k in skill_keys:
                    acc[k].append(r.skill.get(k, np.nan))
            for k in skill_keys:
                vals = np.asarray(acc[k], dtype=float)
                finite = vals[np.isfinite(vals)]
                skill[k][iy, ix] = float(finite.mean()) if finite.size else np.nan
            if progress is not None:
                progress(iy * nx + ix + 1, ny * nx)

    return FrontierGrid(
        x_axis=x_axis, y_axis=y_axis, delta=delta, value_fraction=frac,
        action_changed=changed, available=avail, skill=skill,
        meta={
            "n_worlds": int(n_worlds), "seed": int(seed),
            "scenario": scenario.to_dict(),
            "pipeline": pipeline.to_dict() if pipeline is not None else None,
            "base_params": dict(base_params or {}),
            "base_latency": base_lat.to_dict(),
            "common_random_numbers": True,
        },
    )
