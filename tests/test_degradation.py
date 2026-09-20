"""Degradation operators: behaviour, domain constraints, and algebra."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.degradation.base import (
    DegradationPipeline,
    SourceSelector,
)
from wildfireguardian_forecast_value.degradation.combined import (
    STANDARD_ORDER,
    CorrelatedErrorModel,
    Marginal,
    standard_pipeline,
)
from wildfireguardian_forecast_value.degradation.direction import DirectionError, WidenFront
from wildfireguardian_forecast_value.degradation.displacement import SpatialDisplacement
from wildfireguardian_forecast_value.degradation.spotting import (
    SpotDelay,
    SpotDisplacement,
    SpotMiss,
)
from wildfireguardian_forecast_value.degradation.spread_rate import SpreadRateError, log_ratio_error
from wildfireguardian_forecast_value.fields.front import FireState
from wildfireguardian_forecast_value.validation.invariants import check_identity_degradation

ALL_OPERATORS = [
    SpreadRateError(),
    DirectionError(),
    WidenFront(),
    SpatialDisplacement(mode="polar"),
    SpatialDisplacement(mode="cartesian"),
    SpotMiss(p_miss=0.5),
    SpotDelay(),
    SpotDisplacement(),
]


class TestSpreadRate:
    def test_multiplicative(self, two_source_state):
        out = SpreadRateError().apply(two_source_state, {"eps_r": 0.25})
        assert out.by_label("main").spread_rate == pytest.approx(2.5)
        assert out.by_label("spot1").spread_rate == pytest.approx(1.25)

    def test_asymmetry_is_real(self, wedge):
        st = FireState((wedge,))
        op = SpreadRateError()
        fast = op.apply(st, {"eps_r": 0.5}).by_label("main").spread_rate
        slow = op.apply(st, {"eps_r": -0.5}).by_label("main").spread_rate
        # A +50% rate error costs 1 h at 6 km; a -50% error costs 3 h.
        assert abs(6 / fast - 3.0) == pytest.approx(1.0)
        assert abs(6 / slow - 3.0) == pytest.approx(3.0)

    @pytest.mark.parametrize("bad", [-1.0, -1.5, np.inf, np.nan])
    def test_domain_error_raises(self, two_source_state, bad):
        with pytest.raises(ValueError, match="eps_r"):
            SpreadRateError().apply(two_source_state, {"eps_r": bad})

    def test_domain_error_can_clip_instead(self, two_source_state):
        op = SpreadRateError(on_domain_error="clip")
        out = op.apply(two_source_state, {"eps_r": -2.0})
        assert out.by_label("main").spread_rate > 0

    def test_clip_to_bounds_the_rate(self, two_source_state):
        op = SpreadRateError(clip_to=(0.5, 3.0))
        assert op.apply(two_source_state, {"eps_r": 10.0}).by_label("main").spread_rate == 3.0
        assert op.apply(two_source_state, {"eps_r": -0.99}).by_label("main").spread_rate == 0.5

    def test_log_ratio_is_symmetric(self):
        assert log_ratio_error(4.0, 2.0) == pytest.approx(-log_ratio_error(1.0, 2.0))


class TestDirection:
    def test_adds_and_wraps(self, wedge):
        st = FireState((wedge.with_(heading=3.0),))
        out = DirectionError().apply(st, {"eps_theta": 1.0})
        assert out.by_label("main").heading == pytest.approx(4.0 - 2 * np.pi)

    def test_isotropic_untouched_by_default(self, two_source_state):
        out = DirectionError(selector=SourceSelector()).apply(two_source_state, {"eps_theta": 1.0})
        assert out.by_label("spot1").heading == pytest.approx(
            two_source_state.by_label("spot1").heading)

    def test_isotropic_rotated_when_asked(self, two_source_state):
        out = DirectionError(selector=SourceSelector(), rotate_isotropic=True).apply(
            two_source_state, {"eps_theta": 1.0})
        assert out.by_label("spot1").heading == pytest.approx(1.0)

    def test_default_selector_is_primary_only(self, two_source_state):
        out = DirectionError().apply(two_source_state, {"eps_theta": 0.3})
        assert out.by_label("main").heading == pytest.approx(0.3)
        assert out.by_label("spot1").heading == pytest.approx(0.0)

    def test_widen_front_clips_to_pi(self, two_source_state):
        out = WidenFront().apply(two_source_state, {"eps_phi": 10.0})
        assert out.by_label("main").half_angle == pytest.approx(np.pi)


class TestDisplacement:
    def test_translation_identity(self, wedge):
        """t'(p) = t(p - s), exactly."""
        st = FireState((wedge,))
        s = np.array([1.3, -0.7])
        moved = SpatialDisplacement(mode="cartesian").apply(
            st, {"disp_x": s[0], "disp_y": s[1]})
        pts = np.random.default_rng(1).normal(size=(200, 2)) * 5
        a = moved.arrival_time(pts)
        b = st.arrival_time(pts - s)
        assert np.array_equal(np.isinf(a), np.isinf(b))
        m = np.isfinite(a)
        assert np.allclose(a[m], b[m])

    def test_negative_magnitude_rejected(self, two_source_state):
        with pytest.raises(ValueError, match="magnitude"):
            SpatialDisplacement(mode="polar").apply(
                two_source_state, {"disp_magnitude": -1.0, "disp_heading": 0.0})

    def test_relative_to_heading_follows_the_source(self, wedge):
        st = FireState((wedge.with_(heading=np.pi / 2),))
        out = SpatialDisplacement(mode="polar", relative_to_heading=True).apply(
            st, {"disp_magnitude": 2.0, "disp_heading": 0.0})
        assert out.by_label("main").origin[0] == pytest.approx(0.0, abs=1e-12)
        assert out.by_label("main").origin[1] == pytest.approx(2.0)

    def test_relative_mode_requires_polar(self):
        with pytest.raises(ValueError, match="polar"):
            SpatialDisplacement(mode="cartesian", relative_to_heading=True)


