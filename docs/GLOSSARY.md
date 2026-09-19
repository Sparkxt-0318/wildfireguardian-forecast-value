# Glossary

Terms are defined as this repository uses them. Where a term is used
differently elsewhere in the field, that is noted.

---

**Action** (`a`) — an element of the decision maker's choice set. Here,
`route_a` or `route_b`.

**Arrival time** — the time at which a fire state first reaches a point.
`+inf` means *never reaches it*, not *reaches it very late*, and every
consumer handles the two differently.

**Availability time** (`a = s + delta`) — the first instant a forecast release
can be acted on. Distinct from its information time.

**Baseline** — the forecast-free policy the forecast is compared against. Here
a proximity trigger. Decision value is undefined without one.

**Break-even frontier** — the set where `Delta J = 0`. Not assumed monotone,
single-valued, or non-empty.

**Burnover** — a receptor being reached by the fire while still on the route.
A step term in `J`.

**Clairvoyance** — a forecast containing information it could not have had at
its information time. Structurally prevented; `check_no_clairvoyance` raises
on it. Note that *zero degradation* is not clairvoyance: an un-degraded
forecast still cannot see a spot fire that has not ignited.

**Cluster bootstrap** — resampling **worlds**, whole, with replacement. The
only correct resampling unit here.

**Common random numbers** — evaluating every cell of a parameter sweep on the
same worlds, so that cell-to-cell differences are signal rather than
Monte-Carlo noise. Forces the bootstrap to resample jointly across the grid.

**CSI** (critical success index) — `hits / (hits + false alarms + misses)`.
Preferred over accuracy here because it does not use correct negatives, and so
does not reward padding the domain with unburnt cells. Still depends on the
grid (F-04).

**Decision time** (`t_d`) — when the protective action must be chosen.

**Decision value** (`Delta J`) — `J_baseline - J_forecast` on paired worlds.
Positive means the forecast improved the decision. **The quantity this
repository exists to estimate.**

**Degradation operator** — a deterministic map `FireState -> FireState`
indexed by named parameters, with an exact identity point.

**Design effect** — `1 + (m-1) * ICC`; the factor by which a naive analysis
understates the variance of a mean. 30.4 in the packaged scenario.

**Effective sample size** — `N / design effect`. 264 of 8000 receptors in the
packaged scenario — close to the 200 worlds, as it should be.

**Equivalence** — a claim that two options differ by less than a stated
margin. Requires a margin; this package refuses to default one.

**FAR** (false alarm ratio) — `false alarms / (hits + false alarms)`. `nan`,
not 0, when the forecast never predicts the event.

**Forecast release** — one forecast product with its two timestamps. See
`ForecastRelease`.

**Fraction (of VPI realised)** — `Delta J / VPI`. `nan` where the baseline was
already optimal, because `0/0` is not "realised 0% of the value".

**Half-angle** (`phi`) — the angular half-width of a spreading wedge. `pi` is
isotropic.

**Hours of equivalent delay** — the unit of `J`. Travel time enters directly;
a burnover enters as `burnover_loss` hours. Not money.

**ICC** (intraclass correlation) — the share of total variance that is between
worlds rather than within them. 0.75 in the packaged scenario.

**Information time** (`s`) — the forecast is built from knowledge of the world
up to and including `s`. Distinct from latency and from staleness.

**Latency** (`delta`) — production, transmission and ingest delay. Modelled as
**availability**, never as a penalty on a score.

**Loss** (`J(a, omega)`) — the downstream loss of action `a` in world `omega`.
Smaller is better. Explicit, serialised, and arbitrary by nature (F-07).

**Loss ratio** (`L / c_t`) — the burnover-to-time exchange rate; the *only*
free parameter of the loss, since `J` is invariant to a common rescaling.

**Margin (safety margin)** — `min_k [ t_fire(p_k) - t_receptor(p_k) ]` along a
route. `<= 0` is overrun; `+inf` means the fire never reaches the path.

**Paired worlds** — the same realisation evaluated under two information sets.
All inference is on the paired difference.

**Plug-in policy** — treating the forecast state as if it were the truth and
minimising `J`. The weakest honest use of a deterministic forecast, so every
`Delta J` here is a lower bound (A-08).

**POD** (probability of detection) — `hits / (hits + misses)`.

**Proximity trigger** — the baseline: take the short exposed route unless the
*currently burned area* is within `trigger_distance` of it. Forecast-free by
construction.

**Receptor** — one evacuating household in a world. **Not** an independent
observation.

**Spot fire / spotting** — a secondary ignition ahead of the main front. Can
be missed, delayed or displaced by the error model; never fabricated (F-08).

**Staleness** — the age of information at use, `t_d - s`, which is at least
`delta`. Not the same as latency (F-12).

**TOST** — two one-sided tests; the equivalence procedure. Implemented as
interval inclusion.

**VPI** (value of perfect information) — `J_baseline - J_clairvoyant`. The
most any forecast could be worth in a world; the denominator of the fraction.

**Wedge** — the fire model: a circular sector spreading at constant rate from
an origin. Chosen for hand-checkability (D-01); its hard edge is A-02.

**World** (`omega`) — one synthetic fire realisation plus the community that
must evacuate it. **The unit of analysis.** Not a resident, not a grid cell,
not a route sample.
