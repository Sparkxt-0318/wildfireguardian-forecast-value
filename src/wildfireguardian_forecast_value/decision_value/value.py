"""Decision value: ``Delta J`` under paired worlds.

For one world ``omega`` the package computes three losses:

    J_base(omega)   = J(a_base(omega), omega)      forecast-free policy
    J_fc(omega)     = J(a_fc(omega),   omega)      forecast-informed policy
    J_clair(omega)  = J(a*(omega),     omega)      best action in hindsight

and reports

    Delta J(omega)  = J_base(omega) - J_fc(omega)          (>0: forecast helped)
    VPI(omega)      = J_base(omega) - J_clair(omega)       (value of perfect info)
    fraction(omega) = Delta J / VPI                        (when VPI > 0)

**Paired worlds.**  Both policies are run against the *same* realisation --
same fire, same receptors, same departure schedule.  The only thing that
differs is the information the policy had.  Pairing removes world-to-world
variance, which is enormous here (whether route A is overrun at all swamps
everything else), and it is what makes a few hundred worlds informative
instead of a few hundred thousand.  Every statistic downstream is a statistic
of the paired difference ``Delta J``, never of ``J_base`` and ``J_fc``
separately.

**The fraction, not just the difference.**  ``Delta J = 0.3 hours`` is
meaningless without knowing whether perfect information was worth 0.31 hours
or 31.  ``fraction`` is reported wherever ``VPI > 0``, and is ``nan`` where the
baseline is already optimal -- a world where perfect information is worth
nothing is a world that says nothing about a forecast, and averaging a 0/0
into the headline as "0% of value realised" would be a lie about a world that
never had an opinion.

**Skill is computed but never consulted.**  Each record also carries
arrival-time and categorical skill of the forecast against the truth.  Nothing
in the decision path reads those columns.  They are there so a study can
regress value on skill and find, as it does, that the relationship is not a
function.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from wildfireguardian_forecast_value.degradation.latency import (
    ForecastRelease,
    ForecastStream,
    LatencySpec,
    make_release,
)
from wildfireguardian_forecast_value.fields.front import FireState
from wildfireguardian_forecast_value.skill_metrics.categorical import categorical_scores
from wildfireguardian_forecast_value.skill_metrics.continuous import (
    angular_error,
    arrival_time_metrics,
)
from wildfireguardian_forecast_value.synthetic_decisions.policies import (
    ClairvoyantPolicy,
    ForecastPolicy,
    Policy,
    ProximityTriggerPolicy,
)

__all__ = [
    "WorldResult",
    "default_policies",
    "evaluate_world",
    "run_paired_study",
    "results_to_frame",
]


@dataclass
class WorldResult:
    """One world's paired comparison, plus the skill of the forecast it used."""

    world_id: int
    baseline_action: str
    forecast_action: str
    clairvoyant_action: str
    j_baseline: float
    j_forecast: float
    j_clairvoyant: float
    delta_j: float
    vpi: float
    value_fraction: float
    action_changed: bool
    forecast_available: bool
    #: True when the forecast policy held the order waiting for a late release.
    forecast_waited: bool
    #: Hours by which the forecast policy delayed departures while waiting.
    departure_delay: float
    information_time: float
    latency: float
    decision_time: float
    age_of_information: float
    n_receptors: int
    #: Receptor-level losses under each policy's chosen action, same order as
    #: ``world.departure_times``.  Kept so the statistics module can show what
    #: within-world clustering does to a naive standard error.
    receptor_delta: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))
    skill: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("receptor_delta", "skill", "params")}
        d.update({f"skill_{k}": v for k, v in self.skill.items()})
        d.update({f"param_{k}": v for k, v in self.params.items()
                  if isinstance(v, (int, float, bool, str))})
        return d


