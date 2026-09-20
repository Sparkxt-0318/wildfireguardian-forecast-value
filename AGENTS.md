# AGENTS.md

How work on this repository is organised, and the rules an agent (human or
otherwise) must follow to change it without quietly breaking a claim.

---

## The three roles

Work proceeds through three roles. They are roles, not people: one agent may
play all three, but **never simultaneously on the same change**. The value of
the separation is that the validator does not know how the implementation
works, and the auditor does not get to choose numbers that happen to pass.

### Agent A — Mathematical Auditor

**Owns:** `docs/FORECAST_ERROR_MODEL.md`, `docs/DECISION_VALUE.md`,
`docs/ASSUMPTIONS.md`, the operator and loss definitions.

**Specifies before anything is implemented:** the operator's map, its exact
domain, its identity point, what it does to each field of a `FireSource`, and
what it does *not* do.

Four things Agent A is specifically responsible for catching:

1. **Monotonicity assumptions.** Where is a quantity assumed to be ordered by
   a parameter? Direction error is the trap: `|ε_θ|` does *not* order decision
   value, because a wedge boundary can sweep past one asset and onto another.
   Any code that bisects, any prose that says "beyond X degrees", any plot
   that draws one line per column — each is a monotonicity assumption and must
   be justified or removed. `monotonicity_report` measures; it never assumes.
2. **Correlated error.** Independence must never be the default by omission.
   `CorrelatedErrorModel.independent()` is the named way to assume it. The
   copula's `R` is *not* the parameters' Pearson correlation (F-02), and a
   Gaussian copula cannot express tail dependence (F-03) — both must be
   restated wherever a correlation is reported.
3. **Latency semantics.** Latency is availability, never a score penalty
   (D-02). Information time, latency and staleness are three different numbers
   (F-12). A forecast may not contain what had not happened at its information
   time (F-13). Waiting costs departures, not points (D-03).
4. **Loss-function arbitrariness.** There is no correct `J`. Every result is
   conditional on one; the conditioning must be printed with the result; and
   sensitivity to the loss ratio is a first-class output, not an appendix
   (F-07).

### Agent B — Implementation Engineer

**Owns:** everything under `src/`.

Rules:

* Implement the specification, not an approximation of it. If the
  specification is impossible or ambiguous, send it back to A rather than
  choosing.
* **Every operator needs an exact identity point.** Checked by
  `check_identity_degradation` for every registered operator.
* **Raise, do not warn, on a domain violation.** A silently clipped `ε_r` is a
  wrong number with a manifest that looks right.
* **Never let a skill metric reach a decision.** `skill_metrics` and
  `decision_value` do not import each other, and that boundary is the point of
  the repository (D-09).
* **Never touch global RNG state.** Derive streams by spawning a
  `SeedSequence` (`rng.spawn`), never by offsetting an integer seed — offset
  seeds collide and silently correlate "independent" worlds (A-11).
* Docstrings state *why*, not *what*. The what is in the code.

### Agent C — Independent Validator

**Owns:** `tests/`, `src/.../validation/`, `docs/VALIDATION.md`.

Rules:

* **Derive the expected value by hand, from the inputs, without reading the
  implementation.** Every `HandExample` carries its derivation in full, and
  `test_every_example_has_a_derivation` enforces that it is more than a
  gesture.
* **Assert claims, not code paths.** `tests/test_cases.py` asserts what the
  prose says — that Case 2 scores *better* than Case 1 and decides *worse*,
  that the CSI ranking is inverted. If a change makes the documentation false,
  a test must fail.
* **Choose numbers that are exact in binary floating point** where possible.
  Where a value is irrational, state the tolerance and why.
* **Be suspicious of a passing test that was written after the code.** V8 in
  `hand_examples.py` exists because the first derivation attempted — "the
  tightest point on the route is the point nearest the fire" — was wrong, and
  the test caught the *author*, not the code.

---

## The rule that matters most

