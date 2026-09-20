"""Plotting: the figures must build, and the colour encoding must be honest."""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from wildfireguardian_forecast_value.frontiers.bands import bootstrap_frontier_band
from wildfireguardian_forecast_value.frontiers.grid import FrontierGrid, SweepAxis
from wildfireguardian_forecast_value.plotting.frontier_plot import plot_frontier, plot_scenario_map
from wildfireguardian_forecast_value.plotting.skill_vs_value import (
    plot_case_comparison,
    plot_skill_value_scatter,
)
from wildfireguardian_forecast_value.plotting.style import SERIES, diverging_cmap, symmetric_norm


def _grid(fn=lambda x, y: 1.0 - y, nw=25, seed=0, noise=0.3):
    x = SweepAxis("eps_theta", tuple(np.linspace(-0.5, 0.5, 7)),
                  label="direction error (deg)", display_scale=180 / np.pi)
    y = SweepAxis("latency", tuple(np.linspace(0.0, 2.0, 9)), kind="latency",
                  label="forecast latency (h)")
    rng = np.random.default_rng(seed)
    d = np.empty((9, 7, nw))
    for iy, yv in enumerate(y.values):
        for ix, xv in enumerate(x.values):
            d[iy, ix] = fn(xv, yv) + rng.normal(0, noise, nw)
    z = np.zeros_like(d)
    return FrontierGrid(x, y, d, z, z.astype(bool), np.ones_like(z, dtype=bool))


class TestStyle:
    def test_diverging_midpoint_is_neutral(self):
        cmap = diverging_cmap()
        r, g, b, _ = cmap(0.5)
        assert abs(r - g) < 0.05 and abs(g - b) < 0.08, "the midpoint must read as grey"

    def test_norm_is_symmetric_about_zero(self):
        n = symmetric_norm(np.array([-2.0, 30.0]))
        assert n.vcenter == 0.0
        assert n.vmin == pytest.approx(-n.vmax)

    def test_norm_survives_a_degenerate_surface(self):
        n = symmetric_norm(np.zeros((3, 3)))
        assert n.vmin < n.vcenter < n.vmax

    def test_categorical_order_is_fixed(self):
        assert SERIES[0] == "#2a78d6" and len(SERIES) == 3


class TestFigures:
    def test_frontier_figure_writes(self, tmp_path):
        g = _grid()
        band = bootstrap_frontier_band(g, n_boot=40, seed=0)
        p = plot_frontier(g, band, path=str(tmp_path / "f.png"))
        assert (tmp_path / "f.png").stat().st_size > 10_000

    def test_frontier_figure_without_a_band(self, tmp_path):
        plot_frontier(_grid(), None, path=str(tmp_path / "f2.png"))
        assert (tmp_path / "f2.png").exists()

    def test_frontier_figure_when_no_column_crosses(self, tmp_path):
        """A surface with no break-even anywhere must still render, and say so."""
        g = _grid(fn=lambda x, y: 5.0, noise=0.01)
        plot_frontier(g, bootstrap_frontier_band(g, n_boot=20, seed=0),
                      path=str(tmp_path / "f3.png"))
        assert (tmp_path / "f3.png").exists()

    def test_scenario_map(self, tmp_path, scenario):
        w = scenario.sample_world(3, 5)
        plot_scenario_map(scenario, w, times=(1.0, 2.0), path=str(tmp_path / "m.png"))
        assert (tmp_path / "m.png").stat().st_size > 10_000

    def test_case_comparison_handles_nan_value(self, tmp_path):
        rows = [("a", 0.9, 1.0), ("b", 0.4, 0.0), ("c", 0.6, float("nan"))]
        plot_case_comparison(rows, path=str(tmp_path / "c.png"))
        assert (tmp_path / "c.png").exists()

    def test_skill_value_scatter(self, tmp_path):
        s = np.linspace(0.3, 0.95, 12)
        d = np.concatenate([np.full(6, -5.0), np.full(6, 8.0)])
        plot_skill_value_scatter(s, d, annotations=[(s[0], d[0], "worst")],
                                 path=str(tmp_path / "s.png"))
        assert (tmp_path / "s.png").exists()

    def test_scatter_with_a_single_sign(self, tmp_path):
        plot_skill_value_scatter(np.linspace(0.3, 0.9, 5), np.full(5, 2.0),
                                 path=str(tmp_path / "s2.png"))
        assert (tmp_path / "s2.png").exists()


class TestBenchmarkProvenanceOnFigures:
    """A figure outlives the document that qualifies it, so it carries its own."""

    def _texts(self, fig):
        return [t.get_text() for t in fig.texts]

    def test_frontier_figure_is_stamped(self):
        from wildfireguardian_forecast_value.plotting.style import BENCHMARK_BANNER
        fig = plot_frontier(_grid(), None)
        joined = " ".join(self._texts(fig))
        assert BENCHMARK_BANNER in joined
        assert "NOT operational" in joined
        matplotlib.pyplot.close(fig)

    def test_scenario_map_is_stamped(self, scenario):
        from wildfireguardian_forecast_value.plotting.style import BENCHMARK_BANNER
        fig = plot_scenario_map(scenario, scenario.sample_world(0, 1), times=(1.0,))
        assert BENCHMARK_BANNER in " ".join(self._texts(fig))
        matplotlib.pyplot.close(fig)

    def test_case_comparison_is_stamped(self):
        from wildfireguardian_forecast_value.plotting.style import BENCHMARK_BANNER
        fig = plot_case_comparison([("a", 0.9, 1.0), ("b", 0.4, 0.0)])
        assert BENCHMARK_BANNER in " ".join(self._texts(fig))
        matplotlib.pyplot.close(fig)

    def test_skill_value_scatter_is_stamped(self):
        from wildfireguardian_forecast_value.plotting.style import BENCHMARK_BANNER
        fig = plot_skill_value_scatter(np.linspace(0.3, 0.9, 6), np.linspace(-3, 6, 6))
        assert BENCHMARK_BANNER in " ".join(self._texts(fig))
        matplotlib.pyplot.close(fig)

    def test_the_banner_text_is_the_required_wording(self):
        from wildfireguardian_forecast_value.plotting.style import BENCHMARK_BANNER
        assert BENCHMARK_BANNER == "CONSTRUCTED SYNTHETIC BENCHMARK"