def default_policies(scenario, max_wait: float = 0.0) -> tuple[Policy, Policy, Policy]:
    """``(baseline, forecast, clairvoyant)`` for a toy scenario.

    ``max_wait`` is how long the forecast-informed decision maker will hold the
    evacuation order for a release that has not landed.  It defaults to ``0``
    -- never wait -- which is the configuration the four cases use, so that
    Case 4 shows the availability cliff on its own.  The frontier study uses a
    positive ``max_wait``, because that is what turns latency from a single
    cliff into a cost that grows continuously (the escape route closes while
    you wait).
    """
    baseline = ProximityTriggerPolicy(
        preferred_action=scenario.preferred_action,
        robust_action=scenario.robust_action,
        trigger_distance=scenario.trigger_distance,
    )
    forecast = ForecastPolicy(fallback=baseline, tie_break=(scenario.preferred_action,),
                              max_wait=float(max_wait))
    return baseline, forecast, ClairvoyantPolicy(tie_break=(scenario.preferred_action,))


def _forecast_skill(scenario, truth: FireState, forecast: FireState, horizon: float) -> dict:
    """Traditional skill of ``forecast`` against ``truth`` on the scenario grid."""
    pts = scenario.grid.flat_centres()
    t_true = truth.arrival_time(pts)
    t_fc = forecast.arrival_time(pts)
    at = arrival_time_metrics(t_true, t_fc, horizon=horizon)
    cat = categorical_scores(t_true <= horizon, t_fc <= horizon)
    out = {
        "arrival_mae": at.mae,
        "arrival_rmse": at.rmse,
        "arrival_bias": at.bias,
        "arrival_coverage": at.coverage,
        "n_miss_cells": at.n_miss,
        "n_false_cells": at.n_false,
        "csi": cat["csi"],
        "pod": cat["pod"],
        "far": cat["far"],
        "frequency_bias": cat["frequency_bias"],
        "horizon": float(horizon),
    }
    # Parameter-space skill of the main source, when both states have one.
    try:
        tm, fm = truth.by_label("main"), forecast.by_label("main")
    except KeyError:
        out.update(heading_error_deg=np.nan, rate_ratio=np.nan, origin_error_km=np.nan)
    else:
        out["heading_error_deg"] = float(np.rad2deg(angular_error(fm.heading, tm.heading)))
        out["rate_ratio"] = float(fm.spread_rate / tm.spread_rate)
        out["origin_error_km"] = float(np.linalg.norm(np.subtract(fm.origin, tm.origin)))
    out["n_spots_truth"] = len(truth.of_kind("spot"))
    out["n_spots_forecast"] = len(forecast.of_kind("spot"))
    return out


