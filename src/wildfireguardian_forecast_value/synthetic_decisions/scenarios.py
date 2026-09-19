"""The synthetic decision laboratory: worlds, the toy scenario, and the four cases.

Scenario geometry (all coordinates in km, ``+x`` east, ``+y`` north)::

        y
      12 +                                              SAFE HAVEN (16,12)
      11 + o--------------- route B (22.2 km) ---------o
         |  \                                        /
       8 +   COMMUNITY (2,8)                         /
         |      \                                   /
         |       \      route A (20.0 km)          /
       3 +        o------------------------------ o
         |         (9,3)
       0 +  IGNITION (0,0) ===> nominal spread east, +-30 deg wedge
         +----+----+----+----+----+----+----+----+----+---> x
              2    4    6    8   10   12   14   16

Route A is the short one, but it dips south into the corridor the fire runs
down if it holds its heading.  Route B is 11% longer and stays north.  A
protective decision maker at ``decision_time`` must pick one for the whole
community.

Why the community itself is not in the fire's path: this is an evacuation
driven by *routes being cut*, not by the town burning, which is a common and
entirely real evacuation trigger.  The cost of hesitating is therefore not
that the community burns -- it is that the escape closes while you wait.
Route B's margin under the nominal world is about 0.9 h, so a decision maker
who holds the order for an hour waiting on a late model run loses the robust
route too.  That is the mechanism by which latency costs something
*continuously*, rather than only at the instant it crosses the decision time.

The numbers are tuned so that under the nominal world the safety margin on
route A is a fraction of an hour either side of zero.  That is deliberate:
the interesting physics of forecast *value* lives near the margin, and a
scenario where route A is obviously safe or obviously fatal has no decision in
it to change.  It also means the scenario is **not** a claim about real
wildfire evacuation; it is a fixture chosen to exercise the machinery
(``docs/SCOPE.md``).

Worlds and receptors
--------------------
A :class:`World` is one fire realisation plus a community of ``n_receptors``
who leave on a staggered schedule.  Receptors inside a world share the fire
and share the action, so their outcomes are strongly dependent.  This is the
structure that makes "N worlds x M residents" a false sample size, and it is
built in rather than bolted on -- see
:mod:`wildfireguardian_forecast_value.statistics`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

import numpy as np

from wildfireguardian_forecast_value.decision_value.loss import RouteChoiceLoss
from wildfireguardian_forecast_value.outcomes import Outcome
from wildfireguardian_forecast_value.fields.front import FireSource, FireState, known_at
from wildfireguardian_forecast_value.fields.grids import RasterGrid
from wildfireguardian_forecast_value.rng import spawn
from wildfireguardian_forecast_value.synthetic_decisions.policies import DecisionContext
from wildfireguardian_forecast_value.synthetic_decisions.routes import Route, RouteSet, traverse_all

__all__ = [
    "World",
    "SpotSpec",
    "ToyEvacuationScenario",
    "default_scenario",
    "CaseSpec",
    "CASES",
    "case_specs",
]


@dataclass(frozen=True)
class World:
    """One ground-truth realisation plus the community that must evacuate it."""

    world_id: int
    truth: FireState
    departure_times: np.ndarray
    params: dict = field(default_factory=dict)

    @property
    def n_receptors(self) -> int:
        return int(np.size(self.departure_times))


@dataclass(frozen=True)
class SpotSpec:
    """Distribution of the (at most one) spot ignition in a world."""

    probability: float = 0.5
    origin: tuple[float, float] = (11.0, 6.0)
    origin_jitter_km: float = 0.6
    delay_after_ignition: float = 1.1
    delay_jitter_h: float = 0.1
    spread_rate: float = 2.0

    def to_dict(self) -> dict:
        return {
            "probability": self.probability, "origin": list(self.origin),
            "origin_jitter_km": self.origin_jitter_km,
            "delay_after_ignition": self.delay_after_ignition,
            "delay_jitter_h": self.delay_jitter_h, "spread_rate": self.spread_rate,
        }


@dataclass(frozen=True)
class ToyEvacuationScenario:
    """A two-route protective decision under an advancing synthetic fire."""

    name: str = "two_route_evacuation"
    ignition: tuple[float, float] = (0.0, 0.0)
    nominal_heading_deg: float = 5.0
    heading_sd_deg: float = 6.0
    nominal_rate: float = 6.0
    rate_sd_log: float = 0.12
    half_angle_deg: float = 30.0
    decision_time: float = 1.0
    n_receptors: int = 40
    departure_span_h: float = 0.25
    speed: float = 20.0
    community: tuple[float, float] = (2.0, 8.0)
    safe_haven: tuple[float, float] = (16.0, 12.0)
    route_a_via: tuple[float, float] = (9.0, 3.0)
    route_b_via: tuple[tuple[float, float], ...] = ((-1.0, 11.0), (16.0, 11.0))
    sample_spacing: float = 0.05
    #: Time at which footprint (categorical) skill is scored.  Explicit because
    #: categorical skill is meaningless without it, and because a horizon past
    #: the point where the fire leaves the grid saturates CSI at 1 and hides
    #: every rate error (``docs/FAILURE_MODES.md``, F-04).
    skill_horizon: float = 2.5
    spot: SpotSpec | None = field(default_factory=SpotSpec)
    loss: RouteChoiceLoss = field(default_factory=lambda: RouteChoiceLoss(burnover_loss=50.0))
    trigger_distance: float = 1.5
    grid: RasterGrid = field(
        default_factory=lambda: RasterGrid(x_min=-2.0, x_max=20.0, y_min=-4.0, y_max=18.0, nx=110, ny=110)
    )

    # -- action set --------------------------------------------------------
    @property
    def routes(self) -> RouteSet:
        """The action set.  Memoised on the scenario instance (which is frozen)."""
        cached = self.__dict__.get("_routes")
        if cached is None:
            a = Route("route_a", (self.community, self.route_a_via, self.safe_haven),
                      speed=self.speed, sample_spacing=self.sample_spacing)
            b = Route("route_b", (self.community, *self.route_b_via, self.safe_haven),
                      speed=self.speed, sample_spacing=self.sample_spacing)
            cached = RouteSet((a, b))
            object.__setattr__(self, "_routes", cached)
        return cached

    @property
    def preferred_action(self) -> str:
        """The cheaper action absent any fire -- route A, by construction."""
        return "route_a"

    @property
    def robust_action(self) -> str:
        return "route_b"

    # -- worlds ------------------------------------------------------------
    def departure_times(self) -> np.ndarray:
        """Staggered departures after the decision.

        Deterministic (evenly spaced), not random: within-world spread is a
        property of the evacuation plan, and making it deterministic keeps the
        hand-checked cases exactly reproducible while still giving receptors
        inside a world genuinely different exposures.
        """
        if self.n_receptors == 1:
            return np.array([self.decision_time], dtype=float)
        return self.decision_time + np.linspace(0.0, self.departure_span_h, self.n_receptors)

    def truth_from_params(self, params: dict) -> FireState:
        """Build the true fire state from a world's parameter dict."""
        main = FireSource(
            origin=tuple(params.get("ignition", self.ignition)),
            ignition_time=0.0,
            spread_rate=float(params["rate"]),
            heading=float(params["heading"]),
            half_angle=np.deg2rad(self.half_angle_deg),
            label="main",
            kind="primary",
        )
        sources = [main]
        if params.get("has_spot", False):
            sources.append(
                FireSource(
                    origin=tuple(params["spot_origin"]),
                    ignition_time=float(params["spot_time"]),
                    spread_rate=float(params["spot_rate"]),
                    heading=0.0,
                    half_angle=np.pi,
                    label="spot1",
                    kind="spot",
                )
            )
        return FireState(tuple(sources))

    def sample_world(self, world_id: int, seed: int) -> World:
        """Draw one world.  Worlds are independent by construction."""
        rng = spawn(seed, f"world-{world_id}")
        heading = np.deg2rad(self.nominal_heading_deg) + np.deg2rad(self.heading_sd_deg) * rng.standard_normal()
        rate = self.nominal_rate * float(np.exp(self.rate_sd_log * rng.standard_normal()))
        params: dict = {
            "heading": float(heading),
            "rate": float(rate),
            "ignition": tuple(self.ignition),
            "has_spot": False,
        }
        if self.spot is not None and rng.random() < self.spot.probability:
            jitter = self.spot.origin_jitter_km * rng.standard_normal(2)
            params.update(
                has_spot=True,
                spot_origin=(float(self.spot.origin[0] + jitter[0]), float(self.spot.origin[1] + jitter[1])),
                spot_time=float(self.spot.delay_after_ignition + self.spot.delay_jitter_h * rng.standard_normal()),
                spot_rate=float(self.spot.spread_rate),
            )
        return World(world_id=int(world_id), truth=self.truth_from_params(params),
                     departure_times=self.departure_times(), params=params)

    def sample_worlds(self, n_worlds: int, seed: int) -> list[World]:
        return [self.sample_world(i, seed) for i in range(int(n_worlds))]

    # -- decision plumbing --------------------------------------------------
    def observation(self, world: World) -> FireState:
        """What is visible at the decision time: sources that have already ignited.

        A source that ignites after ``decision_time`` cannot be observed, so it
        is removed.  Note this is the *observation*, not a forecast: policies
        may ask it for the burned area's distance, never for arrival times.
        """
        return known_at(world.truth, self.decision_time)

    def context(self, world: World, stream, with_truth: bool = False) -> DecisionContext:
        return DecisionContext(
            routes=self.routes,
            decision_time=self.decision_time,
            observation=self.observation(world),
            stream=stream,
            loss=self.loss,
            departure_times=world.departure_times,
            truth_state=world.truth if with_truth else None,
        )

    def outcomes(self, world: World, action: str, departure_delay: float = 0.0) -> list[Outcome]:
        """Realised outcomes for every receptor under ``action`` in ``world``.

        ``departure_delay`` shifts every departure later -- the physical cost
        of a decision maker who held the order waiting for a forecast.  The
        fire does not wait with them.
        """
        return traverse_all(self.routes[action], world.truth,
                            np.asarray(world.departure_times, dtype=float) + float(departure_delay))

    def realised_loss(self, world: World, action: str, loss=None,
                      departure_delay: float = 0.0) -> float:
        """World-level loss: the mean over receptors.

        The mean, not the sum: a sum would make ``Delta J`` scale with the
        (arbitrary) community size and invite the exact "thousands of
        independent events" error the statistics module exists to prevent.
        """
        lm = loss if loss is not None else self.loss
        return float(np.mean(lm.losses(self.outcomes(world, action, departure_delay))))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ignition": list(self.ignition),
            "nominal_heading_deg": self.nominal_heading_deg,
            "heading_sd_deg": self.heading_sd_deg,
            "nominal_rate": self.nominal_rate,
            "rate_sd_log": self.rate_sd_log,
            "half_angle_deg": self.half_angle_deg,
            "decision_time": self.decision_time,
            "n_receptors": self.n_receptors,
            "departure_span_h": self.departure_span_h,
            "speed": self.speed,
            "community": list(self.community),
            "safe_haven": list(self.safe_haven),
            "route_a_via": list(self.route_a_via),
            "route_b_via": [list(w) for w in self.route_b_via],
            "sample_spacing": self.sample_spacing,
            "skill_horizon": self.skill_horizon,
            "spot": self.spot.to_dict() if self.spot else None,
            "loss": self.loss.to_dict(),
            "trigger_distance": self.trigger_distance,
            "grid": self.grid.to_dict(),
            "routes": self.routes.to_dict(),
        }

    def with_(self, **changes) -> "ToyEvacuationScenario":
        return replace(self, **changes)


