"""Routes, policies, and the paired decision-value evaluation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from wildfireguardian_forecast_value.decision_value.loss import RouteChoiceLoss, loss_ratio_sweep
from wildfireguardian_forecast_value.decision_value.value import (
    default_policies,
    evaluate_world,
    results_to_frame,
    run_paired_study,
)
from wildfireguardian_forecast_value.degradation.latency import ForecastStream, LatencySpec
from wildfireguardian_forecast_value.fields.front import FireSource, FireState
from wildfireguardian_forecast_value.outcomes import Outcome
from wildfireguardian_forecast_value.synthetic_decisions.policies import (
    FutureOraclePolicy,
    FixedActionPolicy,
    ForecastPolicy,
    ProximityTriggerPolicy,
)
from wildfireguardian_forecast_value.synthetic_decisions.routes import Route, RouteSet, traverse_all
from wildfireguardian_forecast_value.validation.invariants import (
    InvariantError,
    check_baseline_is_forecast_free,
    check_no_oracle_access,
    check_pairing,
)


@pytest.fixture
def crossing_state():
    """Isotropic fire at (-5, 0) spreading at 5 km/h -- used by the margin tests."""
    return FireState((FireSource(origin=(-5.0, 0.0), ignition_time=0.0, spread_rate=5.0,
                                 heading=0.0, half_angle=np.pi),))


@pytest.fixture
def crossing_route():
    return Route("r", ((0.0, -5.0), (0.0, 5.0)), speed=10.0, sample_spacing=0.001)


class TestRoute:
    def test_length_and_travel_time(self):
        r = Route("r", ((0.0, 0.0), (3.0, 4.0)), speed=5.0)
        assert r.length == pytest.approx(5.0)
        assert r.travel_time == pytest.approx(1.0)

    def test_rejects_degenerate_geometry(self):
        with pytest.raises(ValueError, match="waypoints"):
            Route("r", ((0.0, 0.0),), speed=1.0)
        with pytest.raises(ValueError, match="speed"):
            Route("r", ((0.0, 0.0), (1.0, 1.0)), speed=0.0)

    def test_margins_are_vectorised_and_shift_uniformly(self, crossing_route, crossing_state):
        t0 = np.array([0.0, 0.5, 1.0])
        m = crossing_route.margins(crossing_state, t0)
        assert np.allclose(np.diff(m), -np.diff(t0), atol=1e-6)

    def test_overrun_ties_lose(self, crossing_route, crossing_state):
        base = crossing_route.margin(crossing_state, 0.0)
        # Depart exactly late enough for the margin to be zero.
        assert crossing_route.is_overrun(crossing_state, base)

    def test_unreachable_route_has_infinite_margin(self, wedge):
        st = FireState((wedge,))
        away = Route("away", ((0.0, 50.0), (10.0, 60.0)), speed=10.0)
        assert np.isinf(away.margin(st, 0.0))

    def test_finer_sampling_can_only_lower_the_margin(self, crossing_state):
        coarse = Route("r", ((0.0, -5.0), (0.0, 5.0)), speed=10.0, sample_spacing=1.0)
        fine = Route("r", ((0.0, -5.0), (0.0, 5.0)), speed=10.0, sample_spacing=0.001)
        assert fine.margin(crossing_state, 0.0) <= coarse.margin(crossing_state, 0.0) + 1e-12

    def test_route_set_requires_two_distinct_actions(self):
        a = Route("a", ((0.0, 0.0), (1.0, 0.0)), speed=1.0)
        with pytest.raises(ValueError, match="at least two"):
            RouteSet((a,))
        with pytest.raises(ValueError, match="unique"):
            RouteSet((a, a.__class__("a", ((0.0, 0.0), (2.0, 0.0)), speed=1.0)))

    def test_traverse_all_labels_receptors(self, crossing_route, crossing_state):
        outs = traverse_all(crossing_route, crossing_state, [0.0, 0.1, 0.2])
        assert [o.receptor_id for o in outs] == [0, 1, 2]


class TestLoss:
    def test_components(self):
        lm = RouteChoiceLoss(time_cost_per_hour=2.0, burnover_loss=40.0)
        assert lm.loss(Outcome("a", 1.5, False, 1.0)) == pytest.approx(3.0)
        assert lm.loss(Outcome("a", 1.5, True, -1.0)) == pytest.approx(43.0)

    def test_loss_ratio_is_the_only_free_parameter(self):
        """Scaling both weights scales J but changes no sign and no decision."""
        a = RouteChoiceLoss(1.0, 50.0)
        b = RouteChoiceLoss(3.0, 150.0)
        o1, o2 = Outcome("a", 1.0, False, 1.0), Outcome("a", 1.2, True, -1.0)
        assert a.loss_ratio == b.loss_ratio
        assert np.sign(a.loss(o1) - a.loss(o2)) == np.sign(b.loss(o1) - b.loss(o2))

    def test_near_miss_penalty_is_off_by_default(self):
        lm = RouteChoiceLoss()
        assert lm.loss(Outcome("a", 1.0, False, 0.001)) == lm.loss(Outcome("a", 1.0, False, 99.0))

    def test_near_miss_penalty_is_convex_when_enabled(self):
        lm = RouteChoiceLoss(near_miss_penalty=5.0, near_miss_margin=1.0)
        tight = lm.loss(Outcome("a", 1.0, False, 0.0))
        loose = lm.loss(Outcome("a", 1.0, False, 1.0))
        assert tight == pytest.approx(6.0) and loose == pytest.approx(1.0)

    def test_negative_weights_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            RouteChoiceLoss(burnover_loss=-1.0)

    def test_ratio_sweep(self):
        sweep = loss_ratio_sweep(RouteChoiceLoss(2.0, 100.0), [10, 20])
        assert [s.loss_ratio for s in sweep] == [10.0, 20.0]


class TestPolicies:
    def _ctx(self, scenario, world, stream=None, truth=False):
        return scenario.context(world, stream or ForecastStream(()), with_truth=truth)

    def test_fixed_action(self, scenario):
        w = scenario.sample_world(0, 1)
        assert FixedActionPolicy("route_b").decide(self._ctx(scenario, w)).action == "route_b"
        with pytest.raises(KeyError):
            FixedActionPolicy("route_z").decide(self._ctx(scenario, w))

    def test_trigger_fires_when_the_fire_is_close(self, scenario):
        w = scenario.sample_world(0, 1)
        near = ProximityTriggerPolicy("route_a", "route_b", trigger_distance=1e6)
        far = ProximityTriggerPolicy("route_a", "route_b", trigger_distance=0.0)
        assert near.decide(self._ctx(scenario, w)).action == "route_b"
        assert far.decide(self._ctx(scenario, w)).action == "route_a"

    def test_baseline_is_forecast_free(self, scenario, pipeline):
        from wildfireguardian_forecast_value.degradation.latency import make_release
        w = scenario.sample_world(0, 1)
        rel = make_release(w.truth, 0.6, 0.0, pipeline, {"eps_theta": 0.3})
        ctx = self._ctx(scenario, w, ForecastStream((rel,)), truth=True)
        check_baseline_is_forecast_free(ProximityTriggerPolicy("route_a", "route_b", 1.5), ctx)

    def test_a_forecast_using_policy_cannot_be_the_baseline(self, scenario):
        w = scenario.sample_world(0, 1)
        fp = ForecastPolicy(fallback=FixedActionPolicy("route_a"))
        with pytest.raises(InvariantError, match="forecast-using"):
            check_baseline_is_forecast_free(fp, self._ctx(scenario, w))

    def test_no_policy_reads_the_oracle(self, scenario, policies):
        w = scenario.sample_world(0, 1)
        ctx = self._ctx(scenario, w, truth=True)
        for p in policies[:2]:
            check_no_oracle_access(p, ctx)

    def test_clairvoyant_needs_the_oracle(self, scenario):
        w = scenario.sample_world(0, 1)
        with pytest.raises(ValueError, match="truth_state"):
            FutureOraclePolicy().decide(self._ctx(scenario, w, truth=False))

    def test_unavailable_forecast_falls_back_exactly(self, scenario, pipeline):
        from wildfireguardian_forecast_value.degradation.latency import make_release
        w = scenario.sample_world(0, 1)
        late = make_release(w.truth, 0.6, 5.0, pipeline, {})
        fallback = ProximityTriggerPolicy("route_a", "route_b", 1.5)
        fp = ForecastPolicy(fallback=fallback)
        ctx = self._ctx(scenario, w, ForecastStream((late,)))
        assert fp.decide(ctx).action == fallback.decide(ctx).action
        assert fp.decide(ctx).departure_delay == 0.0

    def test_waiting_delays_departure_by_the_shortfall(self, scenario, pipeline):
        from wildfireguardian_forecast_value.degradation.latency import make_release
        w = scenario.sample_world(0, 1)
        rel = make_release(w.truth, 0.6, 0.9, pipeline, {})   # lands at 1.5 h
        fp = ForecastPolicy(fallback=ProximityTriggerPolicy("route_a", "route_b", 1.5),
                            max_wait=1.0)
        d = fp.decide(self._ctx(scenario, w, ForecastStream((rel,))))
        assert d.waited and d.departure_delay == pytest.approx(0.5)

    def test_waiting_stops_at_the_deadline(self, scenario, pipeline):
        from wildfireguardian_forecast_value.degradation.latency import make_release
        w = scenario.sample_world(0, 1)
        rel = make_release(w.truth, 0.6, 5.0, pipeline, {})
        fp = ForecastPolicy(fallback=ProximityTriggerPolicy("route_a", "route_b", 1.5),
                            max_wait=1.0)
        assert not fp.decide(self._ctx(scenario, w, ForecastStream((rel,)))).waited


class TestEvaluateWorld:
    def test_undegraded_forecast_is_clairvoyant_when_nothing_is_unknowable(self, scenario,
                                                                            pipeline):
        """In a world whose only source ignited before the forecast was made, zero
        degradation really is perfect information."""
        no_spots = scenario.with_(spot=None)
        for i in range(15):
            w = no_spots.sample_world(i, 4)
            assert len(w.truth) == 1
            r = evaluate_world(no_spots, w, pipeline, {},
                               LatencySpec(no_spots.decision_time, 0.0))
            assert r.forecast_action == r.future_oracle_action
            assert r.delta_j == pytest.approx(r.future_oracle_value)

    def test_negative_latency_is_not_a_way_to_buy_clairvoyance(self, scenario):
        """There is no configuration in which a forecast sees past its own issue time."""
        from wildfireguardian_forecast_value.degradation.latency import ForecastRelease
        with pytest.raises(ValueError, match="arrives before it was made"):
            ForecastRelease(FireState(()), information_time=99.0, latency=-98.0)

    def test_an_undegraded_forecast_is_still_not_a_future_oracle(
            self, scenario, pipeline):
        """An un-degraded forecast issued at the decision time can still be beaten.

        Not a defect: a spot fire that ignites after the information time is not
        knowable, so a PRESENT_STATE_ORACLE is not a FUTURE_ORACLE. Conflating
        the two is how a study accidentally reports future-oracle value as
        achievable.
        """
        differed = 0
        for i in range(60):
            w = scenario.sample_world(i, 4)
            if not w.params.get("has_spot"):
                continue
            r = evaluate_world(scenario, w, pipeline, {},
                               LatencySpec(scenario.decision_time, 0.0))
            assert r.delta_j <= r.future_oracle_value + 1e-9
            differed += int(r.forecast_action != r.future_oracle_action)
        assert differed > 0, "the scenario should contain worlds with unknowable spot fires"

    def test_delta_j_never_exceeds_vpi(self, scenario, pipeline):
        for i in range(25):
            w = scenario.sample_world(i, 5)
            r = evaluate_world(scenario, w, pipeline, {"eps_theta": 0.25},
                               LatencySpec(0.6, 0.0))
            assert r.delta_j <= r.future_oracle_value + 1e-9

    def test_unavailable_forecast_gives_exactly_zero_value(self, scenario, pipeline):
        w = scenario.sample_world(2, 6)
        r = evaluate_world(scenario, w, pipeline, {"eps_theta": -0.3},
                           LatencySpec(0.6, 10.0))
        assert not r.forecast_available
        assert r.delta_j == 0.0
        assert r.forecast_action == r.baseline_action

    def test_skill_can_be_switched_off(self, scenario, pipeline):
        w = scenario.sample_world(0, 7)
        r = evaluate_world(scenario, w, pipeline, {}, LatencySpec(0.6, 0.0),
                           compute_skill=False)
        assert set(r.skill) == {"release_used"}

    def test_value_fraction_is_nan_when_even_a_future_oracle_is_worth_nothing(
            self, scenario, pipeline):
        """0/0 is reported as nan, never as 'realised 0% of the value'."""
        base = ProximityTriggerPolicy("route_a", "route_b", trigger_distance=1e9)
        pols = (base, ForecastPolicy(fallback=base), FutureOraclePolicy())
        seen_nan = False
        for i in range(30):
            w = scenario.sample_world(i, 8)
            r = evaluate_world(scenario, w, pipeline, {}, LatencySpec(0.6, 0.0), policies=pols)
            if r.future_oracle_value == 0.0:
                assert np.isnan(r.value_fraction)
                seen_nan = True
        assert seen_nan, "an always-robust baseline should be optimal in some worlds"


class TestPairedStudy:
    def test_arms_are_paired(self, scenario, pipeline):
        a = run_paired_study(scenario, 20, 3, pipeline, fixed_params={})
        b = run_paired_study(scenario, 20, 3, pipeline, fixed_params={"eps_theta": 0.2})
        check_pairing(a, b)
        assert [x.world_id for x in a] == list(range(20))

    def test_mismatched_arms_are_caught(self, scenario, pipeline):
        a = run_paired_study(scenario, 8, 3, pipeline, fixed_params={})
        b = run_paired_study(scenario, 6, 3, pipeline, fixed_params={})
        with pytest.raises(InvariantError, match="different worlds"):
            check_pairing(a, b)

    def test_worlds_are_reproducible(self, scenario, pipeline):
        a = run_paired_study(scenario, 10, 3, pipeline, fixed_params={})
        b = run_paired_study(scenario, 10, 3, pipeline, fixed_params={})
        assert [x.delta_j for x in a] == [x.delta_j for x in b]

    def test_different_seeds_give_different_worlds(self, scenario, pipeline):
        a = run_paired_study(scenario, 20, 3, pipeline, fixed_params={})
        b = run_paired_study(scenario, 20, 99, pipeline, fixed_params={})
        assert [x.delta_j for x in a] != [x.delta_j for x in b]

    def test_error_model_and_fixed_params_are_exclusive(self, scenario, pipeline):
        from wildfireguardian_forecast_value.degradation.combined import (
            CorrelatedErrorModel, Marginal,
        )
        em = CorrelatedErrorModel({"eps_theta": Marginal.normal(0, 0.1)})
        with pytest.raises(ValueError, match="not both"):
            run_paired_study(scenario, 4, 1, pipeline, error_model=em,
                             fixed_params={"eps_r": 0.1})

    def test_frame_declares_its_unit_of_analysis(self, scenario, pipeline):
        df = results_to_frame(run_paired_study(scenario, 6, 3, pipeline, fixed_params={}))
        assert df.attrs["unit_of_analysis"] == "world"
        assert len(df) == 6
