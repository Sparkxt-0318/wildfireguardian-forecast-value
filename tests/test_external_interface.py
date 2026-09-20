"""The external input contract.

Defining the contract is not integrating the producers: nothing in
``interfaces/`` reaches out to another repository, and these tests assert that
too.
"""

from __future__ import annotations

import json

import pytest

from wildfireguardian_forecast_value.interfaces import (
    REQUIRED_FIELDS,
    SOURCE_TYPES,
    ExperimentRecord,
    RecordValidationError,
    read_records,
    records_to_frame,
    validate_records,
)

BASE = dict(
    world_id="w-1", event_id="e-1", source_type="OSSE_HIDDEN_WORLD",
    policy_id="forecast_plug_in", forecast_id="fx-1",
    forecast_issue_time=0.6, forecast_availability_time=1.1,
    skill_metrics={"csi": 0.61}, action="route_a", loss=51.0,
    mission_success=False, failure_reason="route_failure",
    decision_time=1.0, loss_units="hours_equivalent_delay",
)


def rec(**over) -> ExperimentRecord:
    return ExperimentRecord(**{**BASE, **over})


class TestShape:
    def test_required_fields_are_the_documented_ones(self):
        assert REQUIRED_FIELDS == (
            "world_id", "event_id", "source_type", "policy_id",
            "forecast_id", "forecast_issue_time", "forecast_availability_time",
            "skill_metrics", "action", "loss", "mission_success", "failure_reason",
        )

    def test_source_types_are_closed(self):
        assert set(SOURCE_TYPES) == {
            "MAIN_EMPIRICAL_STRESS_TEST", "OSSE_HIDDEN_WORLD", "CONSTRUCTED_BENCHMARK",
        }

    def test_round_trip(self):
        r = rec()
        assert ExperimentRecord.from_dict(r.to_dict()) == r

    def test_unknown_fields_are_preserved_not_dropped(self):
        d = {**BASE, "producer_build": "abc123"}
        r = ExperimentRecord.from_dict(d)
        assert r.extra["producer_build"] == "abc123"

    def test_missing_required_field_names_it(self):
        d = dict(BASE)
        d.pop("world_id")
        with pytest.raises(RecordValidationError, match="world_id"):
            ExperimentRecord.from_dict(d)


class TestTheFourConstraints:
    def test_1_world_id_is_mandatory_and_non_empty(self):
        with pytest.raises(RecordValidationError, match="world_id"):
            rec(world_id="")

    def test_2_both_clocks_or_neither(self):
        with pytest.raises(RecordValidationError, match="together"):
            rec(forecast_availability_time=None)
        with pytest.raises(RecordValidationError, match="together"):
            rec(forecast_issue_time=None)

    def test_2_availability_may_not_precede_issue(self):
        with pytest.raises(RecordValidationError, match="before it was made"):
            rec(forecast_issue_time=1.0, forecast_availability_time=0.5)

    def test_2_a_forecast_free_record_carries_no_forecast_id(self):
        r = rec(forecast_id=None, forecast_issue_time=None,
                forecast_availability_time=None, policy_id="trigger",
                skill_metrics={}, mission_success=True, failure_reason=None, loss=1.25)
        assert r.latency is None
        with pytest.raises(RecordValidationError, match="issue and availability"):
            rec(forecast_issue_time=None, forecast_availability_time=None)

    def test_3_availability_is_unknowable_without_a_decision_time(self):
        """`None`, not `False`: absence of evidence is not evidence of absence."""
        assert rec(decision_time=None).was_available() is None
        assert rec(decision_time=1.0).was_available() is False
        assert rec(decision_time=1.5).was_available() is True

    def test_4_a_failed_record_must_say_why(self):
        with pytest.raises(RecordValidationError, match="must say why"):
            rec(mission_success=False, failure_reason=None)

    def test_4_a_successful_record_may_not_carry_a_failure_reason(self):
        with pytest.raises(RecordValidationError, match="failure_reason"):
            rec(mission_success=True, failure_reason="route_failure")


class TestDerivedQuantities:
    def test_latency_is_availability_minus_issue(self):
        assert rec().latency == pytest.approx(0.5)

    def test_staleness_is_not_latency(self):
        r = rec(forecast_issue_time=0.2, forecast_availability_time=0.3, decision_time=1.0)
        assert r.latency == pytest.approx(0.1)
        assert r.information_age_at_decision() == pytest.approx(0.8)
        assert r.information_age_at_decision() > r.latency

    def test_staleness_needs_a_decision_time(self):
        assert rec(decision_time=None).information_age_at_decision() is None


class TestValidationDetail:
    def test_bad_source_type_is_rejected(self):
        with pytest.raises(RecordValidationError, match="source_type"):
            rec(source_type="SOMEWHERE_ELSE")

    def test_non_numeric_skill_metric_is_rejected(self):
        with pytest.raises(RecordValidationError, match="skill_metrics"):
            rec(skill_metrics={"csi": "high"})

    def test_bool_is_not_a_number(self):
        with pytest.raises(RecordValidationError, match="skill_metrics"):
            rec(skill_metrics={"csi": True})

    def test_bad_forecast_class_is_rejected(self):
        with pytest.raises(RecordValidationError, match="forecast_class"):
            rec(forecast_class="PERFECT_FORECAST")

    def test_good_forecast_class_is_accepted(self):
        assert rec(forecast_class="DEGRADED_FORECAST").forecast_class == "DEGRADED_FORECAST"

    def test_batch_validation_names_the_row(self):
        with pytest.raises(RecordValidationError, match="record 1:"):
            validate_records([BASE, {**BASE, "source_type": "NOPE"}])


class TestIO:
    def test_jsonl_round_trip(self, tmp_path):
        p = tmp_path / "run.jsonl"
        good = {**BASE, "policy_id": "trigger", "forecast_id": None,
                "forecast_issue_time": None, "forecast_availability_time": None,
                "skill_metrics": {}, "mission_success": True, "failure_reason": None}
        p.write_text("\n".join([json.dumps(good), "", json.dumps(BASE)]), encoding="utf-8")
        out = list(read_records(p))
        assert len(out) == 2
        assert out[0].policy_id == "trigger"

    def test_a_malformed_line_names_the_file_and_line(self, tmp_path):
        p = tmp_path / "run.jsonl"
        p.write_text(json.dumps(BASE) + "\n" + json.dumps({**BASE, "loss": "lots"}),
                     encoding="utf-8")
        with pytest.raises(RecordValidationError, match=r"run\.jsonl:2"):
            list(read_records(p))

    def test_frame_tags_the_unit_of_analysis(self):
        df = records_to_frame([rec(), rec(policy_id="trigger", forecast_id=None,
                                          forecast_issue_time=None,
                                          forecast_availability_time=None,
                                          skill_metrics={}, mission_success=True,
                                          failure_reason=None, loss=1.25)])
        assert df.attrs["unit_of_analysis"] == "world"
        assert "skill_csi" in df.columns
        assert "latency" in df.columns and "was_available" in df.columns
        assert df["world_id"].nunique() == 1, "a paired pair shares one world"


class TestNoIntegration:
    def test_the_interface_does_not_import_another_repository(self):
        """The freeze forbids integration; the contract may only describe it."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        for path in (root / "src" / "wildfireguardian_forecast_value" / "interfaces").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("import wildfireguardian_osse", "from wildfireguardian_osse",
                              "import wildfireguardian_evaluation",
                              "from wildfireguardian_evaluation",
                              "import wildfireguardian_benchmarks"):
                assert forbidden not in text, f"{path.name} integrates: {forbidden}"
