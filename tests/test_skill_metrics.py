"""Skill metrics, with attention to the ways they can be gamed or misread."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.skill_metrics.categorical import (
    brier_score,
    brier_skill_score,
    categorical_scores,
    contingency_table,
    ensemble_burn_probability,
)
from wildfireguardian_forecast_value.skill_metrics.continuous import (
    angular_error,
    arrival_time_metrics,
    circular_mae,
    rate_metrics,
)


class TestArrivalTime:
    def test_perfect_forecast(self):
        m = arrival_time_metrics([1.0, 2.0], [1.0, 2.0])
        assert (m.mae, m.rmse, m.bias) == (0.0, 0.0, 0.0)
        assert m.coverage == 1.0

    def test_infinities_are_counted_not_averaged(self):
        m = arrival_time_metrics([1.0, np.inf], [1.0, 5.0])
        assert m.n_both == 1 and m.n_false == 1
        assert np.isfinite(m.mae)

    def test_no_overlap_gives_nan_not_zero(self):
        m = arrival_time_metrics([np.inf, 1.0], [1.0, np.inf])
        assert np.isnan(m.mae) and m.n_both == 0

    def test_positive_bias_means_late(self):
        assert arrival_time_metrics([1.0], [1.5]).bias == pytest.approx(0.5)

    def test_rmse_is_gameable_by_predicting_never(self):
        """The documented failure mode: dropping hard points improves RMSE."""
        truth = [1.0, 2.0, 3.0]
        honest = [1.0, 2.0, 9.0]          # badly wrong on the third point
        evasive = [1.0, 2.0, np.inf]      # says 'never' instead
        assert arrival_time_metrics(truth, evasive).rmse < arrival_time_metrics(truth, honest).rmse
        # ...but the miss count exposes it.
        assert arrival_time_metrics(truth, evasive).n_miss == 1
        assert arrival_time_metrics(truth, honest).n_miss == 0

    def test_horizon_censors_both_fields(self):
        m = arrival_time_metrics([1.0, 5.0], [1.0, 6.0], horizon=2.0)
        assert m.n_both == 1 and m.n_neither == 1

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            arrival_time_metrics([1.0], [1.0, 2.0])


class TestAngularAndRate:
    def test_angular_error_wraps(self):
        assert circular_mae(np.deg2rad(179), np.deg2rad(-179)) == pytest.approx(
            np.deg2rad(2.0), abs=1e-9)

    def test_angular_error_is_signed(self):
        assert angular_error(0.2, 0.1) == pytest.approx(0.1)
        assert angular_error(0.1, 0.2) == pytest.approx(-0.1)

    def test_rate_metrics_report_both_coordinates(self):
        m = rate_metrics([4.0], [2.0])
        assert m["mean_relative_error"] == pytest.approx(1.0)
        assert m["mean_log_ratio"] == pytest.approx(np.log(2.0))

    def test_log_ratio_is_symmetric_where_relative_error_is_not(self):
        up, down = rate_metrics([4.0], [2.0]), rate_metrics([1.0], [2.0])
        assert up["mean_relative_error"] != pytest.approx(-down["mean_relative_error"])
        assert up["mean_log_ratio"] == pytest.approx(-down["mean_log_ratio"])

    def test_non_positive_rates_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            rate_metrics([0.0], [2.0])


class TestCategorical:
    def test_table(self):
        t = contingency_table([1, 1, 0, 0], [1, 0, 1, 0])
        assert (t.hits, t.false_alarms, t.misses, t.correct_negatives) == (1, 1, 1, 1)
        assert t.n == 4

    def test_perfect_forecast(self):
        s = categorical_scores([1, 0, 1], [1, 0, 1])
        assert s["csi"] == 1.0 and s["far"] == 0.0 and s["pod"] == 1.0

    def test_undefined_ratios_are_nan_not_zero(self):
        s = categorical_scores([1, 1], [0, 0])       # never forecast burned
        assert np.isnan(s["far"])
        assert s["pod"] == 0.0

    def test_csi_ignores_correct_negatives(self):
        """CSI is chosen over accuracy precisely because it does not use d."""
        small = categorical_scores([1, 1, 0], [1, 0, 0])
        padded = categorical_scores([1, 1] + [0] * 100, [1, 0] + [0] * 100)
        assert small["csi"] == pytest.approx(padded["csi"])
        assert small["accuracy"] != pytest.approx(padded["accuracy"])

    def test_brier(self):
        assert brier_score([1.0, 0.0], [1, 0]) == 0.0
        assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)

    def test_brier_rejects_out_of_range_probabilities(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            brier_score([1.5], [1])

    def test_brier_skill_against_base_rate(self):
        assert brier_skill_score([1.0, 0.0, 1.0], [1, 0, 1]) == pytest.approx(1.0)

    def test_brier_skill_is_nan_for_a_degenerate_outcome(self):
        assert np.isnan(brier_skill_score([0.3, 0.3], [1, 1]))

    def test_ensemble_probability(self, wedge, two_source_state):
        from wildfireguardian_forecast_value.fields.front import FireState
        states = [FireState((wedge,)), two_source_state]
        p = ensemble_burn_probability(states, [[6.0, 0.0]], time=1.5)
        assert p[0] == pytest.approx(0.5)

    def test_ensemble_needs_members(self):
        with pytest.raises(ValueError, match="at least one"):
            ensemble_burn_probability([], [[0, 0]], 1.0)
