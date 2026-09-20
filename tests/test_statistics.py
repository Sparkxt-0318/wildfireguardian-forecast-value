"""World-level statistics, with the clustering trap front and centre."""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.statistics.bootstrap import (
    bootstrap_ci,
    cluster_bootstrap,
    paired_bootstrap_difference,
)
from wildfireguardian_forecast_value.statistics.effect_size import (
    cohens_dz,
    effect_sizes,
    hedges_correction,
    probability_of_superiority,
    value_fraction_summary,
)
from wildfireguardian_forecast_value.statistics.equivalence import non_inferiority, tost
from wildfireguardian_forecast_value.statistics.paired import (
    aggregate_to_worlds,
    clustering_diagnostics,
    paired_summary,
)


class TestPairedSummary:
    def test_arithmetic(self):
        s = paired_summary([0.0, 0.0, 10.0, 10.0])
        assert s.mean == pytest.approx(5.0)
        assert s.sd == pytest.approx(np.sqrt(100 / 3))
        assert s.n_zero == 2 and s.n_positive == 2 and s.win_rate == 0.5

    def test_zero_variance_gives_a_point_interval_not_nan(self):
        """Every world agreeing is an exact estimate, not an undefined one."""
        s = paired_summary([3.0] * 10)
        assert s.ci_low == s.ci_high == pytest.approx(3.0)
        assert np.isnan(s.t_stat) and np.isnan(s.p_value)

    def test_infinite_values_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            paired_summary([1.0, np.inf])

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="no worlds"):
            paired_summary([])


class TestAggregation:
    def test_collapses_to_one_value_per_world(self):
        ids, vals = aggregate_to_worlds([1.0, 3.0, 10.0, 20.0], [0, 0, 1, 1])
        assert ids.tolist() == [0, 1]
        assert vals.tolist() == [2.0, 15.0]

    def test_rejects_unknown_aggregation(self):
        with pytest.raises(ValueError, match="unknown aggregation"):
            aggregate_to_worlds([1.0], [0], how="geometric")

    def test_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="must match"):
            aggregate_to_worlds([1.0, 2.0], [0])


class TestClustering:
    def test_identical_within_world_gives_icc_one(self):
        ids = np.repeat([0, 1, 2, 3], 5)
        vals = np.repeat([0.0, 0.0, 10.0, 10.0], 5)
        d = clustering_diagnostics(vals, ids)
        assert d.icc == pytest.approx(1.0)
        assert d.design_effect == pytest.approx(5.0)
        assert d.effective_sample_size == pytest.approx(4.0)

    def test_naive_standard_error_is_understated(self):
        ids = np.repeat(np.arange(40), 25)
        rng = np.random.default_rng(0)
        world_effect = rng.normal(0, 5, 40)
        vals = np.repeat(world_effect, 25) + rng.normal(0, 0.2, 1000)
        d = clustering_diagnostics(vals, ids)
        assert d.icc > 0.9
        assert d.se_understatement_factor > 3.0
        assert d.effective_sample_size < 80

    def test_pure_noise_has_near_zero_icc(self):
        ids = np.repeat(np.arange(60), 20)
        vals = np.random.default_rng(1).normal(size=1200)
        d = clustering_diagnostics(vals, ids)
        assert abs(d.icc) < 0.1
        assert d.design_effect == pytest.approx(1.0, abs=2.0)

    def test_needs_two_worlds(self):
        with pytest.raises(ValueError, match="at least two"):
            clustering_diagnostics([1.0, 2.0], [0, 0])