def default_scenario(**overrides) -> ToyEvacuationScenario:
    """The scenario used by the toy study, the figures and the tests."""
    return ToyEvacuationScenario(**overrides)


# ---------------------------------------------------------------------------
# The four cases.  Each is one deterministic world plus one forecast
# configuration, chosen so that the named phenomenon is exhibited exactly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseArm:
    """One forecast configuration evaluated inside a case."""

    label: str
    world_params: dict
    degradation_params: dict
    information_time: float
    latency: float
    expected_forecast_action: str
    expected_baseline_action: str
    #: Sign of ``Delta J = J_baseline - J_forecast``: +1 better, 0 equal, -1 worse.
    expected_delta_sign: int
    #: ``nan`` where the baseline is already optimal and the fraction is 0/0.
    expected_value_fraction: float

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "world_params": {k: (list(v) if isinstance(v, tuple) else v)
                             for k, v in self.world_params.items()},
            "degradation_params": dict(self.degradation_params),
            "information_time": self.information_time,
            "latency": self.latency,
            "expected_forecast_action": self.expected_forecast_action,
            "expected_baseline_action": self.expected_baseline_action,
            "expected_delta_sign": self.expected_delta_sign,
            "expected_value_fraction": self.expected_value_fraction,
        }


@dataclass(frozen=True)
class CaseSpec:
    """A hand-designed, deterministic demonstration.

    Each case is one or more :class:`CaseArm` s.  The expectations recorded in
    the arms are asserted by ``tests/test_cases.py``: if a change to the fire
    model, the policies or the loss breaks one, the case stops demonstrating
    what its prose claims, and the test says so rather than the claim quietly
    becoming false.
    """

    key: str
    title: str
    claim: str
    arms: tuple[CaseArm, ...]
    n_receptors: int = 40

    def scenario(self, base: "ToyEvacuationScenario | None" = None) -> "ToyEvacuationScenario":
        s = base if base is not None else default_scenario()
        return s.with_(n_receptors=self.n_receptors)

    def world(self, arm: CaseArm, base: "ToyEvacuationScenario | None" = None) -> World:
        s = self.scenario(base)
        return World(world_id=0, truth=s.truth_from_params(arm.world_params),
                     departure_times=s.departure_times(), params=dict(arm.world_params))

    def to_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "claim": self.claim,
            "n_receptors": self.n_receptors,
            "arms": [a.to_dict() for a in self.arms],
        }


