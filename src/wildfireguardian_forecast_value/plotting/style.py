"""Shared figure tokens.

Colour is assigned by the *job* it does, not by taste:

* ``Delta J`` is a **polarity** quantity -- it has a meaningful zero (the
  break-even point) and two opposite signs -- so it gets a **diverging** ramp:
  blue for "forecast better", red for "trigger better", a neutral grey exactly
  at zero.  The norm is forced symmetric about zero so the neutral midpoint
  lands on the frontier and not somewhere near it.
* Series identity uses a fixed categorical order, never a cycled one.
* Text never wears a series colour.

The categorical slots below were validated for colour-vision deficiency
separation on the light surface (worst all-pairs CVD dE 9.2, normal-vision
dE 24.0).  The aqua slot sits below 3:1 contrast against the surface, so any
chart using it also carries direct labels rather than relying on the legend.
"""

from __future__ import annotations

from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

__all__ = ["TOKENS", "SERIES", "diverging_cmap", "symmetric_norm", "apply_axes_style",
           "add_benchmark_banner", "BENCHMARK_BANNER", "BENCHMARK_FOOTNOTE"]

#: Stamped on every figure. These are constructed fixtures, and a figure that
#: travels without its provenance is the most likely way for a synthetic
#: threshold to be quoted as an operational requirement.
BENCHMARK_BANNER = "CONSTRUCTED SYNTHETIC BENCHMARK"

BENCHMARK_FOOTNOTE = (
    "Constructed synthetic benchmark (docs/CURRENT_RESULT_STATUS.md). Axis values are\n"
    "properties of a geometry built to expose the phenomenon, NOT operational\n"
    "requirements and NOT a claim about real wildfire forecast performance."
)

TOKENS = {
    "surface": "#fcfcfb",
    "text_primary": "#0b0b0b",
    "text_secondary": "#52514e",
    "text_muted": "#8a8983",
    "grid": "#dedcd6",
    "axis": "#b4b2ab",
    "neutral_mid": "#f0efec",
    "good": "#0ca30c",
    "critical": "#d03b3b",
}

#: Fixed categorical order.  A fourth series folds into "other" or gets its own
#: panel; it is never a generated hue.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")

#: Diverging poles.  Blue = forecast better, red = trigger better.
_DIVERGING = ["#0d366b", "#2a78d6", "#86b6ef", TOKENS["neutral_mid"], "#ef9a99", "#e34948", "#8f2322"]


def diverging_cmap(name: str = "wgfv_delta") -> LinearSegmentedColormap:
    """Blue -> neutral grey -> red, equal step count per arm."""
    return LinearSegmentedColormap.from_list(name, _DIVERGING[::-1], N=256)


def symmetric_norm(values, centre: float = 0.0) -> TwoSlopeNorm:
    """Norm with the neutral midpoint pinned exactly at ``centre``.

    Symmetric limits, so equal magnitudes of "forecast better" and "trigger
    better" read as equally saturated.  Without this the eye reads the larger
    arm as the more important one purely because the data happened to be
    asymmetric.
    """
    import numpy as np

    v = np.asarray(values, dtype=float)
    finite = v[np.isfinite(v)]
    span = float(np.max(np.abs(finite - centre))) if finite.size else 1.0
    span = span if span > 0 else 1.0
    return TwoSlopeNorm(vmin=centre - span, vcenter=centre, vmax=centre + span)


def apply_axes_style(ax, title: str = "", subtitle: str = "",
                     xlabel: str = "", ylabel: str = "") -> None:
    """Recessive grid and axes; text in ink tokens."""
    ax.set_facecolor(TOKENS["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(TOKENS["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=TOKENS["text_secondary"], labelsize=9, length=3, width=0.8)
    ax.grid(True, color=TOKENS["grid"], linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    if xlabel:
        ax.set_xlabel(xlabel, color=TOKENS["text_secondary"], fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=TOKENS["text_secondary"], fontsize=10)
    if title:
        ax.set_title(title, color=TOKENS["text_primary"], fontsize=12.5,
                     fontweight="bold", loc="left", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, ha="left", va="bottom",
                color=TOKENS["text_secondary"], fontsize=9.5)


def add_benchmark_banner(fig, footnote: bool = True) -> None:
    """Stamp a figure as a constructed benchmark.

    Prominent by design.  Every number on these axes is a property of a
    geometry that was tuned to make a phenomenon visible
    (``docs/PARAMETER_PROVENANCE.md``).  Figures outlive the documents that
    qualify them, so the qualification travels on the figure.
    """
    fig.text(
        0.995, 0.987, BENCHMARK_BANNER,
        ha="right", va="top", fontsize=9, fontweight="bold",
        color="#7a1f1f",
        bbox=dict(boxstyle="round,pad=0.42", facecolor="#fbe4e4",
                  edgecolor="#d03b3b", linewidth=1.0),
        zorder=1000,
    )
    if footnote:
        fig.text(0.008, 0.004, BENCHMARK_FOOTNOTE, ha="left", va="bottom",
                 fontsize=7.4, color=TOKENS["text_muted"], linespacing=1.35, zorder=1000)