class TestBootstrap:
    def test_replicate_shape_and_determinism(self):
        v = np.arange(20, dtype=float)
        a = cluster_bootstrap(v, np.mean, n_boot=100, seed=3)
        b = cluster_bootstrap(v, np.mean, n_boot=100, seed=3)
        assert a.shape == (100,) and np.array_equal(a, b)

    def test_interval_covers_a_known_mean(self):
        rng = np.random.default_rng(0)
        covered = 0
        for s in range(60):
            v = rng.normal(2.0, 1.0, 200)
            r = bootstrap_ci(v, np.mean, n_boot=300, seed=s)
            covered += int(r.ci_low <= 2.0 <= r.ci_high)
        assert covered >= 51           # ~95% nominal, allowing Monte-Carlo slack

    def test_degenerate_sample_gives_a_point_interval_not_nan(self):
        r = bootstrap_ci(np.zeros(40), np.mean, n_boot=100, seed=0)
        assert r.degenerate and r.ci_low == r.ci_high == 0.0

    def test_percentile_and_bca_agree_on_symmetric_data(self):
        v = np.random.default_rng(2).normal(0, 1, 400)
        p = bootstrap_ci(v, np.mean, n_boot=800, seed=0, method="percentile")
        b = bootstrap_ci(v, np.mean, n_boot=800, seed=0, method="bca")
        assert p.ci_low == pytest.approx(b.ci_low, abs=0.06)

    def test_bca_shifts_on_skewed_data(self):
        """On a skewed sample BCa is not centred where the percentile interval is."""
        v = np.random.default_rng(7).exponential(scale=3.0, size=250)
        p = bootstrap_ci(v, np.mean, n_boot=2000, seed=0, method="percentile")
        b = bootstrap_ci(v, np.mean, n_boot=2000, seed=0, method="bca")
        assert (p.ci_low, p.ci_high) != (b.ci_low, b.ci_high)
        # Both still bracket the estimate.
        for r in (p, b):
            assert r.ci_low < r.estimate < r.ci_high

    def test_needs_two_worlds(self):
        with pytest.raises(ValueError, match="at least two"):
            cluster_bootstrap([1.0], np.mean)

    def test_unknown_method_rejected(self):
        with pytest.raises(ValueError, match="percentile"):
            bootstrap_ci([1.0, 2.0], method="jackknife")

    def test_paired_bootstrap_uses_one_index_for_both_arms(self):
        """Pairing must survive resampling, or the variance reduction is lost."""
        rng = np.random.default_rng(5)
        base = rng.normal(100, 30, 300)
        a, b = base + 1.0, base
        paired = paired_bootstrap_difference(a, b, n_boot=600, seed=0)
        assert paired.ci_low == pytest.approx(1.0, abs=1e-9)
        assert paired.ci_high == pytest.approx(1.0, abs=1e-9)

    def test_paired_arms_must_match_in_length(self):
        with pytest.raises(ValueError, match="equal length"):
            paired_bootstrap_difference([1.0, 2.0], [1.0])


class TestEffectSizes:
    def test_dz(self):
        assert cohens_dz([1.0, 1.0, 1.0, 1.0]) != cohens_dz([1.0, 2.0])
        assert np.isnan(cohens_dz([2.0] * 5))

    def test_hedges_correction_shrinks_toward_zero(self):
        assert 0.9 < hedges_correction(20) < 1.0
        assert hedges_correction(200) > hedges_correction(20)

    def test_probability_of_superiority_splits_ties(self):
        assert probability_of_superiority([1.0, -1.0]) == 0.5
        assert probability_of_superiority([0.0, 0.0]) == 0.5
        assert probability_of_superiority([1.0, 0.0]) == 0.75

    def test_effect_sizes_bundle(self):
        d = np.concatenate([np.zeros(60), np.full(40, 30.0)])
        e = effect_sizes(d, action_changed=d > 0, n_boot=300)
        assert e.mean_delta == pytest.approx(12.0)
        assert e.probability_of_superiority == pytest.approx(0.7)
        assert e.fraction_worlds_action_changed == pytest.approx(0.4)
        assert e.mean_delta_ci[0] < 12.0 < e.mean_delta_ci[1]

    def test_value_fraction_counts_undecidable_worlds_separately(self):
        f = np.array([1.0, 0.5, np.nan, np.nan, 0.0])
        s = value_fraction_summary(f, n_boot=200)
        assert s["n_worlds"] == 5
        assert s["n_worlds_with_positive_future_oracle_value"] == 3
        assert s["n_worlds_undecidable"] == 2
        assert s["mean_value_fraction"] == pytest.approx(0.5)


class TestEquivalence:
    def test_tight_data_is_equivalent_at_a_wide_margin(self):
        d = np.random.default_rng(0).normal(0.0, 0.05, 300)
        assert tost(d, margin=1.0, n_boot=400).is_equivalent

    def test_large_effect_is_not_equivalent_at_a_tight_margin(self):
        d = np.random.default_rng(0).normal(5.0, 1.0, 300)
        assert not tost(d, margin=0.5, n_boot=400).is_equivalent

    def test_margin_must_be_positive(self):
        with pytest.raises(ValueError, match="margin"):
            tost([1.0, 2.0], margin=0.0)

    def test_non_inferiority_one_sided(self):
        d = np.random.default_rng(1).normal(-0.1, 0.3, 300)
        assert non_inferiority(d, margin=1.0, n_boot=400).is_non_inferior
        assert not non_inferiority(d, margin=0.01, n_boot=400).is_non_inferior

    def test_t_and_bootstrap_flavours_broadly_agree(self):
        d = np.random.default_rng(2).normal(0.2, 1.0, 400)
        a = tost(d, margin=1.0, method="t")
        b = tost(d, margin=1.0, method="bootstrap", n_boot=800)
        assert a.decision == b.decision

    def test_results_carry_their_margin(self):
        r = tost(np.zeros(10) + 0.01, margin=2.0, n_boot=200)
        assert r.margin == 2.0 and r.as_dict()["margin"] == 2.0
