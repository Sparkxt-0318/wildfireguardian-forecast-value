"""Figures that show skill and decision value coming apart."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wildfireguardian_forecast_value.plotting.style import (
    SERIES,
    TOKENS,
    add_benchmark_banner,
    apply_axes_style,
)

__all__ = ["plot_case_comparison", "plot_skill_value_scatter"]


def plot_case_comparison(rows, path: str | None = None):
    """Grouped bars: footprint skill against realised decision value, per case arm.

    Both measures are dimensionless and live on ``[0, 1]``, so they share one
    axis.  A second y-scale would make the two bars visually comparable when
    they are not, and is exactly the wrong chart here -- the whole claim is
    that these two numbers do not track each other, which the reader must be
    able to see on a single scale.

    ``rows`` is a sequence of ``(label, csi, value_fraction)``.
    """
    labels = [r[0] for r in rows]
    csi = np.array([r[1] for r in rows], dtype=float)
    frac = np.array([0.0 if not np.isfinite(r[2]) else r[2] for r in rows], dtype=float)
    undecidable = np.array([not np.isfinite(r[2]) for r in rows], dtype=bool)

    idx = np.arange(len(rows), dtype=float)
    w = 0.38
    fig, ax = plt.subplots(figsize=(9.4, 5.2), facecolor=TOKENS["surface"])
    b1 = ax.bar(idx - w / 2 - 0.01, csi, width=w, color=SERIES[0],
                label="forecast skill (footprint CSI)", zorder=3)
    b2 = ax.bar(idx + w / 2 + 0.01, frac, width=w, color=SERIES[1],
                label="decision value realised (fraction of future-oracle value)", zorder=3)

    for rect, v in zip(b1, csi):
        ax.annotate(f"{v:.2f}", (rect.get_x() + rect.get_width() / 2, v), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8.5,
                    color=TOKENS["text_secondary"])
    for rect, v, u in zip(b2, frac, undecidable):
        ax.annotate("n/a" if u else f"{v:.2f}",
                    (rect.get_x() + rect.get_width() / 2, v), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8.5,
                    color=TOKENS["text_secondary"])

    ax.set_xticks(idx)
    ax.set_xticklabels(labels, fontsize=9, color=TOKENS["text_secondary"])
    ax.set_ylim(0, 1.15)
    apply_axes_style(
        ax, "Better prediction scores, worse decisions",
        "the four hand-designed cases · higher is better on both bars",
        ylabel="score / fraction (0-1)")
    leg = ax.legend(loc="upper center", ncols=2, frameon=True, fontsize=9,
                    facecolor=TOKENS["surface"], edgecolor=TOKENS["grid"])
    for t in leg.get_texts():
        t.set_color(TOKENS["text_secondary"])
    fig.text(0.008, 0.072,
             '"n/a" marks a case where the forecast-free trigger was already optimal, '
             "so even a future oracle was worth nothing and the fraction is 0/0.",
             color=TOKENS["text_muted"], fontsize=8)
    fig.tight_layout(rect=(0, 0.105, 1, 0.965))
    add_benchmark_banner(fig)
    if path:
        fig.savefig(path, dpi=170, facecolor=TOKENS["surface"])
        plt.close(fig)
        return path
    return fig


def plot_skill_value_scatter(skill, delta_j, skill_label: str = "footprint CSI",
                             annotations=None, path: str | None = None):
    """Decision value against a skill score, over a degradation sweep.

    Two series by outcome rather than by case, so the palette stays inside the
    three slots that validate for an all-pairs chart form, and every point that
    matters carries a direct label.
    """
    s = np.asarray(skill, dtype=float)
    d = np.asarray(delta_j, dtype=float)
    helped = d > 0
    fig, ax = plt.subplots(figsize=(8.2, 5.4), facecolor=TOKENS["surface"])
    ax.axhline(0.0, color=TOKENS["axis"], linewidth=1.2, zorder=2)
    ax.scatter(s[helped], d[helped], s=46, color=SERIES[0], zorder=4,
               edgecolor=TOKENS["surface"], linewidth=0.8, label="forecast improved the decision")
    ax.scatter(s[~helped], d[~helped], s=46, color=SERIES[1], zorder=4,
               edgecolor=TOKENS["surface"], linewidth=0.8, label="forecast did not")
    if annotations:
        for x0, y0, text in annotations:
            dy = 26 if y0 > 0 else -26
            ax.annotate(text, xy=(x0, y0), xytext=(10, dy), textcoords="offset points",
                        fontsize=9.5, color=TOKENS["text_primary"], ha="left",
                        va="bottom" if y0 > 0 else "top",
                        arrowprops=dict(arrowstyle="-", color=TOKENS["text_secondary"],
                                        linewidth=0.9, shrinkA=0, shrinkB=4))
    span = float(np.nanmax(d) - np.nanmin(d)) or 1.0
    ax.set_ylim(float(np.nanmin(d)) - 0.22 * span, float(np.nanmax(d)) + 0.22 * span)
    apply_axes_style(
        ax, "Forecast skill does not order decision value",
        "each point is one degradation setting, averaged over the same paired worlds",
        xlabel=skill_label, ylabel="mean $\\Delta J$ (hours of equivalent delay)")
    leg = ax.legend(loc="best", frameon=True, fontsize=9, facecolor=TOKENS["surface"],
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