def evaluate_world(
    scenario,
    world,
    pipeline=None,
    params: dict | None = None,
    latency: LatencySpec | None = None,
    policies: tuple[Policy, Policy, Policy] | None = None,
    loss=None,
    skill_horizon: float | None = None,
    extra_releases: tuple[ForecastRelease, ...] = (),
    compute_skill: bool = True,
) -> WorldResult:
    """Run the paired comparison for one world.

    ``pipeline``/``params`` degrade the forecast; ``latency`` sets its
    information and availability times.  ``extra_releases`` lets a study put
    more than one product in the stream (a fast-coarse and a slow-fine one,
    say), which is how Case 4 is staged.
    """
    lat = latency if latency is not None else LatencySpec(scenario.decision_time, 0.0)
    lm = loss if loss is not None else scenario.loss
    baseline, forecast_policy, clair = policies if policies is not None else default_policies(scenario)

    release = make_release(
        truth=world.truth,
        information_time=lat.information_time,
        latency=lat.latency,
        pipeline=pipeline,
        params=params,
    )
    stream = ForecastStream((release, *extra_releases))

    ctx = scenario.context(world, stream, with_truth=False)
    ctx_oracle = scenario.context(world, stream, with_truth=True)

    d_base = baseline.decide(ctx)
    d_fc = forecast_policy.decide(ctx)
    d_clair = clair.decide(ctx_oracle)
    a_base, a_fc, a_clair = d_base.action, d_fc.action, d_clair.action

    # One realised-loss evaluation per distinct action, not per policy: the
    # three policies frequently agree and the fire model is the expensive part.
    # Keyed by (action, departure delay): a policy that waited for a late
    # release faces a different physical world from one that left on time,
    # even when both chose the same route.
    realised: dict[tuple[str, float], np.ndarray] = {}
    for d in (d_base, d_fc, d_clair):
        key = (d.action, float(d.departure_delay))
        if key not in realised:
            realised[key] = lm.losses(scenario.outcomes(world, d.action, d.departure_delay))
    k_base = (a_base, float(d_base.departure_delay))
    k_fc = (a_fc, float(d_fc.departure_delay))
    k_clair = (a_clair, float(d_clair.departure_delay))
    j_base = float(np.mean(realised[k_base]))
    j_fc = float(np.mean(realised[k_fc]))
    j_clair = float(np.mean(realised[k_clair]))

    vpi = j_base - j_clair
    delta = j_base - j_fc
    frac = float(delta / vpi) if vpi > 1e-12 else float("nan")

    base_losses, fc_losses = realised[k_base], realised[k_fc]

    used = stream.available_at(scenario.decision_time)
    if used is None and d_fc.used_release_label:
        used = stream.available_at(scenario.decision_time + getattr(forecast_policy, "max_wait", 0.0))
    horizon = (skill_horizon if skill_horizon is not None
               else getattr(scenario, "skill_horizon", scenario.decision_time + 1.5))
    # Skill is the most expensive thing here (a full raster) and is never read
    # by the decision path, so a sweep that does not need it can switch it off.
    skill = _forecast_skill(scenario, world.truth, release.state, horizon) if compute_skill else {}
    skill["release_used"] = used.label if used is not None else ""

    return WorldResult(
        world_id=world.world_id,
        baseline_action=a_base,
        forecast_action=a_fc,
        clairvoyant_action=a_clair,
        j_baseline=float(j_base),
        j_forecast=float(j_fc),
        j_clairvoyant=float(j_clair),
        delta_j=float(delta),
        vpi=float(vpi),
        value_fraction=frac,
        action_changed=bool(a_base != a_fc),
        forecast_available=bool(used is not None),
        forecast_waited=bool(d_fc.waited),
        departure_delay=float(d_fc.departure_delay),
        information_time=float(lat.information_time),
        latency=float(lat.latency),
        decision_time=float(scenario.decision_time),
        age_of_information=float(scenario.decision_time - lat.information_time),
        n_receptors=int(world.n_receptors),
        receptor_delta=np.asarray(base_losses - fc_losses, dtype=float),
        skill=skill,
        params={k: v for k, v in world.params.items() if not isinstance(v, (tuple, list))},
    )


def run_paired_study(
    scenario,
    n_worlds: int,
    seed: int,
    pipeline=None,
    error_model=None,
    fixed_params: dict | None = None,
    latency: LatencySpec | None = None,
    policies=None,
    loss=None,
    skill_horizon: float | None = None,
) -> list[WorldResult]:
    """Evaluate ``n_worlds`` independent worlds under one forecast configuration.

    Exactly one of ``error_model`` (draw a fresh correlated error vector per
    world) or ``fixed_params`` (the same deterministic degradation in every
    world) should be supplied.  The two answer different questions: the first
    is "what is this forecast *system* worth", the second is "what is an error
    of exactly this size worth", and only the second belongs on a frontier
    axis.
    """
    if error_model is not None and fixed_params:
        raise ValueError("supply error_model or fixed_params, not both")
    worlds = scenario.sample_worlds(n_worlds, seed)
    if error_model is not None:
        draws = error_model.sample_records(n_worlds, seed=seed + 1 if isinstance(seed, int) else seed)
    else:
        draws = [dict(fixed_params or {}) for _ in range(n_worlds)]
    return [
        evaluate_world(
            scenario, w, pipeline=pipeline, params=draws[i], latency=latency,
            policies=policies, loss=loss, skill_horizon=skill_horizon,
        )
        for i, w in enumerate(worlds)
    ]


def results_to_frame(results) -> pd.DataFrame:
    """Tidy one row per world.  This is the unit of analysis, and the only one."""
    df = pd.DataFrame([r.as_row() for r in results])
    df.attrs["unit_of_analysis"] = "world"
    return df
