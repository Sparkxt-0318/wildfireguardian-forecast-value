"""Frontier estimation.  The central property under test is that nothing here
assumes the frontier is monotone, single-valued, or even present."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.frontiers.bands import (
    bootstrap_frontier_band,
    surface_band,
)
from wildfireguardian_forecast_value.frontiers.estimate import (
    classify_regions,
    frontier_from_grid,
    monotonicity_report,
    zero_crossings,
)
from wildfireguardian_forecast_value.frontiers.grid import FrontierGrid, SweepAxis, sweep_grid


class TestZeroCrossings:
    def test_single_crossing_is_interpolated(self):
        c = zero_crossings([0.0, 1.0], [-1.0, 3.0])
        assert len(c) == 1
        assert c[0].position == pytest.approx(0.25)
        assert c[0].rising and not c[0].exact
        assert c[0].bracket == (0.0, 1.0)

    def test_falling_crossing(self):
        c = zero_crossings([0.0, 1.0], [2.0, -2.0])
        assert len(c) == 1 and not c[0].rising

    def test_multiple_crossings_are_all_reported(self):
        """A non-monotone column has several break-even points, not one."""
        x = np.linspace(0.0, 3.0, 61)
        v = np.sin(np.pi * x)          # zeros at 0, 1, 2, 3
        c = zero_crossings(x, v)
        assert len(c) == 4
        assert [round(k.position, 6) for k in c] == [0.0, 1.0, 2.0, 3.0]

    def test_exact_grid_zero_is_reported_once(self):
        c = zero_crossings([0.0, 1.0, 2.0], [-1.0, 0.0, 1.0])
        assert len(c) == 1 and c[0].exact and c[0].position == 1.0

    def test_a_flat_zero_plateau_is_one_crossing_not_many(self):
        c = zero_crossings([0, 1, 2, 3, 4], [0.0, 0.0, 0.0, 1.0, 2.0])
        assert len(c) == 1 and c[0].position == 0.0

    def test_no_crossing_returns_empty(self):
        assert zero_crossings([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == []
        assert zero_crossings([0.0, 1.0, 2.0], [-1.0, -2.0, -3.0]) == []

    def test_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="must match"):
            zero_crossings([0.0, 1.0], [1.0])


def _synthetic_grid(surface_fn, nx=9, ny=11, nw=20, noise=0.0, seed=0):
    x = SweepAxis("x", tuple(np.linspace(-1.0, 1.0, nx)))
    y = SweepAxis("y", tuple(np.linspace(0.0, 2.0, ny)))
    rng = np.random.default_rng(seed)
    delta = np.empty((ny, nx, nw))
    for iy, yv in enumerate(y.values):
        for ix, xv in enumerate(x.values):
            base = surface_fn(xv, yv)
            delta[iy, ix] = base + (rng.normal(0, noise, nw) if noise else 0.0)
    zeros = np.zeros_like(delta)
    return FrontierGrid(x, y, delta, zeros, zeros.astype(bool), np.ones_like(zeros, dtype=bool))


class TestFrontierFromGrid:
    def test_monotone_surface_gives_one_crossing_per_column(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y)          # crosses at y = 1 everywhere
        cols = frontier_from_grid(g)
        assert all(c.n_crossings == 1 for c in cols)
        assert all(c.first == pytest.approx(1.0) for c in cols)

    def test_non_monotone_column_is_reported_as_multi_valued(self):
        """The estimator must not silently pick one of several crossings."""
        g = _synthetic_grid(lambda x, y: np.sin(np.pi * y) - 0.0, ny=41)
        cols = frontier_from_grid(g)
        assert max(c.n_crossings for c in cols) >= 3
        assert not monotonicity_report(g)["frontier_is_a_function_of_x"]

    def test_columns_without_a_crossing_are_labelled(self):
        g = _synthetic_grid(lambda x, y: 1.0 if x > 0 else 5.0 - y * 0.0)
        cols = frontier_from_grid(g)
        assert all(c.status == "all_positive" and c.n_crossings == 0 for c in cols)
        assert np.isnan(cols[0].first)

    def test_negative_surface_is_labelled_all_negative(self):
        g = _synthetic_grid(lambda x, y: -3.0)
        assert all(c.status == "all_negative" for c in frontier_from_grid(g))

    def test_surface_shape_is_validated(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y)
        with pytest.raises(ValueError, match="does not match"):
            frontier_from_grid(g, np.zeros((2, 2)))


class TestMonotonicityReport:
    def test_measures_rather_than_assumes(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y)
        r = monotonicity_report(g)
        assert r["columns_monotone"] is True
        assert r["along_y"]["frac_decreasing"] == pytest.approx(1.0)

    def test_detects_non_monotone(self):
        g = _synthetic_grid(lambda x, y: np.sin(np.pi * y), ny=41)
        r = monotonicity_report(g)
        assert r["columns_monotone"] is False
        assert r["n_columns_multi_crossing"] > 0

    def test_classify_regions(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y)
        reg = classify_regions(g)
        assert set(np.unique(reg)) <= {-1, 0, 1}
        assert reg[0, 0] == 1 and reg[-1, 0] == -1


class TestBands:
    def test_band_brackets_the_point_estimate(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y, nw=60, noise=0.4, seed=1)
        b = bootstrap_frontier_band(g, n_boot=200, seed=0)
        ok = np.isfinite(b.estimate) & np.isfinite(b.lower)
        assert ok.any()
        assert np.all(b.lower[ok] <= b.estimate[ok] + 1e-9)
        assert np.all(b.upper[ok] >= b.estimate[ok] - 1e-9)

    def test_noisier_data_gives_wider_bands(self):
        quiet = bootstrap_frontier_band(
            _synthetic_grid(lambda x, y: 1.0 - y, nw=60, noise=0.05, seed=2),
            n_boot=200, seed=0)
        loud = bootstrap_frontier_band(
            _synthetic_grid(lambda x, y: 1.0 - y, nw=60, noise=0.8, seed=2),
            n_boot=200, seed=0)
        qw = np.nanmean(quiet.upper - quiet.lower)
        lw = np.nanmean(loud.upper - loud.lower)
        assert lw > qw

    def test_crossing_rate_is_reported(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y, nw=40, noise=0.2, seed=3)
        b = bootstrap_frontier_band(g, n_boot=150, seed=0)
        assert b.crossing_rate.shape == (len(g.x_axis.values),)
        assert np.all((b.crossing_rate >= 0) & (b.crossing_rate <= 1))

    def test_a_column_with_no_frontier_has_crossing_rate_zero(self):
        g = _synthetic_grid(lambda x, y: 5.0, nw=30)
        b = bootstrap_frontier_band(g, n_boot=100, seed=0)
        assert np.all(b.crossing_rate == 0.0)
        assert np.all(np.isnan(b.estimate))

    def test_which_selects_among_multiple_crossings(self):
        g = _synthetic_grid(lambda x, y: np.sin(np.pi * y), ny=41, nw=20)
        first = bootstrap_frontier_band(g, n_boot=30, seed=0, which="first")
        last = bootstrap_frontier_band(g, n_boot=30, seed=0, which="last")
        assert np.nanmax(last.estimate) > np.nanmax(first.estimate)
        assert np.any(last.multi_crossing_rate > 0)

    def test_invalid_which_rejected(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y)
        with pytest.raises(ValueError, match="first"):
            bootstrap_frontier_band(g, n_boot=10, which="middle")

    def test_surface_band_brackets_the_mean(self):
        g = _synthetic_grid(lambda x, y: 1.0 - y, nw=50, noise=0.5, seed=4)
        lo, hi = surface_band(g, n_boot=200, seed=0)
        assert np.all(lo <= g.mean_delta + 1e-9) and np.all(hi >= g.mean_delta - 1e-9)


class TestSweepAxis:
    def test_requires_increasing_values(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            SweepAxis("x", (1.0, 0.0))

    def test_requires_two_values(self):
        with pytest.raises(ValueError, match="at least two"):
            SweepAxis("x", (1.0,))

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="axis kind"):
            SweepAxis("x", (0.0, 1.0), kind="weather")

    def test_display_scale(self):
        a = SweepAxis("t", (0.0, np.pi), display_scale=180 / np.pi, label="deg")
        assert a.display_values[1] == pytest.approx(180.0)
        assert a.display_label == "deg"


class TestSweepIntegration:
    def test_common_random_numbers_across_cells(self, scenario, pipeline):
        """Cells must share worlds; that is what makes the surface comparable."""
        x = SweepAxis("eps_theta", tuple(np.deg2rad([-10.0, 0.0, 10.0])))
        y = SweepAxis("latency", (0.0, 0.3), kind="latency")
        g = sweep_grid(scenario, x, y, n_worlds=12, seed=2, pipeline=pipeline,
                       base_latency=LatencySpec(0.6, 0.0), skill_keys=())
        assert g.delta.shape == (2, 3, 12)
        assert g.meta["common_random_numbers"] is True
        # Zero latency rows are identical between the two latency values that
        # both land before the decision time.
        assert np.allclose(g.delta[0], g.delta[1])

    def test_long_frame_round_trips_the_surface(self, scenario, pipeline):
        x = SweepAxis("eps_theta", tuple(np.deg2rad([-10.0, 10.0])))
        y = SweepAxis("latency", (0.0, 0.5), kind="latency")
        g = sweep_grid(scenario, x, y, n_worlds=6, seed=2, pipeline=pipeline,
                       base_latency=LatencySpec(0.6, 0.0), skill_keys=())
        df = g.to_long_frame()
        assert len(df) == 2 * 2 * 6
        assert df.attrs["unit_of_analysis"] == "world"
        recovered = df.pivot_table(index="y_index", columns="x_index",
                                   values="delta_j", aggfunc="mean").to_numpy()
        assert np.allclose(recovered, g.mean_delta)


@pytest.mark.slow
class TestNonMonotoneInTheRealScenario:
    """The non-monotonicity is not a synthetic curiosity; the packaged
    scenario produces it.

    This mirrors ``experiments/manifests/frontier_short_wait.yaml``: with a
    short ``max_wait`` the forecast becomes unavailable partway up the latency
    axis, ``Delta J`` collapses to exactly zero there, and columns near
    ``-15 deg`` cross zero twice -- once where the forecast stops being worth
    acting on, and again where it stops being available at all.
    """

    def test_short_wait_produces_multi_valued_columns(self, scenario, pipeline):
        from wildfireguardian_forecast_value.decision_value.value import default_policies

        x = SweepAxis("eps_theta", tuple(np.deg2rad([-18.0, -15.0, -11.0, -4.0, 8.0])),
                      label="direction error (deg)", display_scale=180 / np.pi)
        y = SweepAxis("latency", tuple(np.linspace(0.0, 1.3, 9)), kind="latency")
        grid = sweep_grid(scenario, x, y, n_worlds=40, seed=11, pipeline=pipeline,
                          base_latency=LatencySpec(0.6, 0.0),
                          policies=default_policies(scenario, max_wait=0.8),
                          skill_keys=())
        report = monotonicity_report(grid)
        assert report["n_columns_multi_crossing"] > 0, (
            "experiments/manifests/frontier_short_wait.yaml is documented as the "
            "regression fixture for a multi-valued frontier; it no longer produces one"
        )
        assert not report["frontier_is_a_function_of_x"]

    def test_long_wait_does_not(self, scenario, pipeline):
        """The shipped configuration is single-valued -- measured, not assumed."""
        from wildfireguardian_forecast_value.decision_value.value import default_policies

        x = SweepAxis("eps_theta", tuple(np.deg2rad([-11.0, 0.0, 11.0])))
        y = SweepAxis("latency", tuple(np.linspace(0.0, 1.8, 10)), kind="latency")
        grid = sweep_grid(scenario, x, y, n_worlds=40, seed=11, pipeline=pipeline,
                          base_latency=LatencySpec(0.6, 0.0),
                          policies=default_policies(scenario, max_wait=1.6),
                          skill_keys=())
        assert monotonicity_report(grid)["frontier_is_a_function_of_x"]
