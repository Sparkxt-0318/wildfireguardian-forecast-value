"""Extracting the ``Delta J = 0`` frontier without assuming it is a function.

The frontier is **not assumed monotone**, and it is not assumed to be a graph
``y = f(x)``.  Both assumptions are tempting -- they make the estimator a
bisection and the plot a line -- and both are wrong here for concrete reasons:

*   A heading error sweeps a wedge boundary *past* an asset.  Decision value
    can fall as the boundary approaches, recover once it has passed, and fall
    again at a second asset.  Along such a column ``Delta J`` may cross zero
    two or three times.
*   Latency acts through a *step*: the forecast is available or it is not.
    Crossing ``s + delta = t_d`` collapses ``Delta J`` to exactly zero
    discontinuously.  A bisection assuming a single sign change will happily
    converge to a point on the wrong side of such a step.

So: :func:`zero_crossings` returns **every** crossing in a column, by scanning
neighbouring cells for sign changes and interpolating linearly.  Columns with
no crossing are reported as such (with which side they sit on), not silently
dropped.  :func:`monotonicity_report` measures how far a surface is from
monotone instead of assuming an answer.

Interpolation
-------------
Crossings are located by linear interpolation between adjacent grid values.
Where the surface is genuinely discontinuous -- the latency step -- linear
interpolation puts the crossing somewhere inside the cell, and the true answer
is "somewhere in this cell".  :attr:`Crossing.bracket` carries the cell bounds
so a plot can show the bracket rather than implying a precision the grid does
not have.  Refining the grid narrows the bracket; it does not make the step
smooth.

Sign convention
---------------
``Delta J = J_baseline - J_forecast``.  Positive means the forecast is better.
A crossing with ``rising=True`` is a boundary below which the trigger wins.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

__all__ = [
    "Crossing",
    "ColumnFrontier",
    "zero_crossings",
    "frontier_from_grid",
    "monotonicity_report",
    "classify_regions",
]

_TOL = 1e-12


@dataclass(frozen=True)
class Crossing:
    """One zero crossing along a 1-D slice."""

    position: float
    #: ``(lower, upper)`` grid values bracketing the crossing.
    bracket: tuple[float, float]
    #: True when ``Delta J`` goes from negative to positive as the coordinate increases.
    rising: bool
    #: True when the crossing is an exact grid point rather than an interpolation.
    exact: bool

    def as_dict(self) -> dict:
        d = asdict(self)
        d["bracket"] = list(self.bracket)
        return d


def zero_crossings(coords, values, tol: float = _TOL) -> list[Crossing]:
    """All sign changes of ``values`` along ``coords``.

    Zeros that are *touched* but not crossed (the surface reaches zero and
    returns on the same side) are reported as crossings too: a point where the
    forecast exactly breaks even is on the frontier regardless of what the
    surface does next.  Runs of consecutive exact zeros report their first
    point only, so a flat zero plateau does not emit one crossing per cell.
    """
    x = np.asarray(coords, dtype=float).ravel()
    v = np.asarray(values, dtype=float).ravel()
    if x.shape != v.shape:
        raise ValueError(f"coords {x.shape} and values {v.shape} must match")
    if x.size < 2:
        return []

    out: list[Crossing] = []
    prev_was_zero = False
    for i in range(x.size):
        if abs(v[i]) <= tol:
            if not prev_was_zero:
                rising = bool(i + 1 < x.size and v[i + 1] > tol) or bool(i > 0 and v[i - 1] < -tol)
                out.append(Crossing(float(x[i]), (float(x[i]), float(x[i])), rising, True))
            prev_was_zero = True
            continue
        prev_was_zero = False
        if i == 0:
            continue
        a, b = v[i - 1], v[i]
        if abs(a) <= tol:
            continue  # already emitted at the zero point
        if a * b < 0:
            frac = a / (a - b)
            pos = float(x[i - 1] + frac * (x[i] - x[i - 1]))
            out.append(Crossing(pos, (float(x[i - 1]), float(x[i])), bool(b > a), False))
    return out


@dataclass(frozen=True)
class ColumnFrontier:
    """Crossings (possibly none, possibly several) along one column of a grid."""

    x_value: float
    crossings: tuple[Crossing, ...]
    #: ``"all_positive"``, ``"all_negative"``, or ``"crosses"``.
    status: str
    min_value: float
    max_value: float

    @property
    def n_crossings(self) -> int:
        return len(self.crossings)

    @property
    def first(self) -> float:
        """Lowest crossing position, or ``nan`` when there is none.

        Provided for plotting a single representative curve.  Reading only
        this and ignoring :attr:`n_crossings` is how a multi-valued frontier
        gets mistaken for a function; the plotting module marks columns with
        more than one crossing.
        """
        return self.crossings[0].position if self.crossings else float("nan")

    def as_dict(self) -> dict:
        return {
            "x_value": self.x_value, "status": self.status,
            "n_crossings": self.n_crossings,
            "crossings": [c.as_dict() for c in self.crossings],
            "min_value": self.min_value, "max_value": self.max_value,
        }


def frontier_from_grid(grid, surface: np.ndarray | None = None, tol: float = _TOL) -> list[ColumnFrontier]:
    """Per-column frontier of a :class:`~.grid.FrontierGrid` (or a bare surface).

    Columns run along the **y** axis, so the result answers "for this much
    direction error, at what latency does the forecast stop being worth it?".
    """
    z = grid.mean_delta if surface is None else np.asarray(surface, dtype=float)
    ys = np.asarray(grid.y_axis.values, dtype=float)
    xs = np.asarray(grid.x_axis.values, dtype=float)
    if z.shape != (ys.size, xs.size):
        raise ValueError(f"surface shape {z.shape} does not match grid {(ys.size, xs.size)}")
    out: list[ColumnFrontier] = []
    for ix, xv in enumerate(xs):
        col = z[:, ix]
        cr = zero_crossings(ys, col, tol=tol)
        if cr:
            status = "crosses"
        elif np.all(col > 0):
            status = "all_positive"
        elif np.all(col < 0):
            status = "all_negative"
        else:
            status = "crosses"
        out.append(ColumnFrontier(float(xv), tuple(cr), status,
                                  float(np.nanmin(col)), float(np.nanmax(col))))
    return out


def monotonicity_report(grid, surface: np.ndarray | None = None) -> dict:
    """Measure, do not assume.

    Reports for each axis the fraction of adjacent pairs that increase, the
    fraction that decrease, and whether the surface is monotone along that
    axis for every line.  A study that wants to quote a single break-even
    threshold should check ``columns_monotone`` first; where it is ``False``,
    a single threshold does not exist.
    """
    z = grid.mean_delta if surface is None else np.asarray(surface, dtype=float)
    dy = np.diff(z, axis=0)
    dx = np.diff(z, axis=1)

    def _stats(d):
        n = d.size
        if n == 0:
            return {"n_steps": 0, "frac_increasing": float("nan"),
                    "frac_decreasing": float("nan"), "frac_flat": float("nan")}
        return {
            "n_steps": int(n),
            "frac_increasing": float(np.mean(d > 0)),
            "frac_decreasing": float(np.mean(d < 0)),
            "frac_flat": float(np.mean(d == 0)),
        }

    cols_mono = bool(np.all(np.all(dy >= 0, axis=0) | np.all(dy <= 0, axis=0)))
    rows_mono = bool(np.all(np.all(dx >= 0, axis=1) | np.all(dx <= 0, axis=1)))
    frontier = frontier_from_grid(grid, z)
    return {
        "along_y": _stats(dy),
        "along_x": _stats(dx),
        "columns_monotone": cols_mono,
        "rows_monotone": rows_mono,
        "max_crossings_in_a_column": max((c.n_crossings for c in frontier), default=0),
        "n_columns_multi_crossing": int(sum(1 for c in frontier if c.n_crossings > 1)),
        "n_columns_no_crossing": int(sum(1 for c in frontier if c.n_crossings == 0)),
        "frontier_is_a_function_of_x": bool(all(c.n_crossings <= 1 for c in frontier)),
    }


def classify_regions(grid, surface: np.ndarray | None = None, tol: float = _TOL) -> np.ndarray:
    """``+1`` forecast better, ``-1`` trigger better, ``0`` break-even, per cell."""
    z = grid.mean_delta if surface is None else np.asarray(surface, dtype=float)
    out = np.zeros(z.shape, dtype=int)
    out[z > tol] = 1
    out[z < -tol] = -1
    return out
