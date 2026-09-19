"""Rasterisation helpers.

Categorical skill metrics (POD/FAR/CSI) need a *population of cells* to count
hits and misses over.  That population is an analyst choice, not a property of
the fire, and it changes the metric values -- a larger domain of mostly-unburnt
cells inflates CSI's denominator differently than a tight one.  The grid is
therefore an explicit, serialisable object rather than an implicit default.
See ``docs/FAILURE_MODES.md`` (F-04, "domain-dependent categorical skill").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["RasterGrid"]


@dataclass(frozen=True)
class RasterGrid:
    """A regular grid of cell centres over ``[x_min, x_max] x [y_min, y_max]``."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    nx: int
    ny: int

    def __post_init__(self) -> None:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("grid bounds must satisfy min < max")
        if self.nx < 1 or self.ny < 1:
            raise ValueError("grid must have at least one cell per axis")

    @property
    def dx(self) -> float:
        return (self.x_max - self.x_min) / self.nx

    @property
    def dy(self) -> float:
        return (self.y_max - self.y_min) / self.ny

    @property
    def cell_area(self) -> float:
        """km^2 per cell."""
        return self.dx * self.dy

    @property
    def n_cells(self) -> int:
        return self.nx * self.ny

    def centres(self) -> np.ndarray:
        """Cell-centre coordinates, shape ``(ny, nx, 2)`` (row-major, y outer)."""
        xs = self.x_min + (np.arange(self.nx) + 0.5) * self.dx
        ys = self.y_min + (np.arange(self.ny) + 0.5) * self.dy
        gx, gy = np.meshgrid(xs, ys, indexing="xy")
        return np.stack([gx, gy], axis=-1)

    def flat_centres(self) -> np.ndarray:
        """Cell centres flattened to ``(n_cells, 2)``."""
        return self.centres().reshape(-1, 2)

    def arrival_field(self, state) -> np.ndarray:
        """Arrival time of ``state`` at every cell centre, shape ``(ny, nx)``."""
        return state.arrival_time(self.flat_centres()).reshape(self.ny, self.nx)

    def burned_field(self, state, time: float) -> np.ndarray:
        """Boolean burned-by-``time`` field, shape ``(ny, nx)``."""
        return self.arrival_field(state) <= float(time)

    def to_dict(self) -> dict:
        return {
            "x_min": self.x_min, "x_max": self.x_max,
            "y_min": self.y_min, "y_max": self.y_max,
            "nx": self.nx, "ny": self.ny,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RasterGrid":
        return cls(**d)
