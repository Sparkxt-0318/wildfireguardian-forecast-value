"""Frozen benchmark fixtures.

The four constructed cases are **immutable regression fixtures**, not a
parameter space to keep tuning.  Each arm is serialised in full --- geometry,
truth, forecast, availability, skill, both actions, loss, ``Delta J``, the
hand derivation and the intended interpretation --- into
``experiments/benchmark_fixtures/``.

Why the whole record and not just the number: a stored ``Delta J`` that drifts
tells you *something* changed.  A stored record tells you **what**.  If the
route geometry moved, the geometry block differs; if the loss ratio moved, the
loss block differs; if only the answer moved, the change is in the evaluation
path and is a genuine defect.

Regeneration is deliberately a separate, explicit command
(``wg-forecast-value freeze-benchmarks --write``).  ``tests/test_benchmark_fixtures.py``
recomputes every fixture and compares; it never rewrites.  A failing fixture
test is a question to answer, not a file to refresh.

Per ``docs/CURRENT_RESULT_STATUS.md`` every value in these files is
``CONSTRUCTED_BENCHMARK``.  None of them is an empirical measurement, and the
thresholds they contain carry no operational meaning.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from wildfireguardian_forecast_value._version import __version__
from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.degradation.latency import LatencySpec, make_release
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import (
    CASES,
    case_specs,
    default_scenario,
)

__all__ = [
    "FIXTURE_DIR",
    "RESULT_STATUS",
    "build_fixture",
    "build_all_fixtures",
    "write_fixtures",
    "load_fixture",
    "fixture_path",
]

#: Where frozen fixtures live, relative to the repository root.
FIXTURE_DIR = Path("experiments/benchmark_fixtures")

#: Stamped into every fixture so a consumer cannot mistake one for a measurement.
RESULT_STATUS = "CONSTRUCTED_BENCHMARK"

#: Tolerance for comparing a recomputed fixture against a stored one.  Tight:
#: these are deterministic computations, and anything looser would let a real
#: numerical regression pass.
COMPARE_ATOL = 1e-9

_DERIVATIONS = {
    "case_1": (
        "Nominal world: ignition (0,0), heading +5 deg, spread 6 km/h, half-angle 30 deg.\n"
        "Route A dips to (9,3); its minimum bearing from the ignition is\n"
        "  atan2(3, 9) = 18.43 deg.\n"
        "The truth wedge spans [5-30, 5+30] = [-25, +35] deg, so route A is inside it and\n"
        "29 of 40 receptors are overrun. Route B stays north and is clear.\n"
        "The +18 deg arm moves the wedge to [-7, +43] deg. Route A's 18.43 deg bearing is\n"
        "still inside, so the forecast still predicts route A overrun and still selects\n"
        "route B. Cells burned by BOTH fields are at unchanged distances from a rotated\n"
        "wedge's apex, so arrival-time RMSE is exactly 0 while CSI falls to about 0.57."
    ),
    "case_2": (
        "Same nominal world. The -17 deg arm moves the wedge to [-42, +18] deg.\n"
        "Route A's minimum bearing is 18.43 deg, which is now OUTSIDE the upper edge at\n"
        "+18 deg -- by 0.43 deg. Every point of route A therefore has arrival time +inf\n"
        "in the forecast, the forecast predicts route A clear, and it selects route A.\n"
        "In truth route A is overrun: protective-action failure.\n"
        "Magnitude comparison with case 1: 17 < 18. CSI is HIGHER (0.65 vs 0.57) because\n"
        "rotating away from the assets produces fewer false-alarm cells on this grid.\n"
        "Fast-world arm: spread 7 km/h brings the observed burn within the 1.5 km trigger\n"
        "radius, so the forecast-free baseline selects route B unaided. The forecast then\n"
        "moves it to the overrun route, and Delta J is about -50 h."
    ),
    "case_3": (
        "Same nominal world, forecast degraded on three channels at once:\n"
        "  rate   r' = 6 * (1 + 0.60) = 9.6 km/h\n"
        "  origin displaced 3 km along heading+pi (backwards, away from the community)\n"
        "  heading +10 deg -> wedge [-15, +45] deg\n"
        "Route A's 18.43 deg bearing is inside [-15, +45], and the displaced, faster fire\n"
        "still reaches route A before the receptors clear it, so the forecast predicts\n"
        "route A overrun and selects route B -- the correct action. CSI about 0.40,\n"
        "the worst of any arm, with FAR about 0.60 from the enlarged footprint."
    ),
    "case_4": (
        "Same nominal world; decision time t_d = 1.0 h.\n"
        "  accurate_late:   s = 1.0, delta = 0.5 -> available at 1.5 h > 1.0 h.\n"
        "                   Not in the information set. The policy falls back to the\n"
        "                   trigger and the release's skill is irrelevant to the action.\n"
        "  degraded_timely: s = 1.0, delta = 0.0 -> available at 1.0 h <= 1.0 h.\n"
        "                   Degraded (rate +35%, heading +9 deg) yet it still places route A\n"
        "                   inside the predicted burn, so it selects route B.\n"
        "Availability is a step at s + delta, so the accurate release's Delta J is exactly\n"
        "0 -- not negative. An absent forecast leaves the decision maker exactly as they\n"
        "were, which is why a latency score penalty cannot reproduce this ordering."
    ),
}

_INTERPRETATION = {
    "case_1": (
        "Prediction metrics moved substantially and the selected action did not. "
        "Establishes that conventional skill can degrade without any decision "
        "consequence. Does NOT establish how often that happens in reality."
    ),
    "case_2": (
        "A smaller heading error with BETTER conventional skill produced a worse "
        "decision, and in the faster world a strictly harmful one. Establishes that "
        "conventional skill does not uniquely determine decision value. The specific "
        "0.43-degree geometric margin is a property of the constructed geometry and "
        "carries no operational meaning."
    ),
    "case_3": (
        "The worst-scoring forecast in the benchmark selected the correct action. "
        "Establishes that large error in a direction the decision does not resolve is "
        "decision-irrelevant."
    ),
    "case_4": (
        "An unavailable high-skill release has exactly zero decision value while a "
        "lower-skill available one has positive value. Establishes that latency must "
        "be modelled as availability, not as a penalty on a score. The 0.5 h latency "
        "is a constructed value chosen to straddle the decision time; it is not a "
        "requirement on any real system."
    ),
}


def fixture_path(case_key: str, arm_label: str, root: Path | str = ".") -> Path:
    return Path(root) / FIXTURE_DIR / f"{case_key}__{arm_label}.json"


def _jsonable(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def build_fixture(case_key: str, arm, base_scenario=None) -> dict:
    """Recompute one arm and return its complete frozen record."""
    from wildfireguardian_forecast_value.decision_value.value import evaluate_world

    scenario = base_scenario if base_scenario is not None else default_scenario()
    case = case_specs()[case_key]
    sc = case.scenario(scenario)
    world = case.world(arm, scenario)
    pipeline = standard_pipeline(p_miss=0.0)
    latency = LatencySpec(arm.information_time, arm.latency)

    release = make_release(world.truth, latency.information_time, latency.latency,
                           pipeline, arm.degradation_params)
    result = evaluate_world(sc, world, pipeline, arm.degradation_params, latency)

    return _jsonable({
        "schema_version": 1,
        "result_status": RESULT_STATUS,
        "package_version": __version__,
        "case_key": case_key,
        "case_title": case.title,
        "arm_label": arm.label,
        "declared_forecast_class": arm.forecast_class,
        "computed_forecast_class": result.forecast_class,

        "geometry": {
            "community": list(sc.community),
            "safe_haven": list(sc.safe_haven),
            "route_a_via": list(sc.route_a_via),
            "route_b_via": [list(w) for w in sc.route_b_via],
            "speed_kmh": sc.speed,
            "route_sample_spacing_km": sc.sample_spacing,
            "half_angle_deg": sc.half_angle_deg,
            "decision_time_h": sc.decision_time,
            "n_receptors": sc.n_receptors,
            "departure_span_h": sc.departure_span_h,
            "trigger_distance_km": sc.trigger_distance,
            "skill_horizon_h": sc.skill_horizon,
            "grid": sc.grid.to_dict(),
            "routes": sc.routes.to_dict(),
        },

        "truth": {
            "world_params": {k: (list(v) if isinstance(v, tuple) else v)
                             for k, v in world.params.items()},
            "state": world.truth.to_dict(),
            "departure_times_h": list(np.asarray(world.departure_times, dtype=float)),
        },

        "forecast": {
            "degradation_params": dict(arm.degradation_params),
            "pipeline": pipeline.to_dict(),
            "state": release.state.to_dict(),
        },

        "availability": {
            "information_time_h": release.information_time,
            "latency_h": release.latency,
            "availability_time_h": release.availability_time,
            "decision_time_h": sc.decision_time,
            "available_at_decision_time": bool(release.is_available_at(sc.decision_time)),
            "information_age_at_decision_h": release.age_at(sc.decision_time),
        },

        "skill_metrics": dict(result.skill),

        "actions": {
            "baseline_action": result.baseline_action,
            "forecast_aware_action": result.forecast_action,
            "future_oracle_action": result.future_oracle_action,
            "action_changed": bool(result.action_changed),
            "forecast_waited": bool(result.forecast_waited),
            "departure_delay_h": result.departure_delay,
        },

        "loss": {
            "model": sc.loss.to_dict(),
            "j_baseline": result.j_baseline,
            "j_forecast": result.j_forecast,
            "j_future_oracle": result.j_future_oracle,
        },

        "decision_value": {
            "delta_j": result.delta_j,
            "future_oracle_value": result.future_oracle_value,
            "value_fraction": (None if not np.isfinite(result.value_fraction)
                               else result.value_fraction),
            "value_fraction_is_undefined": bool(not np.isfinite(result.value_fraction)),
        },

        "expected": {
            "baseline_action": arm.expected_baseline_action,
            "forecast_aware_action": arm.expected_forecast_action,
            "delta_sign": arm.expected_delta_sign,
            "value_fraction": (None if not np.isfinite(arm.expected_value_fraction)
                               else arm.expected_value_fraction),
        },

        "hand_derivation": _DERIVATIONS[case_key],
        "expected_interpretation": _INTERPRETATION[case_key],
        "claim": case.claim,
    })


def build_all_fixtures(base_scenario=None) -> dict[str, dict]:
    """Every arm of every case, keyed ``<case>__<arm>``."""
    out: dict[str, dict] = {}
    specs = case_specs()
    for key in CASES:
        for arm in specs[key].arms:
            out[f"{key}__{arm.label}"] = build_fixture(key, arm, base_scenario)
    return out


def write_fixtures(root: Path | str = ".", base_scenario=None) -> list[Path]:
    """Write every fixture.  Explicit, and never called from the test suite."""
    root = Path(root)
    (root / FIXTURE_DIR).mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in build_all_fixtures(base_scenario).items():
        path = root / FIXTURE_DIR / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def load_fixture(name: str, root: Path | str = ".") -> dict:
    path = Path(root) / FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Frozen fixtures are committed artefacts; regenerate "
            "them deliberately with `wg-forecast-value freeze-benchmarks --write` and "
            "review the diff."
        )
    return json.loads(path.read_text(encoding="utf-8"))
