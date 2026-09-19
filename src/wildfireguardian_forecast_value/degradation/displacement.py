"""Spatial displacement of predicted front geometry.

Definition
----------
The predicted front is shifted rigidly by translating each selected source's
origin:

    o' = o + s

Because a wedge is scale- and translation-covariant in its own frame,
translating the origin translates the whole predicted front geometry and the
whole arrival-time field:

    t'(p) = t(p - s)

That identity is exact for this fire model, is what makes displacement
hand-checkable, and is asserted in ``tests/test_hand_checkable.py``.

Two parameterisations
---------------------
* ``mode="cartesian"`` consumes ``(disp_x, disp_y)`` in km.
* ``mode="polar"`` consumes ``(disp_magnitude, disp_heading)``.  With
  ``relative_to_heading=True`` the displacement heading is measured **from the
  source's own heading**, so "the forecast puts the fire 2 km further along
  its own axis" is ``disp_magnitude=2, disp_heading=0``.

Constraints and consequences:

* ``disp_magnitude`` must be ``>= 0``.  A negative magnitude with a heading is
  an ambiguous way to write a rotation by ``pi`` and is rejected rather than
  silently reinterpreted.
* **Displacement is not a time shift.**  Shifting the origin toward an asset
  makes the fire arrive earlier there *and* later at assets on the far side,
  and it moves the wedge's angular boundary relative to every asset at once.
  Treating a spatial displacement as an equivalent lead-time error is a
  category error; ``docs/FORECAST_ERROR_MODEL.md`` records why.
* **Order dependence.**  With ``relative_to_heading=True`` this operator reads
  ``heading``, so it does **not** commute with
  :class:`~.direction.DirectionError`.  :class:`DegradationPipeline` applies
  direction error first by convention (see :func:`~.combined.standard_pipeline`).
"""

from __future__ import annotations

import numpy as np

from wildfireguardian_forecast_value.degradation.base import DegradationOperator, SourceSelector
from wildfireguardian_forecast_value.fields.front import FireSource
from wildfireguardian_forecast_value.fields.geometry import unit_vector

__all__ = ["SpatialDisplacement"]


class SpatialDisplacement(DegradationOperator):
    """Rigid translation of selected sources."""

    name = "spatial_displacement"

    def __init__(
        self,
        selector: SourceSelector | None = None,
        mode: str = "polar",
        relative_to_heading: bool = False,
        param_prefix: str = "disp",
    ) -> None:
        super().__init__(selector if selector is not None else SourceSelector.primary())
        if mode not in ("polar", "cartesian"):
            raise ValueError(f"mode must be 'polar' or 'cartesian', got {mode!r}")
        self.mode = mode
        self.relative_to_heading = bool(relative_to_heading)
        self.param_prefix = str(param_prefix)
        if mode == "polar":
            self.param_names = (f"{param_prefix}_magnitude", f"{param_prefix}_heading")
        else:
            self.param_names = (f"{param_prefix}_x", f"{param_prefix}_y")
        if relative_to_heading and mode != "polar":
            raise ValueError("relative_to_heading is only meaningful in polar mode")

    def identity_params(self) -> dict[str, float]:
        return {k: 0.0 for k in self.param_names}

    def _offset(self, source: FireSource, values) -> np.ndarray:
        if self.mode == "cartesian":
            dx = float(values[f"{self.param_prefix}_x"])
            dy = float(values[f"{self.param_prefix}_y"])
            off = np.array([dx, dy], dtype=float)
        else:
            mag = float(values[f"{self.param_prefix}_magnitude"])
            head = float(values[f"{self.param_prefix}_heading"])
            if mag < 0.0:
                raise ValueError(
                    f"{self.param_prefix}_magnitude must be >= 0 "
                    f"(write a reversed direction in the heading, not a negative length); got {mag!r}"
                )
            if self.relative_to_heading:
                head = head + source.heading
            off = mag * unit_vector(head)
        if not np.all(np.isfinite(off)):
            raise ValueError(f"displacement must be finite, got {off!r}")
        return off

    def _apply_to_source(self, source: FireSource, values) -> FireSource:
        off = self._offset(source, values)
        return source.with_(origin=(source.origin[0] + float(off[0]), source.origin[1] + float(off[1])))

    def _config(self) -> dict:
        return {
            "mode": self.mode,
            "relative_to_heading": self.relative_to_heading,
            "param_prefix": self.param_prefix,
        }
