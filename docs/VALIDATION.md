# Validation

*Agent C (Independent Validator) owns this document. Nothing here trusts the
implementation; every expected value is arithmetic on the inputs.*

Run them:

```bash
wg-forecast-value validate -v     # prints every derivation
pytest tests/test_hand_checkable.py -q
```

## The three layers

1. **Hand-solvable examples** — closed-form answers computable on paper in
   under a minute, with the derivation written out in full.
2. **Structural invariants** — properties that would silently invalidate a
   study if broken, checked at runtime and before every CLI study.
3. **Claim tests** — the four cases asserted as the *claims the prose makes*,
   so that documentation and code cannot drift apart.

---

## Layer 1 — hand-solvable examples

Thirteen examples, each with a full derivation in
`validation/hand_examples.py`. Numbers are chosen to be exact in binary
floating point where possible (halves, quarters, 3-4-5 triangles); where a
value is irrational the tolerance is stated.

| ID | What it pins down |
|---|---|
| **V1** | Arrival time of a 45-degree wedge, inside, on the edge, outside, and at the origin. `+inf` means never. |
| **V2** | Spread-rate error is multiplicative and **asymmetric**: `+0.5` costs 1 h, `-0.5` costs 3 h at the same point. |
| **V3** | Displacement translates the whole arrival field: `t'(p) = t(p - s)`, exactly. |
| **V4** | Rotating an isotropic source changes nothing — which is why `DirectionError` skips spot fires by default. |
| **V5** | Availability is a step at `s + delta`, inclusive at the boundary; the age of information at use exceeds the latency. |
| **V6** | `known_at` is inclusive and removes sources that have not ignited: a forecast cannot contain a future ignition. |
| **V7** | `SpotMiss` thresholds a latent uniform at `p_miss`; `SpotDelay` leaves the primary source alone. |
| **V8** | Route safety margin — see the worked example below. |
| **V9** | `J = c_t * travel_time + L * 1[overrun]`, and the world-level mean over a community. |
| **V10** | Arrival-time metrics with censoring: infinities are **counted**, never averaged. |
| **V11** | POD, FAR, CSI, frequency bias from an explicit 2×2 table. |
| **V12** | The clustering design effect — see the worked example below. |
| **V13** | Paired-summary arithmetic, including that exact zeros are kept. |

### V8 worked out — the tightest point is not the closest point

This one is included because the intuitive answer is wrong.

Route: the segment `x = 0` from `y = -5` to `y = +5`, travelled at `v = 10`
km/h, so a receptor departing at `t0` is at arc length `L` (hence `y = L - 5`)
at time `t0 + L/10`. Fire: isotropic, origin `(-5, 0)`, `r = 5` km/h, reaching
`(0, y)` at `sqrt(25 + y^2)/5`.

    gap(L) = sqrt(25 + (L-5)^2)/5 - (t0 + L/10)

The naive guess is the route midpoint `(0,0)`, the point nearest the fire,
where the gap is `1.0 - 0.5 = 0.5` h. **That is not the minimum.** Setting
`d(gap)/dL = 0` with `u = L - 5`:

    u / (5 sqrt(25 + u^2)) = 1/10   ->   2u = sqrt(25 + u^2)
    4u^2 = 25 + u^2  ->  u = 5/sqrt(3) = 2.8868,  so L = 7.8868, y = +2.8868

The binding point is *past* the midpoint, on the far side, because the receptor
keeps moving while the fire closes. There:

    fire arrives at   sqrt(25 + 25/3)/5 = 2/sqrt(3) = 1.15470 h
    receptor passes at t0 + 0.78868 h
    margin(t0 = 0)  = (sqrt(3) - 1)/2 = 0.366025 h

Departing later shifts every passage time uniformly, so the margin shifts by
exactly `-dt`: `0.5` h later gives `-0.13397` (overrun), `1.0` h later gives
`-0.63397`.

Tolerance `1e-5`, because the margin is found by sampling the path at 1 m
spacing and sampling can only *overstate* it (A-05).

### V12 worked out — four worlds of five residents are four observations

Worlds A and B have `Delta J = 0` for all five residents; worlds C and D have
`10`. Within-world variance is zero, so `MSW = 0` and `ICC = MSB/MSB = 1`
exactly.

    design effect          = 1 + (m-1) ICC = 1 + 4 = 5   (= the cluster size)
    effective sample size  = 20 / 5 = 4                  (= the number of worlds)

The naive receptor-level SE uses `N = 20`:

    sd = sqrt(20 * 25 / 19) = 5.1299,   SE = 5.1299 / sqrt(20) = 1.1471

The correct world-level SE uses the four world means `(0, 0, 10, 10)`:

    sd = sqrt(100/3) = 5.7735,          SE = 5.7735 / 2 = 2.8868

The naive SE is **2.5× too small — exactly `sqrt(5)`, the design effect.**

---

## Layer 2 — structural invariants

Run by `wg-forecast-value validate` and before every CLI study.

| Check | What it prevents |
|---|---|
| `check_identity_degradation` | An operator with no exact identity point, so "no degradation" is not a point in the sweep. |
| `check_conditional_on_information_time` | A release containing a source that ignites after its information time — a `FUTURE_ORACLE` masquerading as a forecast. The most attractive bug here, because it flatters the forecast in exactly the worlds where being good matters most. |
| `check_latency_semantics` | A broken availability step, or an information age smaller than the latency. |
| `check_baseline_is_forecast_free` | A "baseline" that changes its decision when the forecast stream is emptied — i.e. one that is secretly a forecast, making `Delta J` measure the wrong thing. |
| `check_no_oracle_access` | A candidate policy reading `DecisionContext.truth_state`. Re-runs every non-oracle policy with the slot emptied and asserts the decision is unchanged. |
| `check_pairing` | Two arms of a comparison covering different worlds. |

These raise rather than warn: a study that has violated one is producing
numbers that mean something other than what they are labelled.

---

## Layer 3 — claim tests

`tests/test_cases.py` asserts the *claims*, not the code paths:

* each case arm selects the documented actions and has the documented sign of
  `Delta J` and value fraction;
* Case 1's skill falls substantially while its decision value is bit-for-bit
  identical to the `PRESENT_STATE_ORACLE` arm's;
* Case 2 scores **better** than Case 1 on both CSI and FAR while realising
  **none** of the value;
* Case 3 has the worst CSI of any case and realises **all** of the value;
* Case 4's late forecast is worth exactly zero, not negative;
* `test_skill_ranking_is_inverted_against_value` — every forecast realising
  100% of the value scores worse on CSI than every forecast realising 0%.

If a change to the fire model, the policies or the loss breaks one of these,
the test fails with a message pointing at the prose that has stopped being
true.

---

## What validation does *not* establish

That the model is right about wildfires. Every check above verifies that the
implementation computes what the mathematics says it computes. Whether that
mathematics resembles a real fire is a separate question, and this repository
does not address it (`SCOPE.md`).

## Cross-checks that also act as validation

* **Determinism.** Same seed, same results; different seeds, different worlds
  (`tests/test_decisions.py`).
* **Bootstrap coverage.** A nominal-95% interval covers a known mean in
  roughly 95% of repeated samples (`tests/test_statistics.py`).
* **Paired bootstrap exactness.** With a constant offset between arms, the
  paired interval collapses to that offset — demonstrating that pairing
  survives resampling.
* **Sampling monotonicity.** Finer route sampling can only lower a margin.
* **Operator algebra.** Field-disjoint operators commute; heading-relative
  displacement provably does not.
* **Translation identity.** Displacement agrees with an evaluation at shifted
  points over 200 random points, infinities included.
