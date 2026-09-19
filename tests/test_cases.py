"""The four cases, asserted as *claims* rather than as implementation details.

If one of these fails, the repository's prose has stopped being true and the
docs must change with the code.  That is the point of testing the claim rather
than the code path.
"""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.decision_value.value import evaluate_world
from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import (
    CASES,
    case_specs,
    default_scenario,
)

PIPE = standard_pipeline(p_miss=0.0)


def _run(key, arm, base=None):
    """Evaluate one arm.

    The case is passed by key rather than looked up from the arm: a CaseArm
    whose expected value fraction is ``nan`` never compares equal to itself,
    so identity-by-equality is not available here.
    """
    spec_scenario = default_scenario() if base is None else base
    case = case_specs()[key]
    sc = case.scenario(spec_scenario)
    return evaluate_world(sc, case.world(arm, spec_scenario), PIPE, arm.degradation_params,
                          LatencySpec(arm.information_time, arm.latency))


ARMS = [(key, arm) for key in CASES for arm in case_specs()[key].arms]


@pytest.mark.parametrize("key,arm", ARMS, ids=[f"{k}:{a.label}" for k, a in ARMS])
def test_arm_behaves_as_documented(key, arm):
    r = _run(key, arm)
    assert r.baseline_action == arm.expected_baseline_action
    assert r.forecast_action == arm.expected_forecast_action
    assert int(np.sign(round(r.delta_j, 9))) == arm.expected_delta_sign
    if np.isnan(arm.expected_value_fraction):
        assert np.isnan(r.value_fraction)
    else:
        assert r.value_fraction == pytest.approx(arm.expected_value_fraction)


def test_case_1_skill_falls_while_value_is_untouched():
    perfect, degraded = case_specs()["case_1"].arms
    rp, rd = _run("case_1", perfect), _run("case_1", degraded)
    assert rd.skill["csi"] < rp.skill["csi"] - 0.3          # much worse footprint skill
    assert rd.skill["far"] > rp.skill["far"] + 0.2          # many more false alarms
    assert rd.skill["arrival_rmse"] == pytest.approx(0.0)   # RMSE cannot see it at all
    assert rd.delta_j == pytest.approx(rp.delta_j)          # identical decision value


def test_case_2_small_error_flips_the_decision_and_destroys_the_value():
    nominal, fast = case_specs()["case_2"].arms
    rn, rf = _run("case_2", nominal), _run("case_2", fast)
    perfect = _run("case_1", case_specs()["case_1"].arms[0])
    assert rn.forecast_action != perfect.forecast_action   # the decision flipped
    assert perfect.value_fraction == pytest.approx(1.0)
    assert rn.value_fraction == pytest.approx(0.0)          # all of it lost
    assert rf.delta_j < -10.0                               # and in the fast world, harmful


def test_case_2_scores_better_than_case_1_yet_decides_worse():
    """The headline inversion, at the level of a single pair of forecasts."""
    c1 = _run("case_1", case_specs()["case_1"].arms[1])
    c2 = _run("case_2", case_specs()["case_2"].arms[0])
    assert abs(c2.params.get("heading", 0.0) - c1.params.get("heading", 0.0)) < 1e-12
    assert c2.skill["csi"] > c1.skill["csi"]                # better CSI
    assert c2.skill["far"] < c1.skill["far"]                # better false-alarm ratio
    assert c2.value_fraction < c1.value_fraction            # worse decisions
    assert c2.value_fraction == 0.0 and c1.value_fraction == 1.0


def test_case_3_worst_skill_still_full_value():
    r3 = _run("case_3", case_specs()["case_3"].arms[0])
    others = [_run(k, a) for k in ("case_1", "case_2", "case_4")
              for a in case_specs()[k].arms if a.label != "perfect"]
    assert r3.skill["csi"] <= min(o.skill["csi"] for o in others) + 1e-12
    assert r3.value_fraction == pytest.approx(1.0)


def test_case_4_latency_beats_accuracy():
    late, timely = case_specs()["case_4"].arms
    rl, rt = _run("case_4", late), _run("case_4", timely)
    assert rl.skill["csi"] > rt.skill["csi"]                # the late one is far more accurate
    assert rl.skill["arrival_rmse"] == pytest.approx(0.0)
    assert not rl.forecast_available and rt.forecast_available
    assert rl.value_fraction == 0.0 and rt.value_fraction == pytest.approx(1.0)


def test_case_4_late_forecast_is_worth_zero_not_negative():
    """An absent forecast leaves the decision maker exactly as they were."""
    late = case_specs()["case_4"].arms[0]
    r = _run("case_4", late)
    assert r.delta_j == 0.0
    assert r.forecast_action == r.baseline_action


def test_skill_ranking_is_inverted_against_value():
    """Across the degraded forecasts, CSI orders decision value backwards.

    Concretely: every forecast that realises 100% of the available value scores
    *worse* on CSI than every forecast that realises 0%.
    """
    rows = [(a.label, _run(k, a)) for k in CASES for a in case_specs()[k].arms
            if a.label != "perfect"]
    good = [r.skill["csi"] for _, r in rows if r.value_fraction == 1.0]
    bad = [r.skill["csi"] for _, r in rows
           if np.isfinite(r.value_fraction) and r.value_fraction == 0.0]
    assert good and bad
    assert max(good) < min(bad), (
        "the inversion no longer holds; the README and docs/DECISION_VALUE.md "
        f"claim it does. good-value CSIs {sorted(good)}, zero-value CSIs {sorted(bad)}"
    )


def test_cases_are_deterministic():
    for key in CASES:
        for arm in case_specs()[key].arms:
            assert _run(key, arm).delta_j == _run(key, arm).delta_j


def test_every_case_has_a_claim_and_serialises():
    for key in CASES:
        c = case_specs()[key]
        assert len(c.claim) > 120, key
        assert c.arms, key
        d = c.to_dict()
        assert d["key"] == key and len(d["arms"]) == len(c.arms)
