"""Decision policies.

A **policy** maps the information available at the decision time to an action.
The information set is the whole point, so it is an explicit object
(:class:`DecisionContext`) with three separate slots:

``observation``
    The fire as it can be *seen* at the decision time.  A policy may ask where
    the fire is now and how far it is from a route.  It may **not** ask when
    the fire will arrive somewhere: :meth:`FireState.arrival_time` on the
    observation would be extrapolation, i.e. a forecast, and would turn the
    "forecast-free" baseline into a forecast.  The guard
    :func:`~wildfireguardian_forecast_value.validation.invariants.check_baseline_is_forecast_free`
    exists because this is easy to violate by accident.

``stream``
    Forecast releases, each with an information time and an availability time.
    A policy may only use releases with ``s + delta <= t_d``.

``plan``
    The departure schedule -- known to the planner, not a forecast.

Policies here are all *deterministic plug-in* rules: they treat the forecast
state as if it were the truth and minimise ``J``.  That is the certainty-
equivalent decision, and it is the weakest honest way to use a deterministic
forecast.  It is **not** optimal under uncertainty, and the package does not
pretend otherwise: a risk-averse or ensemble-based policy would extract more
value from the same forecast, so every ``Delta J`` reported here is a lower
bound on what that forecast is worth to a better decision maker
(``docs/ASSUMPTIONS.md``, A-08; ``docs/FAILURE_MODES.md``, F-06).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from wildfireguardian_forecast_value.synthetic_decisions.routes import Route, RouteSet, traverse_all

__all__ = [
    "DecisionContext",
    "Decision",
    "Policy",
    "FixedActionPolicy",
    "ProximityTriggerPolicy",
    "ForecastPolicy",
    "ClairvoyantPolicy",
    "plug_in_expected_loss",
]


@dataclass(frozen=True)
class Decision:
    """What a policy decided: an action **and when the community moves**.

    ``departure_delay`` is the second half of latency semantics.  A decision
    maker who holds the evacuation order until the next model run lands does
    not suffer a penalty on a score -- they suffer a later departure, and the
    fire keeps spreading while they wait.  That cost is physical, falls out of
    the same arrival-time arithmetic as everything else, and can turn a
    correct action into a fatal one.  A policy that does not wait returns
    ``0.0`` and nothing changes.
    """

    action: str
    departure_delay: float = 0.0
    used_release_label: str = ""
    waited: bool = False

    def as_dict(self) -> dict:
        return {"action": self.action, "departure_delay": self.departure_delay,
                "used_release_label": self.used_release_label, "waited": self.waited}


@dataclass(frozen=True)
class DecisionContext:
    """Everything a policy is allowed to look at."""

    routes: RouteSet
    decision_time: float
    observation: object            # FireState visible now
    stream: object                 # ForecastStream
    loss: object                   # LossModel
    departure_times: np.ndarray    # receptor departure times (absolute hours)
    #: The true fire state.  Present only so that
    #: :class:`ClairvoyantPolicy` can compute the value-of-perfect-information
    #: bound.  **No candidate policy may read it.**  It is the last field and
    #: defaults to ``None`` so that a context built for ordinary use cannot
    #: leak it, and
    #: :func:`~wildfireguardian_forecast_value.validation.invariants.check_no_oracle_access`
    #: re-runs every non-clairvoyant policy against a context with this slot
    #: emptied and asserts the action is unchanged.
    truth_state: object | None = None

    @property
    def available_release(self):
        """Most informative release available at the decision time, or ``None``."""
        return self.stream.available_at(self.decision_time)

    def release_available_by(self, t: float):
        """Most informative release available by time ``t``, or ``None``."""
        return self.stream.available_at(float(t))


def plug_in_expected_loss(state, route: Route, departure_times, loss) -> float:
    """Mean loss over receptors if ``state`` were the truth."""
    return float(np.mean(loss.losses(traverse_all(route, state, departure_times))))


class Policy:
    """Interface: ``decide(context) -> Decision``."""

    name = "policy"
    #: True when the policy consults forecast releases.  Used by the invariant
    #: checks and reported in results so baselines cannot be mislabelled.
    uses_forecast = False

    def decide(self, ctx: DecisionContext) -> Decision:  # pragma: no cover - interface
        raise NotImplementedError

    def choose(self, ctx: DecisionContext) -> str:
        """The action only.  Convenience for callers that ignore timing."""
        return self.decide(ctx).action

    def to_dict(self) -> dict:
        return {"policy": self.name, "uses_forecast": self.uses_forecast}


@dataclass(frozen=True)
class FixedActionPolicy(Policy):
    """Always take the same action -- a climatological / standing-order baseline."""

    action: str
    name: str = "fixed_action"
    uses_forecast: bool = False

    def decide(self, ctx: DecisionContext) -> Decision:
        if self.action not in ctx.routes.actions:
            raise KeyError(f"action {self.action!r} not in {ctx.routes.actions}")
        return Decision(self.action)

    def to_dict(self) -> dict:
        return {"policy": self.name, "uses_forecast": False, "action": self.action}


@dataclass(frozen=True)
class ProximityTriggerPolicy(Policy):
    """The forecast-free baseline: a distance trigger on the *observed* fire.

    Take ``preferred_action`` (short, cheap, exposed) unless the currently
    burned area is within ``trigger_distance`` km of it, in which case take
    ``robust_action``.

    This is the honest competitor for a forecast.  It is not a straw man: it
    responds to the fire, it costs nothing to run, and for a large part of the
    error/latency plane it beats the forecast outright.  Producing that region
    -- the "trigger better" side of the primary figure -- is a result of this
    package, not a failure of it.

    Its weakness is structural, not parametric: distance now is a poor proxy
    for arrival time later when the fire is fast or the route is long.  No
    choice of ``trigger_distance`` fixes that, which is exactly why there is a
    region where the forecast wins.
    """

    preferred_action: str
    robust_action: str
    trigger_distance: float
    name: str = "proximity_trigger"
    uses_forecast: bool = False

    def __post_init__(self) -> None:
        if self.trigger_distance < 0:
            raise ValueError("trigger_distance must be >= 0")

    def decide(self, ctx: DecisionContext) -> Decision:
        route = ctx.routes[self.preferred_action]
        d = route.distance_to_burned(ctx.observation, ctx.decision_time)
        return Decision(self.robust_action if d <= self.trigger_distance else self.preferred_action)

    def to_dict(self) -> dict:
        return {
            "policy": self.name,
            "uses_forecast": False,
            "preferred_action": self.preferred_action,
            "robust_action": self.robust_action,
            "trigger_distance": self.trigger_distance,
        }


@dataclass(frozen=True)
class ForecastPolicy(Policy):
    """Plug-in minimiser over the available forecast; falls back when there is none.

    The fallback is not a detail.  A forecast that has not arrived yet does not
    make the decision maker worse informed than someone who never had one --
    it makes them *exactly* as informed.  So an unavailable forecast yields
    precisely the baseline action, and the decision value of a too-late
    forecast is exactly zero, not negative.

    Negative decision value arises the other way: when a forecast *is*
    available, is believed, and is wrong in a way the trigger was not.
    """

    fallback: Policy
    tie_break: tuple[str, ...] = ()
    #: How long the decision maker will hold the order waiting for a release
    #: that has not landed yet.  ``0`` means never wait.  Waiting is not free:
    #: departures shift by the wait and the fire does not pause.
    max_wait: float = 0.0
    name: str = "forecast_plug_in"
    uses_forecast: bool = True

    def decide(self, ctx: DecisionContext) -> Decision:
        release = ctx.available_release
        if release is not None:
            return Decision(_argmin_action(ctx, release.state, self.tie_break),
                            0.0, release.label, False)
        if self.max_wait > 0:
            later = ctx.release_available_by(ctx.decision_time + self.max_wait)
            if later is not None:
                delay = max(0.0, later.availability_time - ctx.decision_time)
                return Decision(_argmin_action(ctx, later.state, self.tie_break),
                                delay, later.label, True)
        fb = self.fallback.decide(ctx)
        return Decision(fb.action, fb.departure_delay, "", False)

    def to_dict(self) -> dict:
        return {
            "policy": self.name,
            "uses_forecast": True,
            "fallback": self.fallback.to_dict(),
            "tie_break": list(self.tie_break),
            "max_wait": self.max_wait,
        }


@dataclass(frozen=True)
class ClairvoyantPolicy(Policy):
    """Chooses with the true fire state.  Defines the value of perfect information.

    Not a candidate policy -- an upper bound.  ``J_baseline - J_clairvoyant``
    is the most any forecast could possibly be worth in a world, and reporting
    ``Delta J`` as a fraction of it keeps "this forecast adds 0.3 hours" from
    being read as large or small without a scale.
    """

    tie_break: tuple[str, ...] = ()
    name: str = "clairvoyant"
    uses_forecast: bool = False

    def decide(self, ctx: DecisionContext) -> Decision:
        if ctx.truth_state is None:
            raise ValueError(
                "ClairvoyantPolicy needs DecisionContext.truth_state; it is deliberately "
                "absent from contexts built for candidate policies."
            )
        return Decision(_argmin_action(ctx, ctx.truth_state, self.tie_break))

    def to_dict(self) -> dict:
        return {"policy": self.name, "uses_forecast": False, "clairvoyant": True}


def _argmin_action(ctx: DecisionContext, state, tie_break: tuple[str, ...]) -> str:
    losses = {r.name: plug_in_expected_loss(state, r, ctx.departure_times, ctx.loss)
              for r in ctx.routes}
    best = min(losses.values())
    tied = [a for a, v in losses.items() if v <= best + 1e-12]
    if len(tied) == 1:
        return tied[0]
    for a in tie_break:
        if a in tied:
            return a
    # Deterministic and documented: first action in the route set's order.
    for a in ctx.routes.actions:
        if a in tied:
            return a
    raise AssertionError("unreachable")  # pragma: no cover
