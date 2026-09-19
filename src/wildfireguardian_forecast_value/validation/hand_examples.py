"""Hand-solvable fixtures: the independent-validation layer.

Every example here has a closed-form answer that can be checked on paper in
under a minute, written out in the ``derivation`` field in full.  The code that
computes the answer and the code that states it are independent: the expected
values are arithmetic on the inputs, not calls into the library.  If an
implementation drifts, these break before anything subtle does.

The examples are used three ways:

* ``tests/test_hand_checkable.py`` asserts each one;
* ``wg-forecast-value validate`` runs them and prints the derivations, so the
  checks are legible to a reader who is not running pytest;
* they are the worked examples in ``docs/VALIDATION.md``.

Numbers are chosen to be exact in binary floating point wherever possible
(halves, quarters, 3-4-5 triangles), so an assertion can be tight rather than
generously toleranced.  Where a value is irrational (a 45-degree diagonal,
``sqrt(2)``), the tolerance is stated in the example.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from wildfireguardian_forecast_value.decision_value.loss import RouteChoiceLoss
from wildfireguardian_forecast_value.degradation.direction import DirectionError
from wildfireguardian_forecast_value.degradation.displacement import SpatialDisplacement
from wildfireguardian_forecast_value.degradation.latency import ForecastRelease, ForecastStream
from wildfireguardian_forecast_value.degradation.spotting import SpotDelay, SpotMiss
from wildfireguardian_forecast_value.degradation.spread_rate import SpreadRateError
from wildfireguardian_forecast_value.fields.front import NEVER, FireSource, FireState, known_at
from wildfireguardian_forecast_value.outcomes import Outcome
from wildfireguardian_forecast_value.skill_metrics.categorical import categorical_scores
from wildfireguardian_forecast_value.skill_metrics.continuous import arrival_time_metrics
from wildfireguardian_forecast_value.statistics.paired import clustering_diagnostics, paired_summary
from wildfireguardian_forecast_value.synthetic_decisions.routes import Route

__all__ = ["HandExample", "hand_examples", "run_hand_examples"]


@dataclass
class HandExample:
    """One closed-form check."""

    key: str
    title: str
    derivation: str
    compute: Callable[[], float | np.ndarray]
    expected: float | np.ndarray
    tolerance: float = 1e-12

    def run(self) -> tuple[bool, object, object]:
        got = self.compute()
        exp = self.expected
        ok = bool(np.allclose(np.asarray(got, dtype=float), np.asarray(exp, dtype=float),
                              rtol=0.0, atol=self.tolerance, equal_nan=True))
        return ok, got, exp


def _wedge() -> FireSource:
    """Rate 2 km/h, due east, 45-degree half-angle, ignited at t = 0 from the origin."""
    return FireSource(origin=(0.0, 0.0), ignition_time=0.0, spread_rate=2.0,
                      heading=0.0, half_angle=np.pi / 4)


def hand_examples() -> list[HandExample]:
    """The full set, in the order they appear in ``docs/VALIDATION.md``."""
    ex: list[HandExample] = []

    # -- 1. arrival time inside and outside the wedge -----------------------
    ex.append(HandExample(
        key="V1_arrival_time",
        title="Arrival time of a 45-degree wedge",
        derivation=(
            "Source: origin (0,0), t0 = 0, r = 2 km/h, heading 0 (east), half-angle 45 deg.\n"
            "  (4, 0): distance 4, bearing 0 deg -> inside. t = 0 + 4/2 = 2 h.\n"
            "  (3, 3): distance sqrt(18) = 4.2426, bearing 45 deg -> exactly on the edge,\n"
            "          which this package counts as inside. t = 4.2426/2 = 2.1213 h.\n"
            "  (0, 4): bearing 90 deg -> outside the +-45 deg wedge. t = +inf (never burns).\n"
            "  (0, 0): the origin, distance 0. t = t0 = 0 h."
        ),
        compute=lambda: _wedge().arrival_time([[4, 0], [3, 3], [0, 4], [0, 0]]),
        expected=np.array([2.0, np.sqrt(18) / 2, NEVER, 0.0]),
        tolerance=1e-12,
    ))

    # -- 2. spread-rate error is multiplicative and asymmetric --------------
    def _rate():
        op = SpreadRateError()
        st = FireState((_wedge(),))
        fast = op.apply(st, {"eps_r": 0.5}).by_label("main").spread_rate
        slow = op.apply(st, {"eps_r": -0.5}).by_label("main").spread_rate
        # Arrival time at (6, 0) under each.
        return np.array([fast, slow, 6.0 / fast, 6.0 / slow])

    ex.append(HandExample(
        key="V2_spread_rate_asymmetry",
        title="eps_r = +0.5 and eps_r = -0.5 are not equal and opposite",
        derivation=(
            "r' = r (1 + eps_r) with r = 2 km/h.\n"
            "  eps_r = +0.5 -> r' = 3.0 km/h; arrival at (6,0) is 6/3 = 2 h (truth: 3 h),\n"
            "                  so the forecast is 1 h EARLY.\n"
            "  eps_r = -0.5 -> r' = 1.0 km/h; arrival at (6,0) is 6/1 = 6 h (truth: 3 h),\n"
            "                  so the forecast is 3 h LATE.\n"
            "Equal-magnitude eps_r gives errors of 1 h and 3 h. Any sweep that treats\n"
            "+eps and -eps as the same size of error is measuring the wrong thing."
        ),
        compute=_rate,
        expected=np.array([3.0, 1.0, 2.0, 6.0]),
    ))

    # -- 3. displacement translates the arrival field exactly ---------------
    def _disp():
        op = SpatialDisplacement(mode="cartesian", relative_to_heading=False)
        st = FireState((_wedge(),))
        moved = op.apply(st, {"disp_x": 1.0, "disp_y": 0.0})
        p = np.array([[5.0, 0.0]])
        return np.array([float(moved.arrival_time(p)[0]), float(st.arrival_time(p - [1.0, 0.0])[0])])

    ex.append(HandExample(
        key="V3_displacement_is_a_translation",
        title="t'(p) = t(p - s) exactly",
        derivation=(
            "Shifting the source origin by s translates the whole arrival-time field:\n"
            "  displaced field at (5,0), s = (1,0):  distance from (1,0) is 4 -> t = 2 h.\n"
            "  original field at (5,0) - (1,0) = (4,0): distance 4 -> t = 2 h.\n"
            "The two must agree to machine precision; they are the same arithmetic."
        ),
        compute=_disp,
        expected=np.array([2.0, 2.0]),
    ))

    # -- 4. direction error is a no-op on an isotropic source ---------------
    def _dir_iso():
        iso = FireSource(origin=(0, 0), ignition_time=0.0, spread_rate=1.0, heading=0.0,
                         half_angle=np.pi, label="spot1", kind="spot")
        op = DirectionError(rotate_isotropic=False)
        st = FireState((iso,))
        out = op.apply(st, {"eps_theta": 1.0})
        p = np.array([[0.0, 3.0]])
        return np.array([float(st.arrival_time(p)[0]), float(out.arrival_time(p)[0])])

    ex.append(HandExample(
        key="V4_direction_error_no_op_on_isotropic",
        title="Rotating a circle changes nothing",
        derivation=(
            "A spot fire has half-angle pi: it burns in every direction. Rotating its\n"
            "heading cannot change its arrival-time field. At (0,3), r = 1 km/h, t0 = 0,\n"
            "the arrival time is 3 h both before and after a 1-radian heading error.\n"
            "This is why DirectionError skips isotropic sources by default rather than\n"
            "silently applying an identity operation."
        ),
        compute=_dir_iso,
        expected=np.array([3.0, 3.0]),
    ))

    # -- 5. latency is availability, not a penalty --------------------------
    def _latency():
        st = FireState((_wedge(),))
        r = ForecastRelease(st, information_time=0.5, latency=0.4)
        stream = ForecastStream((r,))
        return np.array([
            r.availability_time,
            1.0 if stream.available_at(0.89) is not None else 0.0,
            1.0 if stream.available_at(0.90) is not None else 0.0,
            r.age_at(1.0),
        ])

    ex.append(HandExample(
        key="V5_latency_availability",
        title="s + delta <= t_d, inclusive",
        derivation=(
            "A release built from information at s = 0.5 h with latency delta = 0.4 h\n"
            "becomes available at a = 0.9 h.\n"
            "  at t = 0.89 h it does not exist  -> the decision maker has nothing;\n"
            "  at t = 0.90 h it exists exactly  -> inclusive tie convention, it is usable;\n"
            "  used at t = 1.0 h its information is 1.0 - 0.5 = 0.5 h old, which is more\n"
            "  than delta. Staleness and latency are different numbers."
        ),
        compute=_latency,
        expected=np.array([0.9, 0.0, 1.0, 0.5]),
    ))

    # -- 6. information time forbids clairvoyance ---------------------------
    def _known():
        st = FireState((
            _wedge(),
            FireSource(origin=(6, 0), ignition_time=1.2, spread_rate=1.0, heading=0.0,
                       half_angle=np.pi, label="spot1", kind="spot"),
        ))
        return np.array([len(known_at(st, 1.0)), len(known_at(st, 1.2)), len(known_at(st, 2.0))])

    ex.append(HandExample(
        key="V6_no_clairvoyance",
        title="A forecast cannot contain an ignition that has not happened",
        derivation=(
            "Truth has a main front (t0 = 0) and a spot fire igniting at t0 = 1.2 h.\n"
            "  information time 1.0 h -> 1 source: the spot has not happened yet;\n"
            "  information time 1.2 h -> 2 sources: it has just happened (inclusive);\n"
            "  information time 2.0 h -> 2 sources."
        ),
        compute=_known,
        expected=np.array([1, 2, 2]),
    ))

    # -- 7. spot miss and spot delay ----------------------------------------
    def _spot():
        st = FireState((
            _wedge(),
            FireSource(origin=(6, 0), ignition_time=1.0, spread_rate=1.0, heading=0.0,
                       half_angle=np.pi, label="spot1", kind="spot"),
        ))
        miss = SpotMiss(p_miss=0.5)
        kept = len(miss.apply(st, {"spot_miss_u": 0.5}))     # 0.5 < 0.5 is False -> kept
        dropped = len(miss.apply(st, {"spot_miss_u": 0.49}))  # 0.49 < 0.5 -> dropped
        delayed = SpotDelay().apply(st, {"spot_delay": 0.25}).by_label("spot1").ignition_time
        main_untouched = SpotDelay().apply(st, {"spot_delay": 0.25}).by_label("main").ignition_time
        return np.array([kept, dropped, delayed, main_untouched])

    ex.append(HandExample(
        key="V7_spotting",
        title="Spot miss thresholds a latent uniform; spot delay leaves the main front alone",
        derivation=(
            "SpotMiss(p_miss = 0.5) drops the spot when the latent uniform u < 0.5.\n"
            "  u = 0.50 -> not less than 0.5 -> 2 sources remain;\n"
            "  u = 0.49 -> less than 0.5     -> 1 source remains.\n"
            "SpotDelay(+0.25 h) moves the spot's ignition from 1.0 to 1.25 h and must\n"
            "leave the primary source's ignition time at 0.0: the selector is kind='spot'."
        ),
        compute=_spot,
        expected=np.array([2, 1, 1.25, 0.0]),
    ))

    # -- 8. route margin and overrun ----------------------------------------
    def _route():
        route = Route("r", ((0.0, -5.0), (0.0, 5.0)), speed=10.0, sample_spacing=0.001)
        src = FireSource(origin=(-5.0, 0.0), ignition_time=0.0, spread_rate=5.0,
                         heading=0.0, half_angle=np.pi)
        st = FireState((src,))
        return np.array([route.margin(st, 0.0), route.margin(st, 0.5), route.margin(st, 1.0)])

    ex.append(HandExample(
        key="V8_route_margin",
        title="The tightest point on a route is not the closest point to the fire",
        derivation=(
            "Route: the segment x = 0 from y = -5 to y = +5, travelled at v = 10 km/h, so a\n"
            "receptor departing at t0 is at arc length L (hence y = L - 5) at time t0 + L/10.\n"
            "Fire: isotropic, origin (-5, 0), r = 5 km/h, so it reaches (0, y) at\n"
            "sqrt(25 + y^2)/5.\n"
            "\n"
            "  gap(L) = sqrt(25 + (L-5)^2)/5 - (t0 + L/10)\n"
            "\n"
            "The naive guess is the route midpoint (0,0), the point nearest the fire:\n"
            "there the gap is 1.0 - 0.5 = 0.5 h. That is NOT the minimum. Setting\n"
            "d(gap)/dL = 0 with u = L - 5:\n"
            "\n"
            "  u / (5 sqrt(25 + u^2)) = 1/10   ->   2u = sqrt(25 + u^2)\n"
            "  4u^2 = 25 + u^2  ->  u = 5/sqrt(3) = 2.8868,  so L = 7.8868, y = +2.8868.\n"
            "\n"
            "The binding point is PAST the midpoint, on the far side, because the receptor\n"
            "is still moving while the fire closes. There:\n"
            "\n"
            "  fire arrives at sqrt(25 + 25/3)/5 = (10/sqrt(3))/5 = 2/sqrt(3) = 1.1547 h\n"
            "  receptor passes at t0 + 0.78868 h\n"
            "  margin(t0 = 0) = 2/sqrt(3) - (1/2 + 1/(2 sqrt(3))) = (sqrt(3) - 1)/2 = 0.36603 h\n"
            "\n"
            "Departing later shifts every passage time uniformly, so the margin shifts by\n"
            "exactly -dt:\n"
            "  depart 0.5 h -> 0.36603 - 0.5 = -0.13397  (overrun)\n"
            "  depart 1.0 h -> 0.36603 - 1.0 = -0.63397  (overrun)\n"
            "Tolerance 1e-5: the margin is found by sampling the path at 1 m spacing, and\n"
            "sampling can only overstate the margin (docs/ASSUMPTIONS.md, A-05)."
        ),
        compute=_route,
        expected=np.array([(np.sqrt(3) - 1) / 2,
                           (np.sqrt(3) - 1) / 2 - 0.5,
                           (np.sqrt(3) - 1) / 2 - 1.0]),
        tolerance=1e-5,
    ))

    # -- 9. the loss function ----------------------------------------------
    def _loss():
        lm = RouteChoiceLoss(time_cost_per_hour=1.0, burnover_loss=50.0)
        safe = Outcome("a", travel_time=1.0, burned_over=False, safety_margin=0.5)
        caught = Outcome("a", travel_time=1.0, burned_over=True, safety_margin=-0.1)
        # A community of 4 where 1 is caught.
        mean = float(np.mean(lm.losses([safe, safe, safe, caught])))
        return np.array([lm.loss(safe), lm.loss(caught), mean, lm.loss_ratio])

    ex.append(HandExample(
        key="V9_loss",
        title="J = c_t * travel_time + L * 1[overrun]",
        derivation=(
            "c_t = 1 hour per hour, L = 50 hours.\n"
            "  safe:   J = 1*1.0 + 0  = 1.0\n"
            "  caught: J = 1*1.0 + 50 = 51.0\n"
            "  a community of 4 with 1 caught: (1 + 1 + 1 + 51)/4 = 13.5\n"
            "  loss ratio L / c_t = 50."
        ),
        compute=_loss,
        expected=np.array([1.0, 51.0, 13.5, 50.0]),
    ))

    # -- 10. skill metrics with censoring ------------------------------------
    def _skill():
        m = arrival_time_metrics([1.0, 2.0, np.inf, 4.0], [1.5, 2.0, 3.0, np.inf])
        return np.array([m.mae, m.rmse, m.bias, m.n_both, m.n_miss, m.n_false, m.coverage])

    ex.append(HandExample(
        key="V10_arrival_metrics_censoring",
        title="Infinities are counted, never averaged",
        derivation=(
            "truth    = [1.0, 2.0, inf, 4.0]\n"
            "forecast = [1.5, 2.0, 3.0, inf]\n"
            "Both finite at points 1 and 2 only: errors +0.5 and 0.0.\n"
            "  MAE  = (0.5 + 0)/2 = 0.25\n"
            "  RMSE = sqrt((0.25 + 0)/2) = 0.35355\n"
            "  bias = (0.5 + 0)/2 = +0.25 (forecast late)\n"
            "  n_both = 2, n_miss = 1 (truth burns, forecast says never),\n"
            "  n_false = 1, coverage = 2/4 = 0.5."
        ),
        compute=_skill,
        expected=np.array([0.25, np.sqrt(0.125), 0.25, 2, 1, 1, 0.5]),
        tolerance=1e-12,
    ))

    def _cat():
        s = categorical_scores([1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0])
        return np.array([s["pod"], s["far"], s["csi"], s["frequency_bias"]])

    ex.append(HandExample(
        key="V11_categorical_scores",
        title="POD, FAR, CSI from a 2x2 table",
        derivation=(
            "truth    = [1,1,1,0,0,0], forecast = [1,1,0,1,0,0]\n"
            "  hits a = 2, false alarms b = 1, misses c = 1, correct negatives d = 2\n"
            "  POD = a/(a+c) = 2/3 = 0.6667\n"
            "  FAR = b/(a+b) = 1/3 = 0.3333\n"
            "  CSI = a/(a+b+c) = 2/4 = 0.5\n"
            "  frequency bias = (a+b)/(a+c) = 3/3 = 1.0"
        ),
        compute=_cat,
        expected=np.array([2 / 3, 1 / 3, 0.5, 1.0]),
    ))

    # -- 12. the clustering trap, with exact arithmetic ----------------------
    def _cluster():
        # Four worlds of five identical receptors: within-world variance is zero,
        # so the ICC is exactly 1 and the design effect is exactly the cluster size.
        world_ids = np.repeat([0, 1, 2, 3], 5)
        values = np.repeat([0.0, 0.0, 10.0, 10.0], 5)
        d = clustering_diagnostics(values, world_ids)
        return np.array([d.icc, d.design_effect, d.effective_sample_size,
                         d.naive_se, d.correct_se])

    ex.append(HandExample(
        key="V12_clustering_design_effect",
        title="Four worlds of five identical residents are four observations, not twenty",
        derivation=(
            "Worlds A,B have Delta J = 0 for all five residents; worlds C,D have 10.\n"
            "Within-world variance is zero, so MSW = 0 and ICC = MSB/MSB = 1 exactly.\n"
            "  design effect = 1 + (m-1)*ICC = 1 + 4*1 = 5 = the cluster size;\n"
            "  effective sample size = 20/5 = 4 = the number of worlds.\n"
            "The naive receptor-level SE uses N = 20: sd = sqrt(sum(x-5)^2/19)\n"
            "  = sqrt(20*25/19) = 5.1299, SE = 5.1299/sqrt(20) = 1.1471.\n"
            "The correct world-level SE uses the four world means (0,0,10,10):\n"
            "  sd = sqrt(2*25 + 2*25)/sqrt(3) = sqrt(100/3) = 5.7735, SE = 5.7735/2 = 2.8868.\n"
            "The naive SE is 2.5x too small -- exactly sqrt(5), the design effect."
        ),
        compute=_cluster,
        expected=np.array([1.0, 5.0, 4.0,
                           float(np.sqrt(20 * 25 / 19) / np.sqrt(20)),
                           float(np.sqrt(100 / 3) / 2)]),
        tolerance=1e-10,
    ))

    # -- 13. paired summary --------------------------------------------------
    def _paired():
        s = paired_summary([0.0, 0.0, 10.0, 10.0])
        return np.array([s.mean, s.sd, s.se, s.median, s.n_positive, s.n_zero, s.win_rate])

    ex.append(HandExample(
        key="V13_paired_summary",
        title="Paired summary arithmetic",
        derivation=(
            "d = [0, 0, 10, 10]: mean 5, sample sd sqrt(100/3) = 5.7735,\n"
            "SE = 5.7735/2 = 2.8868, median 5, two strictly positive, two exactly zero,\n"
            "win rate 2/4 = 0.5. The two zeros are worlds where the forecast changed\n"
            "nothing; they are evidence and are never dropped."
        ),
        compute=_paired,
        expected=np.array([5.0, float(np.sqrt(100 / 3)), float(np.sqrt(100 / 3) / 2),
                           5.0, 2, 2, 0.5]),
        tolerance=1e-12,
    ))

    return ex


def run_hand_examples(verbose: bool = False) -> tuple[int, int, list[dict]]:
    """Run every example.  Returns ``(n_passed, n_total, records)``."""
    records = []
    passed = 0
    for e in hand_examples():
        ok, got, exp = e.run()
        passed += int(ok)
        records.append({"key": e.key, "title": e.title, "passed": ok,
                        "got": np.asarray(got, dtype=float).tolist(),
                        "expected": np.asarray(exp, dtype=float).tolist(),
                        "derivation": e.derivation if verbose else ""})
    return passed, len(records), records
