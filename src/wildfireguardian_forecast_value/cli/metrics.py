"""Release metrics, collected rather than hand-maintained.

Counts that appear in prose rot.  This repository previously carried both
"275 tests" and "277 tests" in different documents, neither of which was the
number pytest would report, because both were typed by hand at different
moments.

So no document states a count.  :func:`collect_metrics` measures the
repository and writes ``reports/generated_metrics.md`` and
``reports/generated_metrics.json``; every other document links to it.
``tests/test_release_metrics.py`` fails if a hand-maintained count reappears
in prose.

The test count comes from ``pytest --collect-only``, which is the same
collection the suite itself runs, so it cannot disagree with reality the way
a typed number can.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["RepositoryMetrics", "collect_metrics", "count_collected_tests", "write_metrics"]

# pytest prints "N tests collected" normally and "N/M tests collected (K
# deselected)" when a marker filter applies. The selected count is N in both,
# so the two-number form must be tried first or a filtered run reports the
# unfiltered total.
_COLLECTED_SELECTED = re.compile(r"(\d+)/(\d+)\s+tests?\s+collected", re.IGNORECASE)
_COLLECTED = re.compile(r"(\d+)\s+tests?\s+collected", re.IGNORECASE)


def parse_collected(output: str) -> int:
    """Extract the collected-test count from pytest's ``--collect-only -q`` output.

    Kept as a pure function so it can be unit-tested without spawning pytest
    inside pytest.
    """
    m = _COLLECTED_SELECTED.search(output)
    if m:
        return int(m.group(1))
    m = _COLLECTED.search(output)
    if m:
        return int(m.group(1))
    if re.search(r"no tests ran|collected 0 items", output, re.IGNORECASE):
        return 0
    # Fall back to counting node ids, which -q prints one per line.
    nodes = [ln for ln in output.splitlines() if "::" in ln and not ln.startswith(" ")]
    if nodes:
        return len(nodes)
    raise ValueError(f"could not find a test count in pytest output:\n{output[-2000:]}")


def count_collected_tests(root: Path) -> tuple[int, int]:
    """``(total, slow)`` collected tests, measured by running pytest's collector."""
    def _run(extra: list[str]) -> str:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra],
            cwd=str(root), capture_output=True, text=True, timeout=300,
        )
        return proc.stdout + proc.stderr

    total = parse_collected(_run([]))
    slow = parse_collected(_run(["-m", "slow"]))
    return total, slow


@dataclass
class RepositoryMetrics:
    generated_at_utc: str
    package_version: str
    tests_collected: int
    tests_marked_slow: int
    hand_solvable_examples: int
    structural_invariants: int
    frozen_benchmark_fixtures: int
    degradation_operators: int
    documented_assumptions: int
    documented_failure_modes: int
    documented_decisions: int
    benchmark_cases: int
    benchmark_case_arms: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def as_markdown(self) -> str:
        d = self.as_dict()
        rows = "\n".join(
            f"| {k.replace('_', ' ')} | `{v}` |"
            for k, v in d.items() if k not in ("notes", "generated_at_utc")
        )
        notes = "\n".join(f"* {n}" for n in self.notes)
        return f"""# Generated repository metrics

<!-- GENERATED FILE -- do not edit by hand.
     Regenerate with:  wg-forecast-value release-metrics  -->

Generated `{self.generated_at_utc}`.

Every count below is **measured**, not typed. No other document in this
repository states a test count; they link here instead, because this
repository previously carried two different hand-maintained counts and
neither matched what pytest reported.

| metric | value |
|---|---|
{rows}

{notes}
"""


def _count_ids(text: str, prefix: str) -> int:
    return len(set(re.findall(rf"\b({prefix}-\d{{2}})\b", text)))


def collect_metrics(root: Path | str = ".", run_pytest: bool = True) -> RepositoryMetrics:
    """Measure the repository.  ``run_pytest=False`` skips the collection step."""
    root = Path(root).resolve()
    sys.path.insert(0, str(root / "src"))
    from wildfireguardian_forecast_value._version import __version__
    from wildfireguardian_forecast_value.synthetic_decisions.scenarios import CASES, case_specs
    from wildfireguardian_forecast_value.validation.hand_examples import hand_examples
    from wildfireguardian_forecast_value.validation.invariants import __all__ as inv_all

    total, slow = count_collected_tests(root) if run_pytest else (-1, -1)

    specs = case_specs()
    fixtures_dir = root / "experiments" / "benchmark_fixtures"
    fixtures = len(list(fixtures_dir.glob("*.json"))) if fixtures_dir.exists() else 0

    docs = "".join(p.read_text(encoding="utf-8") for p in (root / "docs").glob("*.md"))

    from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
    n_ops = len(standard_pipeline())

    return RepositoryMetrics(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        package_version=__version__,
        tests_collected=total,
        tests_marked_slow=slow,
        hand_solvable_examples=len(hand_examples()),
        structural_invariants=len([n for n in inv_all if n.startswith("check_")
                                   and n != "check_no_clairvoyance"]),
        frozen_benchmark_fixtures=fixtures,
        degradation_operators=n_ops,
        documented_assumptions=_count_ids(docs, "A"),
        documented_failure_modes=_count_ids(docs, "F"),
        documented_decisions=_count_ids(docs, "D"),
        benchmark_cases=len(CASES),
        benchmark_case_arms=sum(len(specs[k].arms) for k in CASES),
        notes=[
            "`tests collected` is what `pytest --collect-only -q` reports at the "
            "repository root; `tests marked slow` is the subset carrying the "
            "`slow` marker (deselect with `-m 'not slow'`).",
            "`degradation operators` counts the operators in the default "
            "`standard_pipeline()`, not every operator the package defines.",
            "All benchmark case results are CONSTRUCTED_BENCHMARK, not "
            "EMPIRICAL_RESULT -- see `docs/CURRENT_RESULT_STATUS.md`.",
        ],
    )


def write_metrics(metrics: RepositoryMetrics, out_dir: Path | str = "reports") -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    js = out / "generated_metrics.json"
    md = out / "generated_metrics.md"
    js.write_text(json.dumps(metrics.as_dict(), indent=2) + "\n", encoding="utf-8")
    md.write_text(metrics.as_markdown(), encoding="utf-8")
    return js, md
