"""The six conceptual properties the v0.1 freeze must keep demonstrating.

These are **correctness tests for the argument**, not for the code. Each one
names a phenomenon the repository claims to exhibit; if a change makes one
false, the repository has stopped demonstrating what it says it does.

They are deliberately written against the public API at a level a reader can
check, and they state the phenomenon in the test name.

Everything here is CONSTRUCTED_BENCHMARK (``docs/CURRENT_RESULT_STATUS.md``).
Passing these tests says the phenomena are *possible* and *constructible*. It
says nothing about how often they occur in reality.
"""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.decision_value.value import (
    default_policies,
    evaluate_world,
    run_paired_study,
)
from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.frontiers.estimate import monotonicity_report
from wildfireguardian_forecast_value.frontiers.grid import SweepAxis, sweep_grid
from wildfireguardian_forecast_value.statistics.equivalence import tost
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import (
    case_specs,
    default_scenario,
)

PIPE = standard_pipeline(p_miss=0.0)
N_WORLDS = 120
SEED = 11


def _mean_over_worlds(scenario, params, latency, n=N_WORLDS, seed=SEED, policies=None):
    rs = run_paired_study(scenario, n, seed, PIPE, fixed_params=params,
                          latency=latency, policies=policies)
    return (
        float(np.mean([r.delta_j for r in rs])),
        float(np.mean([r.skill["csi"] for r in rs])),
        np.array([r.delta_j for r in rs], dtype=float),
    )


# --------------------------------------------------------------- property 1 --
def test_p1_similar_skill_materially_different_decision_value():
    """Two forecasts of near-identical conventional skill, materially different value.

    Equal and opposite heading errors land within about one CSI point of each
    other, because the constructed geometry makes the two rotations cover
    similar numbers of cells. Their downstream losses are nowhere near each
    other: one captures essentially all the available decision value and the
    other captures almost none.
    """
    scenario = default_scenario()
    lat = LatencySpec(0.6, 0.0)
    plus, csi_plus, _ = _mean_over_worlds(scenario, {"eps_theta": float(np.deg2rad(+15))}, lat)
    minus, csi_minus, _ = _mean_over_worlds(scenario, {"eps_theta": float(np.deg2rad(-15))}, lat)

    assert abs(csi_plus - csi_minus) < 0.02, (
        f"the two settings no longer have similar skill (CSI {csi_plus:.4f} vs "
        f"{csi_minus:.4f}); the property needs a new pair"
    )
    assert plus - minus > 10.0, (
        f"the decision values are no longer materially different: "
        f"{plus:+.3f} vs {minus:+.3f} h"
    )
    assert plus > 5.0 * minus > 0.0, (
        "expected a several-fold difference in decision value at matched skill"
    )


def test_p1b_similar_skill_can_even_reverse_the_sign_of_decision_value():
    """The stronger form: matched skill, opposite signs.

    A slightly wider skill tolerance (a few CSI points) buys a pair whose
    decision values have opposite signs -- one forecast helps, the other harms.
    """
    scenario = default_scenario()
    lat = LatencySpec(0.6, 0.0)
    plus, csi_plus, _ = _mean_over_worlds(scenario, {"eps_theta": float(np.deg2rad(+18))}, lat)
    minus, csi_minus, _ = _mean_over_worlds(scenario, {"eps_theta": float(np.deg2rad(-18))}, lat)

    assert abs(csi_plus - csi_minus) < 0.05, (
        f"CSI {csi_plus:.4f} vs {csi_minus:.4f} are no longer comparable"
    )
    assert plus > 0 > minus, (
        f"expected opposite signs at comparable skill, got {plus:+.3f} and {minus:+.3f}"
    )


# --------------------------------------------------------------- property 2 --
def test_p2_accurate_but_late_has_zero_decision_value():
    """High conventional skill, no decision value, because it is not there in time."""
    scenario = default_scenario()
    arm = case_specs()["case_4"].arms[0]
    assert arm.label == "accurate_late"
    r = evaluate_world(scenario, case_specs()["case_4"].world(arm, scenario), PIPE,
                       arm.degradation_params, LatencySpec(arm.information_time, arm.latency))
    assert r.skill["csi"] == pytest.approx(1.0)
    assert r.skill["arrival_rmse"] == pytest.approx(0.0)
    assert not r.forecast_available
    assert r.delta_j == 0.0, "an absent forecast is worth zero, never negative"
    assert r.forecast_action == r.baseline_action
    assert r.future_oracle_value > 0.0, "the world must be one where information could help"


# --------------------------------------------------------------- property 3 --
def test_p3_crude_but_timely_supports_the_useful_action():
    """Lower conventional skill, useful downstream action."""
    scenario = default_scenario()
    late, timely = case_specs()["case_4"].arms
    r_late = evaluate_world(scenario, case_specs()["case_4"].world(late, scenario), PIPE,
                            late.degradation_params,
                            LatencySpec(late.information_time, late.latency))
    r_timely = evaluate_world(scenario, case_specs()["case_4"].world(timely, scenario), PIPE,
                              timely.degradation_params,
                              LatencySpec(timely.information_time, timely.latency))
    assert r_timely.skill["csi"] < r_late.skill["csi"] - 0.3, "the crude arm is no longer crude"
    assert r_timely.delta_j > 0 and r_timely.value_fraction == pytest.approx(1.0)
    assert r_timely.delta_j > r_late.delta_j


