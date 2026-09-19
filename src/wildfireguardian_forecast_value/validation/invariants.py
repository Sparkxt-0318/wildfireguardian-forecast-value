"""Runtime guards against the errors that would silently invalidate a study.

Each of these checks a property that is easy to break by accident and
impossible to notice from the output: a "baseline" that quietly reads a
forecast, a forecast that quietly knows the future, a paired comparison whose
pairs do not line up.  They raise :class:`InvariantError` rather than warning,
because a study that has violated one of them is producing numbers that mean
something other than what they are labelled.

They are cheap, and the CLI runs the whole set before any study.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from wildfireguardian_forecast_value.degradation.latency import ForecastStream

__all__ = [
    "InvariantError",
    "check_no_clairvoyance",
    "check_no_oracle_access",
    "check_baseline_is_forecast_free",
    "check_pairing",
    "check_identity_degradation",
    "check_latency_semantics",
    "run_all_invariants",
]


class InvariantError(AssertionError):
    """A structural assumption of the experiment has been violated."""


def check_no_clairvoyance(release) -> None:
    """A release may not contain a source that ignites after its information time.

    Violating this is the single most attractive bug in a study like this,
    because it makes the forecast look good in exactly the worlds where being
    good matters most (the ones with a late spot ignition).
    """
    s = release.information_time
    bad = [src.label for src in release.state.sources if src.ignition_time > s + 1e-12]
    if bad:
        raise InvariantError(
            f"forecast release {release.label!r} built from information time {s} contains "
            f"source(s) {bad} that ignite later. The release is clairvoyant. Build it with "
            f"degradation.latency.make_release(), which restricts to known_at(truth, s) first."
        )


def check_no_oracle_access(policy, ctx) -> None:
    """A non-clairvoyant policy must choose the same action with the truth removed."""
    if getattr(policy, "name", "") == "clairvoyant":
        return
    with_truth = policy.decide(ctx)
    without = policy.decide(replace(ctx, truth_state=None))
    if with_truth.action != without.action or with_truth.departure_delay != without.departure_delay:
        raise InvariantError(
            f"policy {getattr(policy, 'name', policy)!r} changes its decision when the oracle "
            f"truth state is removed ({with_truth} vs {without}). It is reading "
            "DecisionContext.truth_state, which only ClairvoyantPolicy may do."
        )


def check_baseline_is_forecast_free(policy, ctx) -> None:
    """A baseline must choose identically when every forecast release is removed."""
    if getattr(policy, "uses_forecast", False):
        raise InvariantError(
            f"policy {getattr(policy, 'name', policy)!r} is declared as forecast-using and "
            "cannot serve as the forecast-free baseline."
        )
    full = policy.decide(ctx)
    empty = policy.decide(replace(ctx, stream=ForecastStream(())))
    if full.action != empty.action or full.departure_delay != empty.departure_delay:
        raise InvariantError(
            f"baseline policy {getattr(policy, 'name', policy)!r} changes its decision when the "
            f"forecast stream is emptied ({full} vs {empty}). It is not forecast-free, so "
            "Delta J is not measuring the value of the forecast."
        )


def check_pairing(results_a, results_b) -> None:
    """Two arms of a comparison must cover the same worlds, in the same order."""
    ia = [r.world_id for r in results_a]
    ib = [r.world_id for r in results_b]
    if ia != ib:
        raise InvariantError(
            f"paired arms cover different worlds: {len(ia)} vs {len(ib)} results, "
            f"first mismatch at index {next((i for i, (x, y) in enumerate(zip(ia, ib)) if x != y), 'n/a')}. "
            "Unpaired differencing throws away the variance reduction that makes this "
            "design work and biases nothing in a way you can correct afterwards."
        )


def check_identity_degradation(pipeline, state, tol: float = 1e-12) -> None:
    """At its identity parameters a pipeline must be the identity map."""
    out = pipeline.apply(state, pipeline.identity_params())
    if out.labels != state.labels:
        raise InvariantError(
            f"pipeline at identity parameters changed the source set: "
            f"{state.labels} -> {out.labels}"
        )
    for a, b in zip(state.sources, out.sources):
        for field in ("origin", "ignition_time", "spread_rate", "heading", "half_angle"):
            va, vb = getattr(a, field), getattr(b, field)
            if not np.allclose(np.asarray(va, dtype=float), np.asarray(vb, dtype=float), atol=tol):
                raise InvariantError(
                    f"pipeline at identity parameters changed {a.label!r}.{field}: {va} -> {vb}. "
                    "Every operator must have an exact identity point, or 'no degradation' "
                    "is not a point in the sweep."
                )


def check_latency_semantics(release, decision_time: float) -> None:
    """Availability must be a step at ``s + delta``, and staleness must exceed latency."""
    a = release.availability_time
    if release.is_available_at(a - 1e-9):
        raise InvariantError(f"release {release.label!r} is available before {a}")
    if not release.is_available_at(a):
        raise InvariantError(
            f"release {release.label!r} is not available at exactly its availability time {a}; "
            "the tie convention (inclusive) has been broken"
        )
    if release.is_available_at(decision_time):
        age = release.age_at(decision_time)
        if age < release.latency - 1e-9:
            raise InvariantError(
                f"release {release.label!r} used at t={decision_time} has information age "
                f"{age} < latency {release.latency}, which is impossible"
            )


@dataclass
class InvariantReport:
    checks: tuple[str, ...]
    passed: bool = True

    def as_dict(self) -> dict:
        return {"checks": list(self.checks), "passed": self.passed}


def run_all_invariants(scenario, pipeline, policies, seed: int = 0) -> InvariantReport:
    """Run every structural check against one scenario/pipeline/policy configuration."""
    from wildfireguardian_forecast_value.degradation.latency import LatencySpec, make_release

    baseline, forecast_policy, clair = policies
    ran: list[str] = []

    world = scenario.sample_world(0, seed)
    check_identity_degradation(pipeline, world.truth)
    ran.append("identity_degradation")

    rel = make_release(world.truth, information_time=scenario.decision_time - 0.4,
                       latency=0.2, pipeline=pipeline, params=pipeline.identity_params())
    check_no_clairvoyance(rel)
    ran.append("no_clairvoyance")
    check_latency_semantics(rel, scenario.decision_time)
    ran.append("latency_semantics")

    ctx = scenario.context(world, ForecastStream((rel,)), with_truth=True)
    check_baseline_is_forecast_free(baseline, ctx)
    ran.append("baseline_is_forecast_free")
    for p in (baseline, forecast_policy):
        check_no_oracle_access(p, ctx)
    ran.append("no_oracle_access")

    return InvariantReport(tuple(ran))
