"""Plane geometry conventions for the synthetic fire laboratory.

Conventions -- fixed everywhere in this package, and assumed by every test:

* Coordinates are Cartesian kilometres on a flat plane, ``(x, y)``.
  ``+x`` points **east**, ``+y`` points **north**.  There is no map
  projection, no terrain, and no curvature.  See ``docs/ASSUMPTIONS.md``.
* Angles are **radians**, measured counter-clockwise from ``+x`` (east).
  So east = ``0``, north = ``pi/2``, west = ``pi``, south = ``-pi/2``.
  This is the mathematical convention, *not* the compass-bearing convention
  (clockwise from north); :func:`bearing_to_heading` converts if you need it.
* Every angle returned by this module is wrapped to ``(-pi, pi]``.
* Times are hours; rates are km/h.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "wrap_to_pi",
    "angular_difference",
    "unit_vector",
    "heading_of",
    "rotate",
    "bearing_to_heading",
    "heading_to_bearing",
    "polar_offset",
]

_TWO_PI = 2.0 * np.pi


def wrap_to_pi(angle):
    """Wrap angle(s) to the half-open interval ``(-pi, pi]``.

    ``pi`` maps to ``pi`` (not ``-pi``) so that "due west" has a single stable
    representation; this matters because several degradation operators add a
    perturbation and then compare headings for equality in tests.
    """
    a = np.asarray(angle, dtype=float)
    wrapped = -(np.mod(-a + np.pi, _TWO_PI) - np.pi)
    # np.mod maps the open end to -pi for exactly-pi inputs; force +pi.
    wrapped = np.where(np.isclose(wrapped, -np.pi), np.pi, wrapped)
    return wrapped if wrapped.ndim else float(wrapped)


def angular_difference(a, b):
    """Signed smallest rotation taking ``b`` to ``a``, wrapped to ``(-pi, pi]``."""
    return wrap_to_pi(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))


def unit_vector(heading):
    """Unit vector(s) pointing along ``heading``.  Shape ``(..., 2)``."""
    h = np.asarray(heading, dtype=float)
    return np.stack([np.cos(h), np.sin(h)], axis=-1)


def heading_of(vector):
    """Heading of a displacement vector, wrapped to ``(-pi, pi]``.

    The heading of the zero vector is undefined; we return ``0.0`` and callers
    that care (the arrival-time field) special-case zero displacement first.
    """
    v = np.asarray(vector, dtype=float)
    return wrap_to_pi(np.arctan2(v[..., 1], v[..., 0]))


def rotate(vector, angle):
    """Rotate ``vector`` counter-clockwise by ``angle`` radians."""
    v = np.asarray(vector, dtype=float)
    c, s = np.cos(angle), np.sin(angle)
    x = v[..., 0] * c - v[..., 1] * s
    y = v[..., 0] * s + v[..., 1] * c
    return np.stack([x, y], axis=-1)


def bearing_to_heading(bearing_deg):
    """Compass bearing (degrees clockwise from north) -> heading (radians CCW from east)."""
    return wrap_to_pi(np.deg2rad(90.0 - np.asarray(bearing_deg, dtype=float)))


def heading_to_bearing(heading):
    """Heading (radians CCW from east) -> compass bearing in ``[0, 360)`` degrees."""
    deg = 90.0 - np.rad2deg(np.asarray(heading, dtype=float))
    return np.mod(deg, 360.0)


def polar_offset(magnitude, heading):
    """Cartesian offset of length ``magnitude`` along ``heading``.  Shape ``(..., 2)``."""
    return np.asarray(magnitude, dtype=float)[..., None] * unit_vector(heading) \
        if np.ndim(magnitude) else float(magnitude) * unit_vector(heading)