# --------------------------------------------------------------- property 4 --
def test_p4_forecast_aware_policy_can_be_worse_than_a_strong_baseline():
    """Forecast harm: the forecast-aware policy loses to the forecast-free trigger."""
    scenario = default_scenario()
    arm = case_specs()["case_2"].arms[1]
    assert "fast_world" in arm.label
    r = evaluate_world(scenario, case_specs()["case_2"].world(arm, scenario), PIPE,
                       arm.degradation_params, LatencySpec(arm.information_time, arm.latency))
    assert r.baseline_action != r.forecast_action
    assert r.delta_j < -10.0, "the forecast is no longer strictly harmful here"
    assert r.future_oracle_value == pytest.approx(0.0), (
        "this property needs a world where the baseline was already optimal, so that "
        "the loss is attributable to the forecast rather than to the world"
    )


def test_p4_harm_also_appears_across_a_population_of_worlds():
    """Not a single cherry-picked world: a whole sweep column is net-harmful."""
    scenario = default_scenario()
    mean, _, deltas = _mean_over_worlds(
        scenario, {"eps_theta": float(np.deg2rad(-25))}, LatencySpec(0.6, 0.0))
    assert mean < 0, f"expected net harm across worlds, got {mean:+.3f}"
    assert np.mean(deltas < 0) > 0.2, "harm should appear in a substantial minority of worlds"


# --------------------------------------------------------------- property 5 --
def test_p5_baseline_match_forecast_adds_no_meaningful_benefit():
    """A strong baseline the forecast cannot improve on, declared by equivalence.

    With a trigger radius large enough that the baseline always takes the robust
    route, the forecast agrees almost everywhere and the paired difference is
    statistically equivalent to zero at a stated margin. "No significant
    difference" would not be enough -- equivalence has to be shown, with a
    margin, which is the whole point of ``statistics.equivalence``.
    """
    # A world distribution in which the protective action is never in doubt:
    # the fire is fast enough that the observed burn is always inside the
    # trigger radius, so the forecast-free baseline already takes the robust
    # route in every world.
    scenario = default_scenario(nominal_rate=8.0, rate_sd_log=0.05)
    mean, _, deltas = _mean_over_worlds(scenario, {}, LatencySpec(0.6, 0.0))

    margin = 1.0  # hour of equivalent delay; a policy input, never a default
    result = tost(deltas, margin=margin, n_boot=800, seed=0)
    assert result.is_equivalent, (
        f"expected the forecast to add no meaningful benefit over an always-robust "
        f"baseline; TOST at margin +-{margin} h gave {result.decision} with CI "
        f"[{result.ci_low:+.3f}, {result.ci_high:+.3f}]"
    )
    assert result.margin == margin, "the margin must travel with the claim"
    assert mean == pytest.approx(0.0, abs=1e-9)
    assert np.all(deltas == 0.0), (
        "this construction is meant to be exactly null; a non-zero world means the "
        "trigger is no longer always correct here and the property needs re-siting"
    )


# --------------------------------------------------------------- property 6 --
@pytest.mark.slow
def test_p6_frontier_can_be_multi_valued_where_constructed():
    """More than one zero crossing in a column, where the construction produces it.

    Mirrors ``experiments/manifests/frontier_short_wait.yaml``. This is the
    property that forbids bisecting for "the" break-even point (F-10).
    """
    scenario = default_scenario()
    x = SweepAxis("eps_theta", tuple(np.deg2rad([-18.0, -15.0, -11.0, -4.0, 8.0])))
    y = SweepAxis("latency", tuple(np.linspace(0.0, 1.3, 9)), kind="latency")
    grid = sweep_grid(scenario, x, y, n_worlds=40, seed=SEED, pipeline=PIPE,
                      base_latency=LatencySpec(0.6, 0.0),
                      policies=default_policies(scenario, max_wait=0.8), skill_keys=())
    report = monotonicity_report(grid)
    assert report["n_columns_multi_crossing"] > 0
    assert not report["frontier_is_a_function_of_x"]


def test_all_six_properties_are_present_in_this_module():
    """A structural check: the freeze requires all six, by name."""
    import test_conceptual_properties as mod

    names = [n for n in dir(mod) if n.startswith("test_p")]
    # Each property may have more than one test (p1/p1b, p4 twice); the freeze
    # requires that all six families are present.
    families = sorted({n.split("_")[1].rstrip("abcdef") for n in names})
    assert families == ["p1", "p2", "p3", "p4", "p5", "p6"], (
        f"the v0.1 freeze requires six named conceptual properties; found {families}"
    )
