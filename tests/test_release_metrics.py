"""No count in this repository's prose may be hand-maintained.

The repository previously carried both "275 tests" and "277 tests" in
different documents, and neither matched what pytest reported. The fix is
structural: counts live in one generated file and every other document links
to it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wildfireguardian_forecast_value.cli.metrics import (
    RepositoryMetrics,
    collect_metrics,
    parse_collected,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "reports" / "generated_metrics.md"

#: Prose patterns that mean somebody typed a count.
_HAND_COUNT = re.compile(
    r"\b\d{2,}\s+(?:tests?|test\s+cases?|assertions?)\b"
    r"|\btests?\s*[:=]\s*\d{2,}\b"
    r"|\b\d{2,}\s+tests?\s+(?:pass|passing|total)\b",
    re.IGNORECASE,
)


def _prose_files():
    for pattern in ("*.md", "docs/*.md", "tasks/*.md", "reports/*.md",
                    "experiments/manifests/*.md"):
        for p in ROOT.glob(pattern):
            if p.resolve() == GENERATED.resolve():
                continue
            yield p


class TestParsing:
    def test_plain_count(self):
        assert parse_collected("278 tests collected in 0.42s") == 278

    def test_marker_filtered_count_uses_the_selected_number(self):
        """`-m slow` prints `N/M tests collected`; N is what was selected."""
        assert parse_collected("3/278 tests collected (275 deselected) in 0.4s") == 3

    def test_singular(self):
        assert parse_collected("1 test collected in 0.1s") == 1

    def test_zero(self):
        assert parse_collected("no tests ran in 0.01s") == 0

    def test_unparseable_raises_rather_than_guessing(self):
        with pytest.raises(ValueError, match="could not find a test count"):
            parse_collected("something went wrong")


class TestHygiene:
    def test_no_prose_file_states_a_test_count(self):
        offenders = []
        for p in _prose_files():
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if _HAND_COUNT.search(line):
                    offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not offenders, (
            "hand-maintained counts found; link to reports/generated_metrics.md "
            "instead:\n  " + "\n  ".join(offenders)
        )

    def test_generated_metrics_exists_and_is_marked_generated(self):
        assert GENERATED.exists(), (
            "reports/generated_metrics.md is missing; run `wg-forecast-value release-metrics`"
        )
        text = GENERATED.read_text(encoding="utf-8")
        assert "GENERATED FILE" in text
        assert "do not edit by hand" in text.lower()

    def test_generated_json_is_consistent_with_the_markdown(self):
        js = json.loads((ROOT / "reports" / "generated_metrics.json").read_text(encoding="utf-8"))
        md = GENERATED.read_text(encoding="utf-8")
        assert f"`{js['tests_collected']}`" in md
        assert js["tests_collected"] > 0

    def test_collector_measures_the_non_test_counts_without_running_pytest(self):
        """The cheap half of the collector must work without spawning pytest."""
        m = collect_metrics(ROOT, run_pytest=False)
        assert isinstance(m, RepositoryMetrics)
        assert m.tests_collected == -1          # sentinel for "not measured"
        assert m.hand_solvable_examples >= 13
        assert m.benchmark_cases == 4
        assert m.frozen_benchmark_fixtures == m.benchmark_case_arms
        assert m.documented_assumptions >= 15
        assert m.documented_failure_modes >= 15
