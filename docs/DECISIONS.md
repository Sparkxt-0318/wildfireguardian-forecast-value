# Design decisions

Decisions that were genuinely contested, with the alternative that was
rejected and why. Recorded so that revisiting one is a deliberate act.

---

**D-01 — A wedge fire model, not an ellipse or a cellular automaton.**
*Rejected:* Rothermel-style elliptical growth; a raster CA.
*Why:* hand-checkability. The wedge's arrival time is one distance and one
angle comparison, so `tests/test_hand_checkable.py` can assert closed-form
answers and a reader can redo them on paper. A CA would make every fixture
opaque and would not change any conclusion about skill versus value. The cost
is A-02: the wedge's hard edge makes Case 2 a cliff rather than a gradient.

---

**D-02 — Latency as availability, not as a score penalty.**
*Rejected:* `J -> J + c*delta`, or a lead-time term in a skill score.
*Why:* a penalty makes a late forecast merely worse; reality makes it absent,
which returns the decision maker to their prior policy. Only the availability
model can produce Case 4, where a *more accurate* forecast has *less* value.
This was the explicit brief and it drove the design of `ForecastRelease`,
`ForecastStream` and `DecisionContext`.

---

**D-03 — Waiting is a physical cost, not a penalty either.**
*Rejected:* adding a `c_wait * delay` term to `J` to make latency bite
continuously.
*Why:* that would have smuggled the rejected score-penalty model back in under
another name. Instead `ForecastPolicy(max_wait=...)` shifts the *departures*,
and the fire keeps spreading while the community waits — in the packaged
scenario a delay of about 0.95 h closes the robust route. The cost falls out
of the same arrival-time arithmetic as everything else.
*Consequence:* the scenario geometry had to be retuned so the robust route is
cuttable at all. A route that can never be cut makes waiting free.

---

**D-04 — Operators are deterministic; stochasticity lives in one object.**
*Rejected:* operators that sample their own error.
*Why:* three things follow. Every operator is hand-checkable at a fixed
parameter. A frontier sweep varies parameters on a grid with no RNG involved.
And it becomes structurally impossible to sample two channels independently
merely because two different operators applied them — which is the mistake
`CorrelatedErrorModel` exists to prevent.

---

**D-05 — Spot miss thresholds a latent uniform rather than flipping a coin.**
*Rejected:* `if rng.random() < p_miss: drop`.
*Why:* an internal coin flip cannot be correlated with a spread-rate bias. A
latent uniform, supplied by the copula, can. The cost is one more concept
(`spot_miss_u` is not an error magnitude but a latent variate), which the
docstring states explicitly.

---

**D-06 — The baseline is a proximity trigger, not "always take the safe route".**
*Rejected:* a fixed-action climatological baseline.
*Why:* a fixed action is a straw man, and a forecast that beats a straw man
has demonstrated nothing. The proximity trigger responds to the observed fire,
costs nothing to run, and beats the forecast over a large part of the
error/latency plane. That region is a result. `FixedActionPolicy` remains
available for contrast.

---

**D-07 — The baseline may see where the fire *is*, never where it *will be*.**
*Rejected:* a persistence-nowcast baseline (extrapolate the current front).
*Why:* extrapolation is a forecast. Allowing it would make the comparison
"forecast versus worse forecast", which is a legitimate question but not this
one. `FireSource.distance_to_burned` exists precisely so a policy can ask
about the present without being handed an arrival time.
`check_baseline_is_forecast_free` enforces it.

---

**D-08 — `Outcome` lives at the package root.**
*Rejected:* defining it in `decision_value.loss` next to the loss model.
*Why:* it created an import cycle (routes need `Outcome`, loss needs
`Outcome`, value needs policies, policies need routes) — but more importantly,
the separation is the point: physics produces outcomes, valuation prices them,
and neither should depend on the other. That is what lets a study re-value a
fixed set of outcomes under a whole family of loss functions without re-running
the fire model.

---

**D-09 — `skill_metrics` and `decision_value` do not import each other.**
*Rejected:* a convenience module computing both together.
*Why:* the repository's entire claim is that these two quantities can move
independently. Enforcing it as a module boundary makes "a skill score
influenced a decision" a structural impossibility rather than a code-review
item.

---

**D-10 — Skill is computed but carried as inert columns.**
*Rejected:* not computing skill in the decision path at all.
*Why:* a study needs to regress value on skill to show they do not track.
`evaluate_world(compute_skill=False)` exists because the raster is the
expensive part of a frontier sweep and nothing reads it there.

---

**D-11 — The frontier estimator returns every zero crossing.**
*Rejected:* bisection for a single break-even point.
*Why:* two mechanisms in this very model produce multi-valued columns (F-10),
and bisection converges confidently to the wrong side of the latency step.
The cost is that "the frontier" is sometimes a set, and the plot has to say so.

---

**D-12 — The frontier grid uses common random numbers.**
*Rejected:* independent worlds per cell.
*Why:* near the frontier the differences are smallest, so independent-world
noise would swamp exactly the signal being estimated.
*Consequence:* cells are correlated, so `bootstrap_frontier_band` must resample
worlds jointly across the whole grid. Bootstrapping cells independently would
be wrong in both directions.

---

**D-13 — BCa bootstrap as the default interval.**
*Rejected:* Student-t alone; percentile alone.
*Why:* `Delta J` is a spike at zero plus a heavy positive tail. Both are
reported side by side so disagreement is visible; BCa leads because the
percentile interval is noticeably off-centre in this regime.

---

**D-14 — Degenerate bootstrap replicates report a point interval, not `nan`.**
*Rejected:* `nan` for a zero-width bootstrap distribution.
*Why:* when every world gives the same `Delta J`, the estimate really is exact
under this world distribution. `degenerate: True` with a zero-width interval
says that; `nan` would say "we do not know", which is false.

---

**D-15 — Equivalence has no default margin.**
*Rejected:* a convenience default such as 5% of the mean.
*Why:* the margin is a policy input. A default would be quoted as if it were a
statistical constant, and equivalence at an unstated margin is not a claim.

---

**D-16 — The CLI errors on unknown configuration keys.**
*Rejected:* warning and ignoring.
*Why:* a typo in `burnover_loss` that silently leaves the default in place
produces a plausible, wrong number with a manifest that looks correct.

---

**D-17 — Colour is assigned by the job it does.**
*Rejected:* a rainbow colormap for `Delta J`; a dual-axis chart for skill
against value.
*Why:* `Delta J` has a meaningful zero and two opposite signs, so it gets a
diverging ramp with the neutral midpoint pinned exactly at zero — the colour
change *is* the frontier. Skill and value share one axis in the bar chart
because the whole claim is that the two numbers do not track each other, which
a second y-scale would hide. The categorical palette was validated for
colour-vision-deficiency separation rather than chosen by eye.
