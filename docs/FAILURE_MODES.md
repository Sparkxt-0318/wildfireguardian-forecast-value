# Failure modes

Ways this repository can produce a number that is wrong, or right and
misleading. Identifiers are stable and referenced from docstrings.

Each entry states the failure, whether the code guards against it, and what a
reader should check.

---

## F-01 — Reporting decision value without its alternative

**Failure.** Quoting "this forecast is worth 18 hours" as a property of the
forecast. It is a property of the forecast *relative to the proximity trigger
with this radius*, under this loss, in this scenario.

**Guard.** Partial. The manifest records the baseline policy and its
parameters; `check_baseline_is_forecast_free` ensures the baseline is not
secretly a forecast. Nothing stops a reader from dropping the context.

**Check.** Every `Delta J` in prose should name its baseline.

---

## F-02 — Quoting the copula's correlation as the parameters' correlation

**Failure.** `CorrelatedErrorModel(..., {("eps_theta", "spot_delay"): 0.8})`
does **not** produce a Pearson correlation of 0.8 between the sampled
parameters. `R` is the correlation of the latent normals; they coincide only
where both marginals are normal.

**Guard.** `realised_correlation()` measures it from a sample.
`tests/test_degradation.py::test_latent_correlation_is_not_the_realised_one`
asserts the gap is real.

**Check.** Report `realised_correlation()`, not `R`.

---

## F-03 — Assuming a Gaussian copula can express joint catastrophe

**Failure.** A Gaussian copula has **no tail dependence**. Channels that fail
together only in the tail — the fire is much faster *and* in the wrong
direction *and* the spot was missed, all at once — are systematically
under-represented, no matter how high `rho` is set. Those are exactly the
events that flip protective decisions.

**Guard.** None in code. Documented here and in `combined.py`; listed as
A-15.

**Check.** Treat estimated tail probabilities as lower bounds. A t-copula or an
explicit mixture would be the fix.

---

## F-04 — Domain-dependent categorical skill

**Failure.** POD, FAR, CSI and accuracy all depend on the grid the analyst
chose. Padding the domain with unburnt cells inflates accuracy without
changing anything. A skill horizon past the point where the fire leaves the
grid saturates CSI at 1 and hides every spread-rate error — this actually
happened during development of this repository and produced a case that
appeared to show "large rate error, perfect CSI".

**Guard.** The grid is an explicit, serialisable object; every categorical
result carries `n_cells`; CSI is preferred because it does not use correct
negatives; `skill_horizon` is an explicit scenario field with a docstring
saying why.

**Check.** Compare categorical scores only across runs with the same grid and
horizon. Look at `n_cells` before believing a CSI.

---

## F-05 — Arrival-time RMSE is gameable by predicting "never"

**Failure.** Arrival-time error can only be computed where both fields burn.
A forecast can therefore *improve* its RMSE by predicting "never burns" at
exactly the points it would have got wrong.

**Guard.** `arrival_time_metrics` refuses to return a bare scalar: it returns
`n_both`, `n_miss`, `n_false`, `n_neither` and `coverage` alongside.
`tests/test_skill_metrics.py::test_rmse_is_gameable_by_predicting_never`
demonstrates the exploit and shows the miss count exposing it.

**Check.** An RMSE quoted without its coverage is not interpretable.

---

## F-06 — Reading `Delta J` as *the* value of the forecast

**Failure.** `Delta J` is the value of the forecast **to a plug-in decision
maker**, which is the weakest honest way to use a deterministic forecast. A
risk-averse or ensemble-based policy would do better with the same forecast.

**Guard.** Documented in `policies.py` and as A-08. The clairvoyant bound
(`VPI`) is reported alongside so the headroom is visible.

**Check.** Read every `Delta J` as a lower bound, and read `fraction` as "how
much of the achievable value *this* decision maker captured".

---

## F-07 — Treating the loss function as a measurement

**Failure.** The exchange rate between delay and burnover is an ethical
choice. A frontier is conditional on it, and a frontier that moves under a
factor-of-two change in `L / c_t` is a frontier about the analyst.

**Guard.** `J` is explicit and serialised; `loss_ratio_sweep` re-values fixed
outcomes across a family of losses; the CLI prints "every number above is
conditional on the loss ratio L/c_t = …".

**Check.** Run the sweep. Report the range of ratios over which the *sign* of
`Delta J` is stable, not just the point estimate.

---

## F-08 — Asymmetric spotting error understates over-warning