_NOMINAL = {
    "heading": float(np.deg2rad(5.0)),
    "rate": 6.0,
    "ignition": (0.0, 0.0),
    "has_spot": False,
}

#: A faster world.  Here the proximity trigger fires on its own and picks the
#: correct route without any forecast, so a forecast that errs is not merely
#: valueless but actively harmful.
_FAST = {**_NOMINAL, "rate": 7.0}

#: The four canonical cases, in order.
CASES: tuple[str, ...] = ("case_1", "case_2", "case_3", "case_4")


def case_specs() -> dict[str, CaseSpec]:
    """The four cases.  See ``docs/DECISION_VALUE.md`` for the prose version.

    Read together they make the repository's central point numerically:
    ranked by footprint CSI the forecasts in these cases come out in almost
    exactly the **reverse** of their ranking by decision value.
    ``tests/test_cases.py::test_skill_ranking_is_inverted_against_value``
    asserts that inversion.
    """
    d = np.deg2rad
    return {
        "case_1": CaseSpec(
            key="case_1",
            title="Prediction metrics move; the selected action does not",
            claim=(
                "A +18 degree heading error degrades footprint skill substantially "
                "(CSI 1.00 -> 0.57, FAR 0.00 -> 0.30) while leaving arrival-time RMSE "
                "at zero on the cells both fields burn. The selected action is "
                "unchanged and the decision value is identical to that of a perfect "
                "forecast. Error that lands away from the decision boundary is "
                "invisible to the decision."
            ),
            arms=(
                CaseArm("perfect", dict(_NOMINAL), {}, 1.0, 0.0, "route_b", "route_a", +1, 1.0),
                CaseArm("heading_+18deg", dict(_NOMINAL), {"eps_theta": float(d(18.0))},
                        1.0, 0.0, "route_b", "route_a", +1, 1.0),
            ),
        ),
        "case_2": CaseSpec(
            key="case_2",
            title="A small error flips the optimal decision",
            claim=(
                "A -17 degree heading error -- one degree SMALLER in magnitude than "
                "Case 1's, and scoring BETTER on CSI (0.65 vs 0.57) and on FAR "
                "(0.10 vs 0.30) -- rotates the wedge "
                "boundary just off route A. The forecast now predicts route A safe, "
                "the decision flips to the exposed route, and every hour of value the "
                "forecast could have delivered is lost (value fraction 1.00 -> 0.00). "
                "In the faster world, where the forecast-free trigger would have "
                "picked correctly on its own, the same error makes the forecast "
                "strictly harmful: Delta J is about -50 hours."
            ),
            arms=(
                CaseArm("heading_-17deg", dict(_NOMINAL), {"eps_theta": float(d(-17.0))},
                        1.0, 0.0, "route_a", "route_a", 0, 0.0),
                CaseArm("heading_-17deg_fast_world", dict(_FAST), {"eps_theta": float(d(-17.0))},
                        1.0, 0.0, "route_a", "route_b", -1, float("nan")),
            ),
        ),
        "case_3": CaseSpec(
            key="case_3",
            title="A clearly poor forecast still makes the right call",
            claim=(
                "A forecast that is 60 percent fast, displaced 3 km, and 10 degrees "
                "off in heading scores worse than every other forecast in these cases "
                "(CSI 0.40, FAR 0.60) and still selects the correct protective action, "
                "realising 100 percent of the available decision value. Large error in "
                "a direction the decision does not resolve costs nothing."
            ),
            arms=(
                CaseArm("poor_but_decisive", dict(_NOMINAL),
                        {"eps_r": 0.60, "disp_magnitude": 3.0, "disp_heading": float(np.pi),
                         "eps_theta": float(d(10.0))},
                        1.0, 0.0, "route_b", "route_a", +1, 1.0),
            ),
        ),
        "case_4": CaseSpec(
            key="case_4",
            title="The more accurate forecast is worth less, because it is late",
            claim=(
                "Two forecasts of the same world. The first is perfect (RMSE 0, CSI "
                "1.00) but has 0.5 h of latency, so at the decision time it does not "
                "exist: the decision maker falls back to the trigger and realises zero "
                "value. The second is markedly worse (CSI 0.46) but arrives in time, "
                "and realises all of it. Latency is modelled as availability, not as a "
                "penalty on a score; a score penalty cannot produce this ordering."
            ),
            arms=(
                CaseArm("accurate_late", dict(_NOMINAL), {}, 1.0, 0.5,
                        "route_a", "route_a", 0, 0.0),
                CaseArm("degraded_timely", dict(_NOMINAL),
                        {"eps_r": 0.35, "eps_theta": float(d(9.0))}, 1.0, 0.0,
                        "route_b", "route_a", +1, 1.0),
            ),
        ),
    }
