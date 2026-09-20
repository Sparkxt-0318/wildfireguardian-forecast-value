"""The four information classes, and the distinction they exist to enforce."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.decision_value.value import evaluate_world
from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.degradation.latency import LatencySpec, make_release
from wildfireguardian_forecast_value.fields.front import FireState
from wildfireguardian_forecast_value.forecast_classes import (
    FORECAST_CLASS_DESCRIPTIONS,
    ForecastClass,
    classify_release,
)
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import (
    CASES,
    case_specs,
    default_scenario,
)


class TestTaxonomy:
    def test_all_four_classes_exist_with_stable_string_values(self):
        assert {c.value for c in ForecastClass} == {
            "PRESENT_STATE_ORACLE", "CONDITIONAL_FORECAST",
            "DEGRADED_FORECAST", "FUTURE_ORACLE",
        }

    def test_every_class_is_described(self):
        for c in ForecastClass:
            assert len(FORECAST_CLASS_DESCRIPTIONS[c.value]) > 60

    def test_str_is_the_stable_value(self):
        assert str(ForecastClass.FUTURE_ORACLE) == "FUTURE_ORACLE"


class TestClassification:
    def test_undegraded_conditional_release_is_a_present_state_oracle(self, two_source_state):
        r = make_release(two_source_state, information_time=0.5, latency=0.0)
        assert classify_release(r, two_source_state) is ForecastClass.PRESENT_STATE_ORACLE

    def test_degraded_release_is_a_degraded_forecast(self, two_source_state):
        pipe = standard_pipeline(p_miss=0.0)
        r = make_release(two_source_state, 0.5, 0.0, pipe, {"eps_theta": 0.3})
        assert classify_release(r, two_source_state) is ForecastClass.DEGRADED_FORECAST

    def test_identity_parameters_do_not_make_a_degraded_forecast(self, two_source_state):
        """`{"eps_theta": 0.0}` is not a degradation."""
        pipe = standard_pipeline(p_miss=0.0)
        r = make_release(two_source_state, 0.5, 0.0, pipe, {"eps_theta": 0.0})
        assert classify_release(r, two_source_state) is ForecastClass.PRESENT_STATE_ORACLE

    def test_a_release_carrying_a_future_ignition_is_a_future_oracle(self, two_source_state):
        r = make_release(two_source_state, 0.5, 0.0,
                         enforce_conditional_on_information_time=False)
        assert classify_release(r) is ForecastClass.FUTURE_ORACLE

    def test_without_a_truth_reference_an_undegraded_release_is_conditional(
            self, two_source_state):
        r = make_release(two_source_state, 0.5, 0.0)
        assert classify_release(r) is ForecastClass.CONDITIONAL_FORECAST


class TestTheDistinctionThatMatters:
    def test_a_present_state_oracle_is_not_a_future_oracle(self):
        """The reason 'perfect forecast' was removed from this repository.

        An error-free estimate of the present, issued at the decision time,
        still cannot contain a spot ignition that has not happened. It
        therefore does not achieve the future-oracle loss in worlds that have
        one.
        """
        scenario = default_scenario()
        pipe = standard_pipeline(p_miss=0.0)
        differed = 0
        checked = 0
        for i in range(60):
            w = scenario.sample_world(i, 4)
            if not w.params.get("has_spot"):
                continue
            checked += 1
            r = evaluate_world(scenario, w, pipe, {},
                               LatencySpec(scenario.decision_time, 0.0))
            assert r.forecast_class == "PRESENT_STATE_ORACLE"
            assert r.delta_j <= r.future_oracle_value + 1e-9
            differed += int(r.forecast_action != r.future_oracle_action)
        assert checked > 0
        assert differed > 0, (
            "no world showed the gap; without it, 'present-state oracle' and "
            "'future oracle' would be the same object and the taxonomy would be idle"
        )

    def test_the_gap_closes_when_nothing_is_unknowable(self):
        scenario = default_scenario(spot=None)
        pipe = standard_pipeline(p_miss=0.0)
        for i in range(15):
            w = scenario.sample_world(i, 4)
            r = evaluate_world(scenario, w, pipe, {},
                               LatencySpec(scenario.decision_time, 0.0))
            assert r.forecast_action == r.future_oracle_action
            assert r.delta_j == pytest.approx(r.future_oracle_value)


class TestBenchmarkArmsAreLabelled:
    def test_every_arm_declares_a_valid_class(self):
        valid = {c.value for c in ForecastClass}
        for key in CASES:
            for arm in case_specs()[key].arms:
                assert arm.forecast_class in valid, f"{key}/{arm.label}"

    def test_no_arm_is_a_future_oracle(self):
        for key in CASES:
            for arm in case_specs()[key].arms:
                assert arm.forecast_class != "FUTURE_ORACLE"

    def test_declared_class_matches_what_evaluation_computes(self):
        scenario = default_scenario()
        pipe = standard_pipeline(p_miss=0.0)
        for key in CASES:
            case = case_specs()[key]
            for arm in case.arms:
                r = evaluate_world(case.scenario(scenario), case.world(arm, scenario),
                                   pipe, arm.degradation_params,
                                   LatencySpec(arm.information_time, arm.latency))
                assert r.forecast_class == arm.forecast_class, f"{key}/{arm.label}"


class TestDeprecatedAliases:
    def test_policy_alias_still_resolves(self):
        from wildfireguardian_forecast_value.synthetic_decisions.policies import (
            ClairvoyantPolicy,
            FutureOraclePolicy,
        )
        assert ClairvoyantPolicy is FutureOraclePolicy

    def test_invariant_alias_still_resolves(self):
        from wildfireguardian_forecast_value.validation.invariants import (
            check_conditional_on_information_time,
            check_no_clairvoyance,
        )
        assert check_no_clairvoyance is check_conditional_on_information_time

    def test_result_field_aliases(self):
        scenario = default_scenario()
        r = evaluate_world(scenario, scenario.sample_world(0, 1),
                           standard_pipeline(p_miss=0.0), {}, LatencySpec(0.6, 0.0))
        assert r.vpi == r.future_oracle_value
        assert r.clairvoyant_action == r.future_oracle_action
