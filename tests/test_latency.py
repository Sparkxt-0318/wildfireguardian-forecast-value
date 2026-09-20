"""Latency semantics: availability, staleness, and the no-clairvoyance rule."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.degradation.latency import (
    ForecastRelease,
    ForecastStream,
    LatencySpec,
    issue_times,
    make_release,
)
from wildfireguardian_forecast_value.fields.front import FireState
from wildfireguardian_forecast_value.forecast_classes import ForecastClass, classify_release
from wildfireguardian_forecast_value.validation.invariants import (
    InvariantError,
    check_conditional_on_information_time,
    check_latency_semantics,
)


class TestRelease:
    def test_availability_is_information_time_plus_latency(self, two_source_state):
        r = ForecastRelease(two_source_state, 0.5, 0.4)
        assert r.availability_time == pytest.approx(0.9)

    def test_availability_is_inclusive_at_the_boundary(self, two_source_state):
        r = ForecastRelease(two_source_state, 0.5, 0.4)
        assert not r.is_available_at(0.9 - 1e-9)
        assert r.is_available_at(0.9)

    def test_negative_latency_rejected(self, two_source_state):
        with pytest.raises(ValueError, match="negative latency"):
            ForecastRelease(two_source_state, 0.5, -0.1)

    def test_zero_latency_is_legal(self, two_source_state):
        assert ForecastRelease(two_source_state, 1.0, 0.0).is_available_at(1.0)

    def test_age_exceeds_latency_when_used_later(self, two_source_state):
        r = ForecastRelease(two_source_state, 0.5, 0.2)
        assert r.age_at(1.0) == pytest.approx(0.5)
        assert r.age_at(1.0) > r.latency
        check_latency_semantics(r, 1.0)

    def test_staleness_and_latency_are_different_numbers(self, two_source_state):
        """A fast product from old data can be staler than a slow one from new data."""
        fast_but_stale = ForecastRelease(two_source_state, 0.2, 0.05, "fast")
        slow_but_fresh = ForecastRelease(two_source_state, 0.8, 0.15, "slow")
        assert fast_but_stale.latency < slow_but_fresh.latency
        assert fast_but_stale.age_at(1.0) > slow_but_fresh.age_at(1.0)


class TestStream:
    def test_empty_stream_offers_nothing(self):
        assert ForecastStream(()).available_at(10.0) is None

    def test_picks_the_most_informative_available_release(self, two_source_state):
        fast_stale = ForecastRelease(two_source_state, 0.2, 0.05, "fast")
        slow_fresh = ForecastRelease(two_source_state, 0.8, 0.15, "slow")
        stream = ForecastStream((fast_stale, slow_fresh))
        # Before the fresh one lands, only the stale one exists.
        assert stream.available_at(0.5).label == "fast"
        # Once both are available the fresher information wins, not the earlier arrival.
        assert stream.available_at(1.0).label == "slow"

    def test_nothing_available_before_the_first_arrival(self, two_source_state):
        stream = ForecastStream((ForecastRelease(two_source_state, 0.6, 0.3),))
        assert stream.available_at(0.89) is None

    def test_issue_times_are_regular(self):
        assert issue_times(0.0, 0.25, 4) == [0.0, 0.25, 0.5, 0.75]
        with pytest.raises(ValueError):
            issue_times(0.0, 0.0, 3)


class TestConditionalOnInformationTime:
    def test_make_release_drops_unknowable_sources(self, two_source_state):
        r = make_release(two_source_state, information_time=0.5, latency=0.1)
        assert r.state.labels == ("main",)
        check_conditional_on_information_time(r)

    def test_restriction_happens_before_degradation(self, two_source_state):
        """Order matters: restrict, then degrade -- never the other way round."""
        pipe = standard_pipeline(p_miss=0.0)
        r = make_release(two_source_state, 0.5, 0.0, pipe, {"spot_delay": 0.0})
        assert "spot1" not in r.state.labels

    def test_a_hand_built_future_oracle_release_is_caught(self, two_source_state):
        bad = ForecastRelease(two_source_state, information_time=0.5, latency=0.0)
        assert classify_release(bad) is ForecastClass.FUTURE_ORACLE
        with pytest.raises(InvariantError, match="FUTURE_ORACLE"):
            check_conditional_on_information_time(bad)

    def test_opting_out_is_possible_but_explicit(self, two_source_state):
        """The escape hatch exists so the invariant itself can be tested."""
        r = make_release(two_source_state, 0.5, 0.0,
                         enforce_conditional_on_information_time=False)
        assert "spot1" in r.state.labels
        assert classify_release(r) is ForecastClass.FUTURE_ORACLE
        with pytest.raises(InvariantError):
            check_conditional_on_information_time(r)

    def test_a_conditional_release_is_classified_as_a_present_state_oracle(
            self, two_source_state):
        r = make_release(two_source_state, information_time=0.5, latency=0.1)
        assert classify_release(r, two_source_state) is ForecastClass.PRESENT_STATE_ORACLE


class TestLatencySpec:
    def test_builds_a_release(self, two_source_state):
        spec = LatencySpec(0.7, 0.2)
        r = spec.release(two_source_state, "x")
        assert (r.information_time, r.latency, r.label) == (0.7, 0.2, "x")
        assert spec.to_dict() == {"information_time": 0.7, "latency": 0.2}
