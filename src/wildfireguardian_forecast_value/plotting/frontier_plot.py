"""The primary demonstration figure: the break-even frontier."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np

from wildfireguardian_forecast_value.frontiers.estimate import frontier_from_grid
from wildfireguardian_forecast_value.plotting.style import (
    SERIES,
    TOKENS,
    add_benchmark_banner,
    apply_axes_style,
    diverging_cmap,
    symmetric_norm,
)

__all__ = ["plot_frontier", "plot_scenario_map"]


def plot_frontier(
    grid,
    band=None,
    title: str = "When is a wildfire forecast worth acting on?",
    subtitle: str | None = None,
    path: str | None = None,
    annotate_regions: bool = True,
):
    """Filled ``Delta J`` surface with the ``Delta J = 0`` frontier and its band.

    Three things are drawn that a plain contour plot would leave out, each
    because leaving it out would overstate what the estimate supports:

    * columns where ``Delta J`` never crosses zero are marked along the top,
      since there is no frontier there to draw and interpolating one would
      invent it;
    * columns where the bootstrap found a crossing in fewer than 80% of
      replicates are drawn faded -- the frontier exists there only sometimes;
    * columns with more than one crossing get a marker, because the single
      plotted line is then a choice, not the answer.
    """
    x = np.asarray(grid.x_axis.display_values, dtype=float)
    y = np.asarray(grid.y_axis.display_values, dtype=float)
    Z = grid.mean_delta

    fig, ax = plt.subplots(figsize=(8.8, 6.2), facecolor=TOKENS["surface"])
    norm = symmetric_norm(Z)
    mesh = ax.pcolormesh(x, y, Z, cmap=diverging_cmap(), norm=norm, shading="nearest")
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02)
    cbar.set_label("mean $\\Delta J$  (hours of equivalent delay)\nblue: forecast better   ·   red: trigger better",
                   color=TOKENS["text_secondary"], fontsize=9)
    cbar.ax.tick_params(colors=TOKENS["text_secondary"], labelsize=8.5)
    cbar.outline.set_edgecolor(TOKENS["axis"])

    cols = frontier_from_grid(grid)
    pos = np.array([c.first for c in cols], dtype=float)
    scale = grid.y_axis.display_scale
    ax.plot(x, pos * scale, color=TOKENS["text_primary"], linewidth=2.0,
            solid_capstyle="round", zorder=5, label="break-even frontier  ($\\Delta J = 0$)")

    if band is not None:
        lo = np.asarray(band.lower, dtype=float) * scale
        hi = np.asarray(band.upper, dtype=float) * scale
        rate = np.asarray(band.crossing_rate, dtype=float)
        solid = rate >= 0.8
        ax.fill_between(x, lo, hi, where=solid, color=TOKENS["text_primary"], alpha=0.20,
                        linewidth=0, zorder=4,
                        label=f"{band.confidence:.0%} bootstrap band ({band.n_boot} world resamples)")
        if np.any(~solid & np.isfinite(lo)):
            ax.fill_between(x, lo, hi, where=~solid, color=TOKENS["text_primary"], alpha=0.07,
                            linewidth=0, zorder=4,
                            label="band where the frontier exists in <80% of resamples")
        multi = np.asarray(band.multi_crossing_rate, dtype=float) > 0.05
        if np.any(multi):
            ax.scatter(x[multi], pos[multi] * scale, s=34, facecolor=TOKENS["surface"],
                       edgecolor=TOKENS["text_primary"], linewidth=1.4, zorder=6,
                       label="column has more than one crossing")

    missing = ~np.isfinite(pos)
    if np.any(missing):
        ytop = float(np.max(y))
        ax.scatter(x[missing], np.full(missing.sum(), ytop), marker="v", s=40,
                   color=TOKENS["critical"], zorder=6, clip_on=False,
                   label="no break-even: the trigger wins at every latency")

    if annotate_regions:
        if np.any(np.isfinite(pos)):
            ax.text(0.97, 0.06, "forecast better", transform=ax.transAxes, ha="right", va="bottom",
                    fontsize=11, color=TOKENS["text_primary"], fontweight="bold")
            ax.text(0.03, 0.94, "trigger better", transform=ax.transAxes, ha="left", va="top",
                    fontsize=11, color=TOKENS["text_primary"], fontweight="bold")

    if subtitle is None:
        subtitle = (f"synthetic scenario · {grid.n_worlds} paired worlds per cell · "
                    "common random numbers across the grid")
    apply_axes_style(ax, title, subtitle,
                     xlabel=grid.x_axis.display_label, ylabel=grid.y_axis.display_label)
    # Below the axes: every corner of this plot carries data or a region label.
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncols=2,
                    frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(TOKENS["text_secondary"])
    fig.tight_layout(rect=(0, 0.075, 1, 0.965))
    add_benchmark_banner(fig)
    if path:
        fig.savefig(path, dpi=170, facecolor=TOKENS["surface"])
        plt.close(fig)
        return path
    return fig


def plot_scenario_map(scenario, world, times=(1.0, 2.0, 3.0), path: str | None = None):
    """The scenario geometry: fire footprints at several times, and the two routes."""
    fig, ax = plt.subplots(figsize=(7.6, 6.2), facecolor=TOKENS["surface"])
    g = scenario.grid
    arrival = g.arrival_field(world.truth)
    xs = np.linspace(g.x_min, g.x_max, g.nx)
    ys = np.linspace(g.y_min, g.y_max, g.ny)

    # Footprints nest, so the largest must go down first or it hides the rest.
    order = sorted(times, reverse=True)
    shades = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5"]
    for t, c in zip(order, shades):
        ax.contourf(xs, ys, (arrival <= t).astype(float), levels=[0.5, 1.5], colors=[c], alpha=0.9)
    for t in order:
        ax.contour(xs, ys, arrival, levels=[t], colors=[TOKENS["axis"]], linewidths=0.8)
        far = np.unravel_index(np.argmax(np.where(arrival <= t, arrival, -np.inf)), arrival.shape)
        ax.annotate(f"t={t:g} h", xy=(xs[far[1]], ys[far[0]]), xytext=(-4, 6),
                    textcoords="offset points", ha="right", fontsize=8.5,
                    color=TOKENS["text_secondary"])

    for route, colour in zip(scenario.routes, SERIES):
        w = np.asarray(route.waypoints, dtype=float)
        ax.plot(w[:, 0], w[:, 1], color=colour, linewidth=2.4, solid_capstyle="round",
                marker="o", markersize=5, label=f"{route.name} ({route.length:.1f} km)")
        pts, arc = route.samples
        mid = pts[int(np.argmin(np.abs(arc - arc[-1] / 2.0)))]
        ax.annotate(route.name, xy=(mid[0], mid[1]), xytext=(6, 7), textcoords="offset points",
                    color=colour, fontsize=10, fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=TOKENS["surface"])])

    c = np.asarray(scenario.community, dtype=float)
    s = np.asarray(scenario.safe_haven, dtype=float)
    ig = np.asarray(world.truth.by_label("main").origin, dtype=float)
    for pt, lab, mk, off in ((c, "community", "s", (9, -4)), (s, "safe haven", "*", (0, 12)),
                             (ig, "ignition", "X", (9, -12))):
        ax.scatter(*pt, marker=mk, s=130, color=TOKENS["text_primary"], zorder=7,
                   edgecolor=TOKENS["surface"], linewidth=1.2)
        ax.annotate(lab, xy=pt, xytext=off, textcoords="offset points", zorder=7,
                    ha="center" if off[0] == 0 else "left",
                    fontsize=9.5, color=TOKENS["text_primary"],
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=TOKENS["surface"])])
    for sp in world.truth.of_kind("spot"):
        ax.scatter(*sp.origin, marker="^", s=95, color=TOKENS["critical"], zorder=7,
                   edgecolor=TOKENS["surface"], linewidth=1.2)
        ax.annotate(f"spot ignition (t={sp.ignition_time:.2f} h)", xy=sp.origin, xytext=(9, 4),
                    textcoords="offset points", fontsize=9, color=TOKENS["critical"], zorder=7,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=TOKENS["surface"])])

    apply_axes_style(
        ax, "Toy evacuation scenario",
        f"burned footprint at t = {', '.join(f'{t:g}' for t in times)} h · "
        f"decision at t = {scenario.decision_time:g} h · route A is shorter but crosses the fire corridor",
        xlabel="x (km, east)", ylabel="y (km, north)")
    ax.set_aspect("equal")
    leg = ax.legend(loc="lower right", frameon=True, fontsize=9, facecolor=TOKENS["surface"],
                    edgecolor=TOKENS["grid"])
    for t in leg.get_texts():
        t.set_color(TOKENS["text_secondary"])
    fig.tight_layout(rect=(0, 0.075, 1, 0.965))
    add_benchmark_banner(fig)
    if path:
        fig.savefig(path, dpi=170, facecolor=TOKENS["surface"])
        plt.close(fig)
        return path
    return fig
