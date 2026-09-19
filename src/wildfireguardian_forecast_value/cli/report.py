"""Turning results into the summary a reader should actually see.

Every summary this module produces leads with the effect size and its
interval, reports the clustering diagnostics next to them, and states the loss
ratio the numbers are conditional on.  A ``p`` value appears only alongside
those, never alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from wildfireguardian_forecast_value.statistics.bootstrap import bootstrap_ci
from wildfireguardian_forecast_value.statistics.effect_size import effect_sizes, value_fraction_summary
from wildfireguardian_forecast_value.statistics.equivalence import non_inferiority, tost
from wildfireguardian_forecast_value.statistics.paired import clustering_diagnostics, paired_summary

__all__ = ["summarise_study", "format_study_summary", "write_json"]


def summarise_study(results, loss, n_boot: int = 2000, confidence: float = 0.95,
                    equivalence_margin: float = 2.0, seed: int = 0) -> dict:
    """Full world-level summary of a list of :class:`WorldResult`."""
    delta = np.array([r.delta_j for r in results], dtype=float)
    frac = np.array([r.value_fraction for r in results], dtype=float)
    changed = np.array([r.action_changed for r in results], dtype=bool)
    avail = np.array([r.forecast_available for r in results], dtype=bool)

    receptor_vals = np.concatenate([r.receptor_delta for r in results])
    world_ids = np.concatenate([np.full(r.receptor_delta.size, r.world_id) for r in results])

    out: dict = {
        "n_worlds": len(results),
        "n_receptors_total": int(receptor_vals.size),
        "unit_of_analysis": "world",
        "loss": loss.to_dict(),
        "paired_summary": paired_summary(delta, confidence).as_dict(),
        "bootstrap": bootstrap_ci(delta, np.mean, n_boot=n_boot,
                                  confidence=confidence, seed=seed).as_dict(),
        "effect_sizes": effect_sizes(delta, changed, n_boot=n_boot,
                                     confidence=confidence, seed=seed).as_dict(),
        "value_fraction": value_fraction_summary(frac, n_boot=n_boot,
                                                 confidence=confidence, seed=seed),
        "fraction_worlds_forecast_available": float(avail.mean()),
        "fraction_worlds_action_changed": float(changed.mean()),
    }
    if receptor_vals.size and len(results) > 1:
        out["clustering"] = clustering_diagnostics(receptor_vals, world_ids).as_dict()
    if len(results) > 1:
        out["equivalence"] = tost(delta, margin=equivalence_margin, method="bootstrap",
                                  n_boot=n_boot, seed=seed).as_dict()
        out["non_inferiority"] = non_inferiority(delta, margin=equivalence_margin,
                                                 method="bootstrap", n_boot=n_boot,
                                                 seed=seed).as_dict()
    return out


def format_study_summary(s: dict) -> str:
    """Human-readable block, ordered so the effect comes before the p value."""
    ps, bs, es = s["paired_summary"], s["bootstrap"], s["effect_sizes"]
    vf = s["value_fraction"]
    lines = [
        f"  worlds                     {s['n_worlds']}   (receptors: {s['n_receptors_total']};"
        f" the unit of analysis is the WORLD)",
        f"  mean Delta J               {ps['mean']:+.3f} h",
        f"    bootstrap {bs['confidence']:.0%} CI       [{bs['ci_low']:+.3f}, {bs['ci_high']:+.3f}]"
        f"   ({bs['method']}, {bs['n_boot']} world resamples)",
        f"    Student-t {ps['confidence']:.0%} CI       [{ps['ci_low']:+.3f}, {ps['ci_high']:+.3f}]",
        f"  P(forecast better)         {es['probability_of_superiority']:.3f}"
        f"   [{es['pos_ci_low']:.3f}, {es['pos_ci_high']:.3f}]   (ties split, never dropped)",
        f"  Cohen's d_z / Hedges' g    {es['cohens_dz']:.3f} / {es['hedges_g']:.3f}",
        f"  worlds where action changed{s['fraction_worlds_action_changed']:>8.1%}",
        f"  worlds where forecast was available {s['fraction_worlds_forecast_available']:.1%}",
        f"  mean fraction of VPI realised  "
        f"{vf.get('mean_value_fraction', float('nan')):.3f}"
        f"   [{vf.get('ci_low', float('nan')):.3f}, {vf.get('ci_high', float('nan')):.3f}]"
        f"   (on {vf['n_worlds_with_positive_vpi']}/{vf['n_worlds']} worlds where perfect"
        f" information was worth anything)",
        f"  two-sided p (t)            {ps['p_value']:.3g}"
        "   <- reported last and on purpose: with synthetic worlds this measures the"
        " compute budget, not the forecast",
    ]
    if "clustering" in s:
        c = s["clustering"]
        lines += [
            "",
            "  clustering diagnostics (why the world is the unit):",
            f"    ICC {c['icc']:.4f}   design effect {c['design_effect']:.2f}"
            f"   effective n {c['effective_sample_size']:.1f} of {c['n_receptors_total']} receptors",
            f"    a naive receptor-level SE would be {c['se_understatement_factor']:.2f}x too small"
            f"  ({c['naive_se']:.4f} vs {c['correct_se']:.4f})",
        ]
    if "equivalence" in s:
        eq, ni = s["equivalence"], s["non_inferiority"]
        lines += [
            "",
            f"  equivalence at margin +-{eq['margin']:g} h: {eq['decision'].upper()}"
            f"   (CI [{eq['ci_low']:+.3f}, {eq['ci_high']:+.3f}] at {eq['ci_level']:.0%})",
            f"  non-inferiority at margin {ni['margin']:g} h: {ni['decision'].upper()}",
            "    'not_shown' is not evidence of a difference; it means this many worlds"
            " could not resolve one.",
        ]
    lines += [
        "",
        f"  every number above is conditional on the loss ratio "
        f"L/c_t = {s['loss'].get('loss_ratio', float('nan')):g}",
    ]
    return "\n".join(lines)


def write_json(obj: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=_default)
    return path


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)
