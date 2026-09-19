"""Figures.  Matplotlib only, ``Agg`` backend, no interactive state."""

from wildfireguardian_forecast_value.plotting.frontier_plot import plot_frontier, plot_scenario_map
from wildfireguardian_forecast_value.plotting.skill_vs_value import (
    plot_case_comparison,
    plot_skill_value_scatter,
)
from wildfireguardian_forecast_value.plotting.style import (
    SERIES,
    TOKENS,
    apply_axes_style,
    diverging_cmap,
    symmetric_norm,
)

__all__ = [
    "plot_frontier", "plot_scenario_map", "plot_case_comparison", "plot_skill_value_scatter",
    "TOKENS", "SERIES", "diverging_cmap", "symmetric_norm", "apply_axes_style",
]