class TestSpotting:
    def test_miss_thresholds_the_latent_uniform(self, two_source_state):
        op = SpotMiss(p_miss=0.5)
        assert len(op.apply(two_source_state, {"spot_miss_u": 0.50})) == 2
        assert len(op.apply(two_source_state, {"spot_miss_u": 0.49})) == 1

    def test_miss_never_touches_the_primary(self, two_source_state):
        out = SpotMiss(p_miss=1.0).apply(two_source_state, {"spot_miss_u": 0.0})
        assert out.labels == ("main",)

    def test_latent_uniform_out_of_range_rejected(self, two_source_state):
        with pytest.raises(ValueError, match="latent uniform"):
            SpotMiss(p_miss=0.5).apply(two_source_state, {"spot_miss_u": 1.5})

    def test_negative_delay_is_future_oracle_information_and_is_rejected(
            self, two_source_state):
        """Predicting an ignition before it happens is not error, it is leakage."""
        with pytest.raises(ValueError, match="future-oracle"):
            SpotDelay().apply(two_source_state, {"spot_delay": -0.1})

    def test_delay_moves_only_the_spot(self, two_source_state):
        out = SpotDelay().apply(two_source_state, {"spot_delay": 0.5})
        assert out.by_label("spot1").ignition_time == pytest.approx(1.5)
        assert out.by_label("main").ignition_time == pytest.approx(0.0)

    def test_spot_displacement_has_its_own_parameters(self):
        assert SpotDisplacement().param_names == ("spot_disp_magnitude", "spot_disp_heading")


class TestAlgebra:
    @pytest.mark.parametrize("op", ALL_OPERATORS, ids=lambda o: o.name + str(o.param_names))
    def test_every_operator_has_an_exact_identity(self, op, two_source_state):
        check_identity_degradation(DegradationPipeline([op]), two_source_state)

    @pytest.mark.parametrize("op", ALL_OPERATORS, ids=lambda o: o.name + str(o.param_names))
    def test_missing_parameters_raise(self, op, two_source_state):
        if not op.param_names:
            pytest.skip("operator takes no parameters")
        with pytest.raises(KeyError):
            op.apply(two_source_state, {})

    def test_pipeline_refuses_unknown_parameters(self, two_source_state):
        pipe = DegradationPipeline([SpreadRateError()])
        with pytest.raises(KeyError, match="not consumed"):
            pipe.apply(two_source_state, {"eps_theta": 0.1})

    def test_standard_pipeline_is_in_the_documented_order(self):
        names = [op.name for op in standard_pipeline()]
        assert names == [n for n in STANDARD_ORDER if n in names]

    def test_field_disjoint_operators_commute(self, two_source_state):
        """Rate, absolute displacement and spot delay touch disjoint fields."""
        ops = [SpreadRateError(), SpatialDisplacement(mode="cartesian"), SpotDelay()]
        p = {"eps_r": 0.3, "disp_x": 1.0, "disp_y": -2.0, "spot_delay": 0.4}
        a = DegradationPipeline(ops).apply(two_source_state, p)
        b = DegradationPipeline(ops[::-1]).apply(two_source_state, p)
        assert a.to_dict() == b.to_dict()

    def test_heading_relative_displacement_does_not_commute(self, two_source_state):
        """Documented exception: relative displacement reads the heading."""
        ops = [DirectionError(), SpatialDisplacement(mode="polar", relative_to_heading=True)]
        p = {"eps_theta": np.pi / 2, "disp_magnitude": 3.0, "disp_heading": 0.0}
        a = DegradationPipeline(ops).apply(two_source_state, p)
        b = DegradationPipeline(ops[::-1]).apply(two_source_state, p)
        assert a.by_label("main").origin != b.by_label("main").origin

    def test_pipeline_identity_leaves_the_state_untouched(self, two_source_state):
        pipe = standard_pipeline(p_miss=0.9)
        assert pipe.apply(two_source_state).to_dict() == two_source_state.to_dict()


