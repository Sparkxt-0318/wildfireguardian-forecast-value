"""Geometry conventions and the arrival-time field."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.fields.front import NEVER, FireSource, FireState, known_at
from wildfireguardian_forecast_value.fields.geometry import (
    angular_difference,
    bearing_to_heading,
    heading_of,
    heading_to_bearing,
    rotate,
    unit_vector,
    wrap_to_pi,
)
from wildfireguardian_forecast_value.fields.grids import RasterGrid


class TestAngles:
    def test_wrap_endpoints(self):
        assert wrap_to_pi(np.pi) == pytest.approx(np.pi)
        assert wrap_to_pi(-np.pi) == pytest.approx(np.pi)
        assert wrap_to_pi(3 * np.pi) == pytest.approx(np.pi)
        assert wrap_to_pi(0.0) == pytest.approx(0.0)

    def test_wrap_is_idempotent(self):
        a = np.linspace(-20, 20, 501)
        assert np.allclose(wrap_to_pi(wrap_to_pi(a)), wrap_to_pi(a))

    def test_near_branch_cut_difference_is_small(self):
        """179 deg and -179 deg differ by 2 deg, not 358."""
        d = angular_difference(np.deg2rad(179), np.deg2rad(-179))
        assert abs(np.rad2deg(d)) == pytest.approx(2.0, abs=1e-9)

    def test_bearing_roundtrip(self):
        for b in (0.0, 45.0, 90.0, 180.0, 270.0, 359.0):
            assert heading_to_bearing(bearing_to_heading(b)) == pytest.approx(b, abs=1e-9)

    def test_east_is_zero_north_is_half_pi(self):
        assert np.allclose(unit_vector(0.0), [1.0, 0.0])
        assert np.allclose(unit_vector(np.pi / 2), [0.0, 1.0], atol=1e-15)

    def test_rotate_preserves_length(self):
        v = np.array([3.0, 4.0])
        assert np.linalg.norm(rotate(v, 0.7)) == pytest.approx(5.0)

    def test_heading_of_round_trips(self):
        for h in np.linspace(-np.pi + 0.01, np.pi, 20):
            assert heading_of(unit_vector(h)) == pytest.approx(wrap_to_pi(h), abs=1e-12)


class TestFireSource:
    def test_rejects_bad_parameters(self):
        with pytest.raises(ValueError, match="spread_rate"):
            FireSource(origin=(0, 0), ignition_time=0, spread_rate=0.0, heading=0, half_angle=1.0)
        with pytest.raises(ValueError, match="half_angle"):
            FireSource(origin=(0, 0), ignition_time=0, spread_rate=1.0, heading=0, half_angle=0.0)
        with pytest.raises(ValueError, match="origin"):
            FireSource(origin=(0, 0, 0), ignition_time=0, spread_rate=1, heading=0, half_angle=1)
        with pytest.raises(ValueError, match="kind"):
            FireSource(origin=(0, 0), ignition_time=0, spread_rate=1, heading=0,
                       half_angle=1, kind="ember")

    def test_outside_the_wedge_is_never_not_late(self, wedge):
        t = wedge.arrival_time([[0.0, 4.0]])
        assert np.isinf(t[0]) and t[0] > 0

    def test_wedge_edge_counts_as_inside(self, wedge):
        """Exactly on the edge is inside; the tolerance makes that deterministic."""
        edge = np.array([[np.cos(np.pi / 4), np.sin(np.pi / 4)]]) * 4.0
        assert np.isfinite(wedge.arrival_time(edge)[0])

    def test_origin_burns_at_ignition_even_for_a_narrow_wedge(self):
        s = FireSource(origin=(1.0, 2.0), ignition_time=0.5, spread_rate=3.0,
                       heading=0.0, half_angle=0.01)
        assert s.arrival_time([[1.0, 2.0]])[0] == pytest.approx(0.5)

    def test_isotropic_never_returns_never(self, spot):
        pts = np.random.default_rng(0).normal(size=(50, 2)) * 10
        assert np.all(np.isfinite(spot.arrival_time(pts)))

    def test_arrival_time_is_linear_in_distance(self, wedge):
        pts = np.array([[1.0, 0.0], [2.0, 0.0], [4.0, 0.0]])
        t = wedge.arrival_time(pts)
        assert np.allclose(t, [0.5, 1.0, 2.0])


class TestDistanceToBurned:
    def test_zero_inside_the_burn(self, wedge):
        assert wedge.distance_to_burned([[1.0, 0.0]], 1.0)[0] == pytest.approx(0.0)

    def test_radial_outside_along_the_axis(self, wedge):
        # At t=1 the burned radius is 2; (5,0) is 3 km beyond the front.
        assert wedge.distance_to_burned([[5.0, 0.0]], 1.0)[0] == pytest.approx(3.0)

    def test_before_ignition_there_is_no_burned_set(self, spot):
        assert np.isinf(spot.distance_to_burned([[6.0, 0.0]], 0.5)[0])

    def test_angularly_outside_uses_the_edge(self, wedge):
        # Edge tip at t=1 is 2*(cos45, sin45); distance from (0,5) to that tip.
        tip = 2.0 * np.array([np.cos(np.pi / 4), np.sin(np.pi / 4)])
        expected = float(np.linalg.norm(np.array([0.0, 5.0]) - tip))
        assert wedge.distance_to_burned([[0.0, 5.0]], 1.0)[0] == pytest.approx(expected)

    def test_monotone_decreasing_in_time(self, wedge):
        p = [[8.0, 0.0]]
        d = [float(wedge.distance_to_burned(p, t)[0]) for t in (0.5, 1.0, 2.0, 4.0)]
        assert d == sorted(d, reverse=True)
        assert d[-1] == pytest.approx(0.0)


class TestFireState:
    def test_minimum_over_sources(self, two_source_state):
        # (6,0): the spot's own origin, arriving at its ignition time 1.0;
        # the main front would take 3.0 h.
        assert two_source_state.arrival_time([[6.0, 0.0]])[0] == pytest.approx(1.0)

    def test_empty_state_never_burns(self):
        assert np.isinf(FireState().arrival_time([[0.0, 0.0]])[0])

    def test_duplicate_labels_rejected(self, wedge):
        with pytest.raises(ValueError, match="unique"):
            FireState((wedge, wedge))

    def test_known_at_is_inclusive(self, two_source_state):
        assert len(known_at(two_source_state, 0.999)) == 1
        assert len(known_at(two_source_state, 1.0)) == 2

    def test_replace_source_preserves_order(self, two_source_state):
        out = two_source_state.replace_source("main", two_source_state.by_label("main"))
        assert out.labels == two_source_state.labels

    def test_round_trip_serialisation(self, two_source_state):
        again = FireState.from_dict(two_source_state.to_dict())
        assert again.to_dict() == two_source_state.to_dict()


class TestRasterGrid:
    def test_cell_geometry(self):
        g = RasterGrid(0, 4, 0, 2, 4, 2)
        assert (g.dx, g.dy, g.cell_area, g.n_cells) == (1.0, 1.0, 1.0, 8)
        assert g.centres().shape == (2, 4, 2)
        assert g.flat_centres()[0].tolist() == [0.5, 0.5]

    def test_rejects_inverted_bounds(self):
        with pytest.raises(ValueError, match="min < max"):
            RasterGrid(4, 0, 0, 2, 4, 2)

    def test_burned_field_matches_arrival(self, wedge):
        g = RasterGrid(-1, 5, -3, 3, 12, 12)
        st = FireState((wedge,))
        assert np.array_equal(g.burned_field(st, 1.25), g.arrival_field(st) <= 1.25)
