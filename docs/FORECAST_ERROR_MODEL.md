# The forecast error model

*Agent A (Mathematical Auditor) owns this document. Every operator's exact
behaviour, domain, and failure of intuition is recorded here.*

## Structure

A **degradation operator** is a deterministic map indexed by named real
parameters:

    T_p : FireState -> FireState

Stochasticity lives in exactly one place, `CorrelatedErrorModel`, which draws
the parameter vector `p`. The split is deliberate: every operator can be
hand-checked at a fixed `p`, a frontier sweep varies `p` on a grid without
touching an RNG, and it is structurally impossible to sample two error
channels independently just because two different operators applied them.

Every operator has an **exact identity point** — the parameter vector at which
it is the identity map. Without one, "no degradation" is not a point in the
sweep. `tests/test_degradation.py::test_every_operator_has_an_exact_identity`
asserts this for every registered operator.

## The fire model being degraded

A `FireState` is a set of `FireSource`s. Each source spreads as a circular
**wedge**: constant rate `r`, centred on `heading`, half-width `phi`, from
`origin`, starting at `ignition_time`. Arrival time at a point is the minimum
over sources; a point angularly outside every wedge has arrival time `+inf`,
which means *never*, not *very late*.

The wedge is chosen because it is exactly hand-solvable (one distance, one
angle comparison). Its hard angular edge is a feature for this work — it is
the mechanism by which a small heading error flips a decision — and its
largest limitation (A-02).

---

## Spread-rate error

    r' = r (1 + eps_r)

**Domain.** `eps_r > -1` strictly. `eps_r = -1` is not a slow fire, it is a
fire that never moves, and `FireSource` rejects a zero rate. Values at or
below `-1` raise, or clip if `on_domain_error="clip"`.

**Asymmetry — the trap.** The map is multiplicative, so `+0.5` and `-0.5` are
*not* mirror images. At 6 km from a 2 km/h fire, the truth is 3 h:

| `eps_r` | `r'` | predicted arrival | error |
|---|---|---|---|
| `+0.5` | 3.0 km/h | 2 h | 1 h early |
| `-0.5` | 1.0 km/h | 6 h | 3 h late |

A sweep linear in `eps_r` is not a sweep over equally-sized errors. Use
`log_ratio_error` — `log(r_hat / r)` — when you need a symmetric coordinate.
Both are reported by `rate_metrics`. **The shape of a frontier depends on
which coordinate it was drawn against**, and a frontier plotted against
`eps_r` will look asymmetric even when the underlying error is symmetric.

**Monotonicity.** Arrival time is monotone decreasing in `eps_r` at every
point *inside* the wedge and completely insensitive outside it. The burned
footprint at fixed time is monotone increasing inside the wedge. Decision
value is monotone in neither, because the decision depends on which side of a
threshold the arrival time falls, not on the arrival time.

## Direction error

    theta' = wrap(theta + eps_theta)

**Circularity.** `eps_theta` is added then wrapped to `(-pi, pi]`. The
parameter is not itself wrapped, so `3*pi` is a legal way to write `pi` — but
a *sweep* beyond `+-pi` revisits headings it has already visited, making any
estimated frontier periodic and any "monotone in `eps_theta`" claim false by
construction. Keep sweeps inside `[-pi, pi]`.

**Isotropic sources are invariant.** A source with `half_angle = pi` burns in
every direction; rotating it changes nothing. `DirectionError` skips such
sources by default rather than silently applying an identity map, so the
no-op is visible in the manifest.

**Non-monotonicity — the important one.** This is the operator most likely to
produce a non-monotone decision-value response. A wedge boundary sweeping
across an asset produces a step in loss; sweeping further can move the
boundary *off* a second asset. Along such a column `Delta J` may cross zero
two or three times. Nothing in this package assumes `|eps_theta|` orders
decision value, and the frontier estimator returns every crossing it finds.

**Sign matters more than magnitude.** In the packaged scenario a `+18 deg`
error costs nothing and a `-17 deg` error costs everything. Any summary that
reports `|eps_theta|` has already destroyed the finding.

**Half-angle is untouched.** Heading error and front-width error are different
failures; widening a forecast wedge is *hedging*, not error. `WidenFront`
models it separately and is not in the default pipeline. It is the natural
confound for direction error: a wider wedge covers the truth heading more
often, so it scores better categorically while telling the decision maker
less.

## Spatial displacement

    o' = o + s     and therefore     t'(p) = t(p - s)

The translation identity is **exact** for this fire model and is asserted in
`tests/test_degradation.py::test_translation_identity` and hand-check V3.