class TestCorrelatedErrorModel:
    def test_marginal_moments(self):
        m = CorrelatedErrorModel({"a": Marginal.normal(1.0, 2.0)})
        s = m.sample(40_000, 0)["a"]
        assert s.mean() == pytest.approx(1.0, abs=0.05)
        assert s.std() == pytest.approx(2.0, abs=0.05)

    def test_unit_uniform_is_exactly_in_range(self):
        m = CorrelatedErrorModel({"u": Marginal.unit_uniform()})
        s = m.sample(5000, 1)["u"]
        assert s.min() >= 0.0 and s.max() <= 1.0

    def test_half_normal_is_non_negative(self):
        m = CorrelatedErrorModel({"d": Marginal("half_normal", sigma=0.4)})
        assert m.sample(5000, 2)["d"].min() >= 0.0

    def test_correlation_is_induced(self):
        m = CorrelatedErrorModel(
            {"a": Marginal.normal(0, 1), "b": Marginal.normal(0, 1)},
            {("a", "b"): 0.8})
        s = m.sample(40_000, 3)
        assert np.corrcoef(s["a"], s["b"])[0, 1] == pytest.approx(0.8, abs=0.02)

    def test_zero_correlation_gives_independence(self):
        m = CorrelatedErrorModel.independent(
            {"a": Marginal.normal(0, 1), "b": Marginal.normal(0, 1)})
        s = m.sample(40_000, 4)
        assert abs(np.corrcoef(s["a"], s["b"])[0, 1]) < 0.02

    def test_latent_correlation_is_not_the_realised_one(self):
        """The documented caveat: R is the copula's, not Pearson's."""
        m = CorrelatedErrorModel(
            {"a": Marginal.normal(0, 1), "d": Marginal("half_normal", sigma=1.0)},
            {("a", "d"): 0.9})
        realised = m.realised_correlation(40_000, 5)[0, 1]
        assert realised < 0.9 - 0.02

    def test_non_psd_matrix_is_rejected(self):
        with pytest.raises(ValueError, match="positive semi-definite"):
            CorrelatedErrorModel(
                {"a": Marginal.normal(), "b": Marginal.normal(), "c": Marginal.normal()},
                {("a", "b"): 0.95, ("b", "c"): 0.95, ("a", "c"): -0.95})

    def test_singular_matrix_is_allowed(self):
        m = CorrelatedErrorModel(
            {"a": Marginal.normal(), "b": Marginal.normal()}, {("a", "b"): 1.0})
        s = m.sample(200, 6)
        assert np.allclose(s["a"], s["b"])

    def test_unknown_marginal_kind_is_rejected(self):
        with pytest.raises(ValueError, match="unknown marginal"):
            Marginal("cauchy", mu=0.0)

    def test_round_trip(self):
        m = CorrelatedErrorModel(
            {"a": Marginal.normal(0, 0.2), "u": Marginal.unit_uniform()}, {("a", "u"): -0.3})
        again = CorrelatedErrorModel.from_dict(m.to_dict())
        assert again.names == m.names
        assert np.allclose(again.correlation_matrix, m.correlation_matrix)

    def test_records_feed_a_pipeline(self, two_source_state):
        pipe = standard_pipeline(p_miss=0.5)
        m = CorrelatedErrorModel(
            {k: (Marginal.unit_uniform() if k == "spot_miss_u"
                 else Marginal("half_normal", sigma=0.2) if k == "spot_delay"
                 else Marginal.normal(0.0, 0.1))
             for k in pipe.param_names})
        for rec in m.sample_records(20, 7):
            rec["disp_magnitude"] = abs(rec["disp_magnitude"])
            rec["spot_disp_magnitude"] = abs(rec["spot_disp_magnitude"])
            pipe.apply(two_source_state, rec)
