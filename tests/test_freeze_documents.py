"""The v0.1 freeze deliverables exist and say what the freeze requires.

Documents drift. These tests are the mechanism that stops a freeze commitment
from quietly becoming untrue — the same reason ``test_cases.py`` asserts claims
rather than code paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    p = ROOT / rel
    assert p.exists(), f"{rel} is a v0.1 freeze deliverable and is missing"
    return p.read_text(encoding="utf-8")


def _flat(rel: str) -> str:
    """Lower-cased with whitespace collapsed, so a claim split across a line
    break still reads as the claim."""
    return re.sub(r"[\s>*_`]+", " ", _read(rel).lower())


class TestResultStatus:
    def test_document_exists_and_classifies_everything_as_constructed(self):
        t = _read("docs/CURRENT_RESULT_STATUS.md")
        assert "CONSTRUCTED_BENCHMARK" in t
        assert "EMPIRICAL_RESULT" in t
        assert re.search(r"no result in this repository is classified\s+`?EMPIRICAL_RESULT",
                         t, re.IGNORECASE), "the document must say which it is NOT"

    def test_it_states_the_positive_claim(self):
        t = _flat("docs/CURRENT_RESULT_STATUS.md")
        assert "not sufficient" in t and "uniquely determine" in t, (
            "the document must state that conventional skill is not sufficient to "
            "uniquely determine downstream decision value"
        )

    @pytest.mark.parametrize("must_deny", [
        "prevalence", "korean", "heading accuracy", "required latency",
        "real wildfire forecast performance",
    ])
    def test_it_denies_each_unsupported_inference(self, must_deny):
        t = _flat("docs/CURRENT_RESULT_STATUS.md")
        assert must_deny in t, f"the document must explicitly deny establishing: {must_deny}"

    def test_it_lists_the_numbers_that_must_not_be_read_operationally(self):
        t = _read("docs/CURRENT_RESULT_STATUS.md")
        for value in ("1.33", "0.48", "19"):
            assert value in t, f"{value} must be listed as a constructed, non-operational value"


class TestParameterProvenance:
    def test_document_exists_and_uses_the_required_markers(self):
        t = _read("docs/PARAMETER_PROVENANCE.md")
        assert "BENCHMARK_CONSTRUCTION" in t
        assert "PREDECLARED_EMPIRICAL" in t
        assert re.search(r"nothing here is\s+`?PREDECLARED_EMPIRICAL", t, re.IGNORECASE)

    @pytest.mark.parametrize("topic", [
        "route geometry", "waiting", "heading offset", "spread rate",
        "trigger distance", "loss",
    ])
    def test_each_required_topic_has_provenance(self, topic):
        t = _read("docs/PARAMETER_PROVENANCE.md").lower()
        assert topic in t, f"provenance must cover: {topic}"

    def test_it_does_not_conceal_post_hoc_construction(self):
        t = _read("docs/PARAMETER_PROVENANCE.md").lower()
        assert "post-hoc" in t
        assert "after seeing results" in t
        assert "tuned" in t


class TestExternalInterface:
    def test_document_exists_and_defines_both_sources(self):
        t = _read("docs/EXTERNAL_EXPERIMENT_INTERFACE.md")
        assert "MAIN_EMPIRICAL_STRESS_TEST" in t
        assert "OSSE_HIDDEN_WORLD" in t

    @pytest.mark.parametrize("field_name", [
        "world_id", "event_id", "source_type", "policy_id", "forecast_id",
        "forecast_issue_time", "forecast_availability_time", "skill_metrics",
        "action", "loss", "mission_success", "failure_reason",
    ])
    def test_every_contract_field_is_documented(self, field_name):
        assert field_name in _read("docs/EXTERNAL_EXPERIMENT_INTERFACE.md")

    def test_the_documented_fields_match_the_code(self):
        from wildfireguardian_forecast_value.interfaces import REQUIRED_FIELDS

        t = _read("docs/EXTERNAL_EXPERIMENT_INTERFACE.md")
        for f in REQUIRED_FIELDS:
            assert f in t, f"{f} is required by the code but absent from the contract document"

    def test_it_says_integration_is_not_happening(self):
        t = _read("docs/EXTERNAL_EXPERIMENT_INTERFACE.md").lower()
        assert "not integrating" in t or "not integration" in t


class TestRepositoryRole:
    def test_document_exists_and_names_the_pipeline_stages(self):
        t = _read("docs/REPOSITORY_ROLE.md").lower()
        for stage in ("ingest", "align skill", "experiment grid",
                      "break-even", "export", "wildfireguardian-evaluation"):
            assert stage in t, f"the pipeline must name: {stage}"

    @pytest.mark.parametrize("not_owned", [
        "nature-model simulation", "production wildfire forecasting",
        "assisted mission search", "historical evidence retrieval",
        "final statistical inference",
    ])
    def test_each_non_responsibility_is_disclaimed(self, not_owned):
        assert not_owned in _read("docs/REPOSITORY_ROLE.md").lower()

    def test_it_forbids_growing_the_local_statistics_package(self):
        t = _read("docs/REPOSITORY_ROLE.md").lower()
        assert "does not grow" in t or "must not be added" in t
        assert "pseudoreplication" in t, (
            "the lightweight diagnostic that is explicitly retained must be named"
        )


class TestFreezeReport:
    def test_report_exists(self):
        _read("reports/V0_1_FREEZE_REPORT.md")

    @pytest.mark.parametrize("n", range(1, 11))
    def test_all_ten_questions_are_answered(self, n):
        t = _read("reports/V0_1_FREEZE_REPORT.md")
        assert re.search(rf"^##\s*{n}\.", t, re.MULTILINE), (
            f"freeze report question {n} is missing a top-level section"
        )


class TestReadmeCarriesTheStatus:
    def test_readme_leads_with_the_classification(self):
        t = _read("README.md")
        head = t[:4000]
        assert "CONSTRUCTED_BENCHMARK" in head
        assert "do **not** establish" in head or "do not establish" in head
        assert "CURRENT_RESULT_STATUS.md" in head

    def test_readme_flags_the_numeric_breakpoints_as_constructed(self):
        t = _read("README.md")
        assert "properties of the constructed geometry" in t
        assert "must not be read as operational requirements" in t


class TestNoPerfectForecastLanguage:
    """The ambiguous phrase is gone from prose except where it is being retired."""

    #: Lines that are *retiring* the phrase, rather than using it.
    ALLOWED = ("forecast_classes", "ambiguous", "renamed", "previously called",
               "appears nowhere", "has been removed", "no longer", "retired",
               "deprecated alias")

    def test_prose_does_not_use_perfect_forecast_loosely(self):
        offenders = []
        for pattern in ("*.md", "docs/*.md", "tasks/*.md", "reports/*.md"):
            for p in ROOT.glob(pattern):
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    low = line.lower()
                    if "perfect forecast" in low or "perfect information" in low:
                        if not any(a in low for a in self.ALLOWED):
                            offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not offenders, (
            "use one of PRESENT_STATE_ORACLE / CONDITIONAL_FORECAST / "
            "DEGRADED_FORECAST / FUTURE_ORACLE instead:\n  " + "\n  ".join(offenders)
        )


class TestNoUnsupportedMortalityLanguage:
    FORBIDDEN = re.compile(
        r"\b(fatal|fatalit\w*|death\w*|died|dies|killed|lives saved|casualt\w*|mortality)\b",
        re.IGNORECASE,
    )
    #: A line stating the rule is not a violation of it.
    META = ("mortality language", "models mortality", "mortality is not modelled")

    def test_no_prose_file_uses_mortality_language(self):
        offenders = []
        for pattern in ("*.md", "docs/*.md", "tasks/*.md", "reports/*.md",
                        "experiments/manifests/*.md"):
            for p in ROOT.glob(pattern):
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if self.FORBIDDEN.search(line) and not any(
                            m in line.lower() for m in self.META):
                        offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not offenders, (
            "nothing in this package models mortality; use protective-action "
            "failure / route failure / high-loss action / mission failure:\n  "
            + "\n  ".join(offenders)
        )

    def test_no_source_file_uses_mortality_language(self):
        offenders = []
        for p in (ROOT / "src").rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if self.FORBIDDEN.search(line):
                    offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not offenders, "\n  ".join(offenders)