Two parameterisations: cartesian `(disp_x, disp_y)`, or polar
`(disp_magnitude, disp_heading)`. With `relative_to_heading=True` the
displacement is measured from the source's own heading, so "the forecast puts
the fire 2 km further along its own axis" is `disp_magnitude=2,
disp_heading=0`.

**Constraints.** `disp_magnitude >= 0`. A negative magnitude with a heading is
an ambiguous way to write a rotation by `pi` and is rejected rather than
reinterpreted.

**Displacement is not a time shift.** Shifting the origin toward an asset makes
the fire arrive earlier there *and* later at assets on the far side, *and*
moves the angular wedge boundary relative to every asset simultaneously.
Treating a spatial displacement as an equivalent lead-time error is a category
error.

**Order dependence.** With `relative_to_heading=True` this operator reads
`heading`, so it does **not** commute with `DirectionError`. Every other pair
in the canonical set writes disjoint fields and does commute. Both facts are
asserted in `tests/test_degradation.py`.

## Temporal latency

Latency gets its own document section because it is the one most often
modelled wrongly. See `DECISION_VALUE.md` § "Latency is availability".

Three clocks:

| symbol | meaning |
|---|---|
| `s` | **information time** — the forecast is built from knowledge up to `s` |
| `delta` | **latency** — production, transmission and ingest delay |
| `t_d` | **decision time** |

The forecast is in the decision maker's hands iff `s + delta <= t_d`
(inclusive; A-07).

**It is not a score penalty.** `J -> J + c*delta` would make a late forecast
merely *worse*. In reality a late forecast is **absent**, and absence returns
the decision maker to the policy they had without it. That produces a
behaviour a penalty cannot: increasing accuracy while increasing latency can
strictly *decrease* decision value, discontinuously.

**Information time forbids future-oracle leakage.** A source igniting after `s` is
unknowable, and `make_release` restricts the truth to `known_at(truth, s)`
*before* degrading it. Restricting afterwards would let an operator move an
unknowable source into the forecast.
`validation.invariants.check_conditional_on_information_time` catches a release that violates
this.

**Staleness is not latency.** When a release *is* available, what degrades the
decision is the age of information `t_d - s >= delta`. A low-latency product
built on stale observations can be worse than a high-latency product built on
fresh ones. `ForecastStream.available_at` therefore picks the **most
informative** available release — largest `s` — not the last to arrive.

**Latency also costs waiting.** A decision maker who holds the order for a
late model run does not pay a score penalty; their departures shift later and
the fire keeps spreading. `ForecastPolicy(max_wait=...)` models this, and it
is what makes latency cost something *continuously* rather than only at the
instant it crosses `t_d`.

## Spotting failure

Spot fires are where "slightly wrong" and "catastrophically wrong for this
decision" diverge most sharply: a spot on the far side of a route converts a
safe route into a trap, and accuracy about the main front does not compensate.

| operator | parameter | behaviour |
|---|---|---|
| `SpotMiss` | `spot_miss_u` | latent uniform in `[0,1]`; the spot is dropped when `u < p_miss` |
| `SpotDelay` | `spot_delay` | `t0' = t0 + spot_delay`, `>= 0` enforced |
| `SpotDisplacement` | `spot_disp_magnitude`, `spot_disp_heading` | independent channel from main-front displacement |

**Why a latent uniform rather than an internal Bernoulli draw.** Thresholding
a latent uniform is what lets a missed spot be *correlated* with, say, a
spread-rate bias. An internal coin flip could not be.

**A negative spot delay is rejected.** A forecast predicting an ignition
*before* it happens is future-oracle information, not error.

**All three default to `kind="spot"` sources only**, so "the spot was missed"
cannot silently delete the main fire.

**Asymmetry (F-08).** Spots can be missed, delayed or displaced, but never
fabricated. The error model therefore understates the cost of over-warning.

## Correlated combination

Channels are combined by a **Gaussian copula**: draw `z ~ N(0, R)`, map to
uniforms `u = Phi(z)`, push each through its own marginal quantile function.

A copula rather than a multivariate normal, because the channels do not share
a family: `eps_theta` is roughly symmetric, `spot_delay` is non-negative, and
`spot_miss_u` must be *exactly* uniform because it is thresholded.

**Independence is never the default by omission.** `CorrelatedErrorModel`
requires the correlation structure to be passed, and
`CorrelatedErrorModel.independent(...)` is the named way to say "we assumed
independence", so that assumption appears in the manifest rather than being
the shape of the silence.

**Two caveats the auditor must not skip:**

* `R` is the correlation of the **latent normals**, not the Pearson
  correlation of the sampled parameters. They coincide only where both
  marginals are normal. Report `realised_correlation()` — measured from a
  sample — not `R`. (F-02)
* A Gaussian copula has **no tail dependence**. Channels that fail together
  *only* in the tail — which is exactly the joint-catastrophe case — are not
  representable. (F-03)

Pairwise correlations also cannot be chosen freely: `corr(a,b) = corr(b,c) =
0.9` forces `corr(a,c) >= 0.62`. A non-PSD matrix is rejected with that
explanation rather than silently repaired.

## Canonical order

`standard_pipeline()` applies operators in `STANDARD_ORDER`:

1. `direction_error`
2. `spread_rate_error`
3. `spatial_displacement`
4. `spot_miss`
5. `spot_delay`
6. `spot_displacement`

Direction precedes displacement because displacement may be expressed relative
to the heading. Every other adjacent pair commutes. The order is fixed anyway,
so that adding a non-commuting operator later changes results visibly rather
than silently.