**Failure.** Spot fires can be missed, delayed or displaced, but never
fabricated. A forecast that invents a spot fire and triggers an unnecessary
evacuation is not representable, so the model systematically favours forecasts
over the trigger relative to reality.

**Guard.** None in code. Documented in `spotting.py` and in `SCOPE.md`.

**Check.** The blue region of the frontier figure is optimistic. Adding
false-alarm spotting would shrink it.

---

## F-09 — Treating residents as independent events

**Failure.** The headline statistical error. N worlds × M residents is not
N×M observations. In the packaged scenario the naive standard error is 5.5×
too small.

**Guard.** Strong. Inference functions take world-level values;
`aggregate_to_worlds` is the only sanctioned entry point; the cluster
bootstrap resamples whole worlds; `clustering_diagnostics` is printed on every
study run; `results_to_frame` tags the frame with
`attrs["unit_of_analysis"] = "world"`.

**Check.** If an `n` in a report is larger than the number of worlds, it is
wrong.

---

## F-10 — Assuming the frontier is a single-valued monotone curve

**Failure.** Bisecting for "the" break-even latency. Wedge boundaries sweeping
past assets and the latency availability step both produce columns with
several zero crossings, and a bisection converges confidently to the wrong
side of a step.

**Guard.** `zero_crossings` returns every crossing; `monotonicity_report`
measures monotonicity rather than assuming it; `ColumnFrontier.first` carries a
docstring warning that reading it alone is how a multi-valued frontier gets
mistaken for a function; the plot marks multi-crossing columns.

**Check.** Read `frontier_is_a_function_of_x` and
`n_columns_multi_crossing` before quoting a single threshold.

---

## F-11 — Reporting a frontier where the surface does not resolve a sign

**Failure.** Drawing a confident line through a region where the bootstrap
interval for the surface straddles zero.

**Guard.** `surface_band` gives a pointwise interval for the surface itself;
`crossing_rate` reports how often a frontier exists at all; the plot fades
columns below 0.8 and marks columns with none.

**Check.** A crossing rate below 1.0 means the *existence* of the frontier is
uncertain, and the band does not capture that.

---

## F-12 — Confusing latency with staleness

**Failure.** Treating `delta` as "how out of date the forecast is". It is not:
the age of information at use is `t_d - s >= delta`. A low-latency product
built on old observations can be staler than a high-latency one built on fresh
observations.

**Guard.** Separate fields and separate axis kinds
(`"latency"` vs `"information_time"`); `ForecastRelease.age_at`;
`ForecastStream.available_at` selects by information time, not arrival order;
hand-check V5.

**Check.** A frontier plotted against latency is not a frontier against
staleness.

---

## F-13 — Accidental clairvoyance

**Failure.** Building a forecast that contains a spot ignition which had not
yet happened at the forecast's information time. This is the most attractive
bug in a study like this, because it makes the forecast look good in exactly
the worlds where being good matters most.

**Guard.** `make_release` restricts to `known_at(truth, s)` *before*
degrading; `check_no_clairvoyance` raises on a violating release;
`DecisionContext.truth_state` defaults to `None` and `check_no_oracle_access`
re-runs every candidate policy with it removed and asserts the decision is
unchanged.

**Check.** `wg-forecast-value validate` runs all of these. Note that
"zero degradation" is therefore **not** "perfect information" — asserted in
`tests/test_decisions.py::test_an_undegraded_forecast_is_still_not_clairvoyant_about_the_future`.

---

## F-14 — Sweeping an error coordinate that is not what you think

**Failure.** A sweep linear in `eps_r` is not a sweep over equally-sized rate
errors (`+0.5` costs 1 h; `-0.5` costs 3 h). A sweep of `eps_theta` beyond
`+-pi` revisits headings. Either makes a frontier's shape an artefact of the
parameterisation.

**Guard.** `log_ratio_error` and `rate_metrics` report both coordinates;
`SweepAxis` requires strictly increasing values; documented in
`FORECAST_ERROR_MODEL.md`.

**Check.** Ask which coordinate the x-axis is in before reading a frontier's
asymmetry as physical.

---

## F-15 — Quoting a confidence interval as total uncertainty

**Failure.** The intervals here cover sampling variation over the world
distribution *only*. The fire model, the loss, the policy class, the baseline,
the scenario geometry and the grid resolution are all fixed, and every one of
them is a larger source of uncertainty.

**Guard.** Documented at the end of `STATISTICAL_PROTOCOL.md` and in
`statistics/paired.py`.

**Check.** No interval in this repository should be described as "the"
uncertainty.
