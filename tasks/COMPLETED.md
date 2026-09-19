# Completed

## v0.1 — methods foundation

Every item in the brief's definition of done, with the evidence.

### Degradation library works
Five operator families — spread rate, direction, spatial displacement,
spotting (miss / delay / displacement), plus front widening — composable
through `DegradationPipeline` with a documented canonical order. Every
operator has an exact identity point, raises on domain violations, and
declares which sources it touches. Correlated combination via a Gaussian
copula with per-channel marginals.
*Evidence:* `tests/test_degradation.py` (56 tests), hand-checks V1–V4, V7.

### Latency semantics are explicit
Three clocks (information time, latency, decision time) as separate fields.
Availability is a step at `s + δ`, inclusive. Information time structurally
forbids clairvoyance: `make_release` restricts truth *before* degrading.
Staleness (`t_d − s`) is reported separately from latency. A decision maker may
wait, and waiting shifts departures rather than scoring points.
*Evidence:* `tests/test_latency.py`, hand-checks V5–V6, Case 4.

### Synthetic decisions work
Two-route evacuation tuned so the safety margin on the exposed route sits a
fraction of an hour either side of zero. Three policy classes: forecast-free
proximity trigger, plug-in forecast policy with fallback and optional waiting,
clairvoyant upper bound. Worlds carry staggered receptors, which is what makes
the clustering problem real rather than illustrative.
*Evidence:* `tests/test_decisions.py`, `figures/scenario_map.png`.

### Forecast skill vs decision value is demonstrated
All four requested cases, deterministic and asserted:

1. `+18°` heading error — CSI `1.00 → 0.57`, FAR `0.00 → 0.30`, arrival-time
   RMSE exactly 0, **action unchanged, value unchanged**.
2. `−17°` heading error — *smaller* in magnitude, *better* CSI and FAR, and it
   flips the decision; value `100% → 0%`, and `ΔJ ≈ −50 h` in a faster world
   where the trigger would have been right on its own.
3. 60% fast, 3 km displaced, 10° off — **worst CSI of any case (0.40)**, full
   value realised.
4. Perfect forecast 0.5 h late — CSI 1.00, **value 0%**; a CSI-0.46 forecast
   that arrives on time realises 100%.

Ranked by CSI, the value column is **exactly inverted**.
*Evidence:* `tests/test_cases.py`, `figures/case_comparison.png`,
`figures/skill_vs_value.png` (two settings, identical CSI 0.64,
`ΔJ = +17.4 h` and `−2.7 h`).

### World-level statistics work
Paired world-level comparison, cluster bootstrap with BCa and percentile
intervals, effect sizes (mean `ΔJ`, tie-splitting probability of superiority,
`d_z`/Hedges' `g`, fraction of VPI realised), TOST equivalence and
non-inferiority with a mandatory margin, and clustering diagnostics printed on
every run (ICC 0.75, design effect 30.4, naive SE 5.5× too small).
*Evidence:* `tests/test_statistics.py`, hand-checks V12–V13.

### Frontier estimator works
`ΔJ = 0` extracted with every zero crossing returned, columns with no crossing
reported rather than interpolated through, and `monotonicity_report` measuring
rather than assuming. Common random numbers across the grid, with a bootstrap
that resamples worlds jointly to match.
*Evidence:* `tests/test_frontiers.py`, `figures/frontier_direction_latency.png`.

### Uncertainty is reported
BCa intervals on every effect size, pointwise bootstrap bands on the frontier,
per-column crossing rates (a frontier that exists in only 83% of resamples is
labelled as such), surface bands, and an explicit statement of what the
intervals do **not** cover.

### Tests include hand-checkable examples
13 closed-form examples with full derivations, runnable as
`wg-forecast-value validate -v`. 277 tests total.

### Assumptions and failure modes are documented
A-01…A-15 with consequences, F-01…F-15 with guards and what to check,
D-01…D-17 with rejected alternatives.

---

## Notable findings from building it

* **The CSI ranking of the four cases is the exact reverse of their decision
  value ranking.** This was not designed in; the cases were chosen to
  demonstrate four separate phenomena and the inversion fell out. It is now
  asserted by a test.
* **Sign beats magnitude for direction error.** `+18°` is free and `−17°` is
  catastrophic in the same scenario. Any summary reporting `|ε_θ|` destroys
  the finding.
* **A "perfect" forecast is not clairvoyant.** An un-degraded forecast issued
  at the decision time still cannot see a spot fire that ignites afterwards.
  This surfaced as a *failing test* whose assertion was wrong, and it is now
  asserted in the correct direction.
* **Route sampling caught a wrong hand-derivation.** The binding point on a
  route crossed by a fire is *not* the point nearest the fire — the receptor
  keeps moving while the fire closes. V8 now carries the calculus.
* **Making waiting costly required retuning the geometry.** A robust route
  that can never be cut makes waiting free, which would have made the latency
  axis a single cliff. The robust route is now cuttable at a delay of ~0.95 h.
* **The sign of `Delta J` is remarkably insensitive to the loss ratio.**
  Across `L/c_t` from 0.05 to 200 — a 4000-fold range — the sign never
  changes, though the realised fraction of perfect information collapses from
  0.92 to 0.30 around `L/c_t ~ 0.12`, where the detour cost and the burnover
  cost become comparable. That is the regime in which the decision is finely
  balanced and a forecast has the least room to help, and it is not where the
  default loss sits.
* **A too-long skill horizon saturates CSI at 1** and hid a large spread-rate
  error during development. `skill_horizon` is now an explicit scenario field
  and the episode is recorded as F-04.
