# Generated repository metrics

<!-- GENERATED FILE -- do not edit by hand.
     Regenerate with:  wg-forecast-value release-metrics  -->

Generated `2026-09-20T02:53:22+00:00`.

Every count below is **measured**, not typed. No other document in this
repository states a test count; they link here instead, because this
repository previously carried two different hand-maintained counts and
neither matched what pytest reported.

| metric | value |
|---|---|
| package version | `0.1.0` |
| tests collected | `434` |
| tests marked slow | `4` |
| hand solvable examples | `13` |
| structural invariants | `6` |
| frozen benchmark fixtures | `7` |
| degradation operators | `6` |
| documented assumptions | `15` |
| documented failure modes | `15` |
| documented decisions | `17` |
| benchmark cases | `4` |
| benchmark case arms | `7` |

* `tests collected` is what `pytest --collect-only -q` reports at the repository root; `tests marked slow` is the subset carrying the `slow` marker (deselect with `-m 'not slow'`).
* `degradation operators` counts the operators in the default `standard_pipeline()`, not every operator the package defines.
* All benchmark case results are CONSTRUCTED_BENCHMARK, not EMPIRICAL_RESULT -- see `docs/CURRENT_RESULT_STATUS.md`.
