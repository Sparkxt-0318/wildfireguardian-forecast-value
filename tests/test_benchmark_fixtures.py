"""The frozen benchmark fixtures are a regression boundary.

These tests **recompute** every fixture and compare against the committed
record. They never rewrite it. A failure here means the evaluation path
produces a different answer than the one this repository froze and documented,
which is a question to answer rather than a file to refresh.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from wildfireguardian_forecast_value.benchmark_fixtures import (
    FIXTURE_DIR,
    RESULT_STATUS,
    build_all_fixtures,
    fixture_path,
    load_fixture,
)
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import CASES, case_specs

ROOT = Path(__file__).resolve().parents[1]
NAMES = [f"{k}__{a.label}" for k in CASES for a in case_specs()[k].arms]


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        where = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, where + "."))
        else:
            out[where] = v
    return out


@pytest.fixture(scope="module")
def rebuilt():
    return build_all_fixtures()


def test_every_arm_has_a_committed_fixture():
    missing = [n for n in NAMES if not fixture_path(*n.split("__", 1), root=ROOT).exists()]
    assert not missing, (
        f"no frozen fixture for {missing}. Every benchmark arm must be frozen; "
        "run `wg-forecast-value freeze-benchmarks --write`."
    )


def test_no_orphan_fixtures():
    on_disk = sorted(p.stem for p in (ROOT / FIXTURE_DIR).glob("*.json"))
    assert on_disk == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_reproduces_exactly(name, rebuilt):
    stored = _flatten(load_fixture(name, ROOT))
    fresh = _flatten(rebuilt[name])
    ignore = {"package_version"}
    for key in sorted(set(stored) | set(fresh)):
        if key in ignore:
            continue
        a, b = stored.get(key, "<absent>"), fresh.get(key, "<absent>")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
                and not isinstance(a, bool) and not isinstance(b, bool):
            assert np.isclose(a, b, rtol=0.0, atol=1e-9, equal_nan=True), \
                f"{name}: {key} drifted {a!r} -> {b!r}"
        else:
            assert a == b, f"{name}: {key} changed {a!r} -> {b!r}"


@pytest.mark.parametrize("name", NAMES)
def test_fixture_is_labelled_as_constructed(name):
    d = load_fixture(name, ROOT)
    assert d["result_status"] == RESULT_STATUS == "CONSTRUCTED_BENCHMARK", (
        "a benchmark fixture must never present itself as an empirical result"
    )


@pytest.mark.parametrize("name", NAMES)
def test_fixture_records_everything_the_freeze_requires(name):
    d = load_fixture(name, ROOT)
    for block in ("geometry", "truth", "forecast", "availability", "skill_metrics",
                  "actions", "loss", "decision_value", "expected"):
        assert block in d and d[block] != {}, f"{name}: missing {block}"
    assert d["actions"]["baseline_action"]
    assert d["actions"]["forecast_aware_action"]
    assert isinstance(d["decision_value"]["delta_j"], (int, float))
    assert d["availability"]["availability_time_h"] == pytest.approx(
        d["availability"]["information_time_h"] + d["availability"]["latency_h"])
    assert len(d["hand_derivation"].strip().splitlines()) >= 4, "derivation is a gesture"
    assert len(d["expected_interpretation"]) > 80


@pytest.mark.parametrize("name", NAMES)
def test_declared_and_computed_forecast_class_agree(name):
    d = load_fixture(name, ROOT)
    assert d["declared_forecast_class"] == d["computed_forecast_class"], (
        f"{name}: the arm declares {d['declared_forecast_class']} but the release "
        f"computes as {d['computed_forecast_class']}"
    )
    assert d["declared_forecast_class"] != "FUTURE_ORACLE", (
        "no benchmark arm may be a future oracle; that is the denominator, not a forecast"
    )


@pytest.mark.parametrize("name", NAMES)
def test_fixture_matches_its_declared_expectations(name):
    d = load_fixture(name, ROOT)
    assert d["actions"]["baseline_action"] == d["expected"]["baseline_action"]
    assert d["actions"]["forecast_aware_action"] == d["expected"]["forecast_aware_action"]
    assert int(np.sign(round(d["decision_value"]["delta_j"], 9))) == d["expected"]["delta_sign"]


def test_fixtures_are_valid_json_with_a_schema_version():
    for name in NAMES:
        raw = (ROOT / FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
        d = json.loads(raw)
        assert d["schema_version"] == 1