**If you change behaviour, change the prose in the same commit.**

The claims in `README.md` and `docs/DECISION_VALUE.md` are asserted by tests.
A change that makes one false will fail
`tests/test_cases.py::test_skill_ranking_is_inverted_against_value` with a
message naming the document. Fix the document or fix the change; do not
weaken the test.

---

## Extending the package safely

### Adding a degradation operator

1. **A specifies** the map, domain, identity point, which `FireSource` fields
   it writes, whether it commutes with the existing set, and its entry in
   `docs/FORECAST_ERROR_MODEL.md`.
2. **B implements** `DegradationOperator` with `name`, `param_names`,
   `identity_params()`, `_apply_to_source()` and `_config()`, and adds it to
   `STANDARD_ORDER` if it belongs in the default chain.
3. **C adds** it to `ALL_OPERATORS` in `tests/test_degradation.py` (which
   parametrises the identity and missing-parameter checks over it), plus a
   hand-solvable example if its arithmetic is non-obvious.

**If the new operator reads a field another operator writes, it does not
commute.** Say so in its docstring, put it in the right place in
`STANDARD_ORDER`, and add a non-commutation test as
`SpatialDisplacement(relative_to_heading=True)` has.

### Adding a policy

Declare `uses_forecast` honestly. A baseline must pass
`check_baseline_is_forecast_free`, which re-runs it with the forecast stream
emptied. No candidate policy may read `DecisionContext.truth_state`;
`check_no_oracle_access` re-runs it with the slot emptied and compares.

A policy returns a `Decision` — an action **and** a departure delay. If your
policy waits for anything, the delay must be real, because that is how latency
costs something.

### Adding a statistic

It takes **world-level** values. If it cannot, it does not belong in
`statistics/`. Anything that consumes receptor-level data goes through
`aggregate_to_worlds` so the collapse is visible.

Report an effect size and an interval. A p-value may accompany them; it may
not replace them.

### Adding a figure

Read `docs/DECISIONS.md` D-17 first. Colour is assigned by the job it does:
diverging with the neutral midpoint pinned at zero for `ΔJ`; a fixed
categorical order (never cycled) for identity; one axis, never two y-scales.
Validate a new categorical palette rather than eyeballing it.

---

## Definition of done for any change

- [ ] `pytest -q` passes. Do **not** write the count into any document;
      regenerate [`reports/generated_metrics.md`](reports/generated_metrics.md)
      with `wg-forecast-value release-metrics` instead.
- [ ] `wg-forecast-value freeze-benchmarks` reports no drift, or the drift is a
      documented defect fix re-frozen with `--write`.
- [ ] `wg-forecast-value validate` passes — 13 hand-solvable examples and 5
      structural invariants.
- [ ] New behaviour has a hand-checkable example or a claim test.
- [ ] Any new assumption has an `A-nn` entry; any new way to be misled has an
      `F-nn` entry; any contested choice has a `D-nn` entry.
- [ ] Prose that a test asserts is still true.
- [ ] Nothing imports another WildfireGuardian repository (`docs/SCOPE.md`).

---

## Things that look like improvements and are not

* **Defaulting the equivalence margin.** It is a policy input. A default would
  be quoted as a statistical constant (D-15).
* **Warning instead of raising on unknown config keys.** A typo in
  `burnover_loss` produces a plausible wrong number (D-16).
* **Returning `nan` for a degenerate bootstrap.** When every world agrees, the
  estimate is exact, not unknown (D-14).
* **Dropping ties from the probability of superiority.** A world where the
  forecast changed nothing is evidence about the forecast.
* **Reporting `|ε_θ|`.** Sign is the whole finding; magnitude alone destroys
  it.
* **Bisecting for the frontier.** It converges confidently to the wrong side
  of the latency step (F-10).
* **"Simplifying" `Delta J` to a single headline number.** It is a surface
  conditional on a baseline, a loss and a scenario.
