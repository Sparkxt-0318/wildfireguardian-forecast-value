# Statistical protocol

## Rule 0 — the world is the unit of analysis

**A world is one observation. A resident is not.**

A study of 500 synthetic fires with 40 residents each has `n = 500`, not
`n = 20 000`. Residents inside a world share the fire, share the route choice,
and therefore share their fate almost entirely. They are not 20 000 draws from
anything.

This is not a pedantic point; it is the largest available error in this kind
of study, and it is one-directional — it always *overstates* confidence. In
the packaged scenario:

```
  ICC 0.75   design effect 30.4   effective n 264 of 8000 receptors
  a naive receptor-level SE would be 5.5x too small  (0.291 vs 1.607)
```

A 5.5-fold understatement of the standard error turns a null result into a
p-value of `10^-23`.

### How the package enforces it

* Every inference function takes **world-level** values and says so.
* `aggregate_to_worlds` is the only sanctioned route in from receptor-level
  data, so the collapse is a visible step rather than something that either
  happened or did not.
* `clustering_diagnostics` reports the ICC, the design effect, the effective
  sample size and the naive/correct SE ratio, so a study can state the size of
  the error it avoided. `wg-forecast-value run-toy-study` prints it every time.
* The cluster bootstrap resamples **worlds, whole**. When a world is drawn its
  entire receptor block comes with it.

## Pairing

`Delta J` is a paired difference: the same world under two information sets.
All inference is on the vector of `Delta J`. Unpaired comparison of `J_base`
and `J_fc` as two samples would be valid but hopelessly inefficient —
between-world variance dwarfs the effect.

`check_pairing` asserts that two arms cover the same worlds in the same order.

## Intervals

Two are reported side by side so that any disagreement is visible rather than
hidden:

* **Student-t** — conventional and cheap. Assumes approximate normality of the
  *mean*, which is strained here: `Delta J` is close to a two-point
  distribution (the action either flipped or it did not).
* **Cluster bootstrap, BCa** — the default. `Delta J` is strongly skewed (most
  worlds give exactly zero, a few give tens of hours) and the percentile
  interval is noticeably off-centre in that regime. BCa's acceleration is
  estimated by jackknife over worlds.

**Degenerate replicates.** When every world gives the same `Delta J` — common
in a frontier corner where the action never changes — every replicate is
identical and the interval collapses to a point. That is reported as a
zero-width interval with `degenerate: True`, not as `nan`: under this world
distribution the estimate really is exact, and "undefined" would be less
informative than saying so.

## Effect sizes, not p-values

With synthetic worlds, significance measures the compute budget. Run more
worlds and any non-zero effect becomes significant. The CLI prints the p-value
**last**, with that caveat attached.

Three effect sizes are reported instead:

| statistic | why |
|---|---|
| `mean Delta J` with a bootstrap CI | the quantity of interest, in the units of `J` |
| `P(forecast better)` — `P(d>0) + 0.5 P(d=0)` | assumption-free; the right headline for a distribution that is mostly a spike at zero. **Ties are split, never dropped**: a world where the forecast changed nothing is evidence about the forecast, not a missing observation |
| mean fraction of the future-oracle value realised | scale-free and directly interpretable: "captures 92% of what knowing the realised world would be worth" |

`Cohen's d_z` and Hedges' `g` are also computed and are the most misleading of
the set here, because `d` is near two-point and its standard deviation is not
a natural scale.

## Equivalence and non-inferiority

"The forecast did not significantly improve the decision" is **not** evidence
that it made no difference. The question an agency actually asks has the
opposite shape:

* *Is this forecast's decision value close enough to the incumbent's that
  switching is not worth it?* → **equivalence** (`tost`)
* *Is it at least not materially worse?* → **non-inferiority**
  (`non_inferiority`)

Both require a **margin**: how much decision value, in hours of equivalent
delay, counts as material. The margin is a policy input, not a statistical
one, and this package refuses to default it. It is recorded in every result so
the claim cannot travel without it.

Equivalence is declared by **interval inclusion** — the `(1 - 2*alpha)`
interval lies inside `(-m, +m)` — rather than by two p-values, because the
interval is the same object the rest of the package reports and cannot be
misread as a claim about a point null.

**Interpretation traps, stated in the module docstring and here:** failing to
declare equivalence is not evidence of a difference, and equivalence at a
margin of 5 hours says nothing about a margin of 0.5.

## Common random numbers on the frontier grid

Every grid cell is evaluated on the **same** worlds. This is not an
optimisation — with independent worlds per cell, Monte-Carlo noise would swamp
the signal exactly where the differences are smallest, near the frontier.

The cost is that cells are correlated, so their uncertainties may not be
treated as independent either. `bootstrap_frontier_band` therefore resamples
worlds **jointly across the whole grid**: one resampled index vector applied to
every cell. Bootstrapping cells independently would give bands far too narrow
where the surface is flat and wrongly shaped where it is steep.

## Frontier bands

Pointwise over the world distribution: at each `x` the band covers the
crossing position in the stated fraction of replicates. It is **not** a
simultaneous band for the whole curve.

A replicate may fail to cross zero in a column that the point estimate
crosses. Those replicates are counted (`crossing_rate`) and excluded from the
quantile. A column with a crossing rate of 0.6 does not have a frontier with a
95% interval — it has a frontier that exists in 60% of resamples. Reporting
the interval without the rate would misrepresent the estimate's stability, so
the plotting layer fades such columns.

## What the intervals do not cover

A confidence interval here is over **the world distribution the scenario
defines**, and nothing else. It does not cover:

* the fire model (a wedge is not a wildfire);
* the loss function and its exchange rate;
* the policy class (a plug-in rule is not an optimal one);
* the choice of baseline;
* the choice of scenario geometry;
* the grid resolution on a frontier.

Every one of those is larger than the sampling uncertainty the intervals
quantify. Quoting a tight interval as if it bounded the total uncertainty
would be the most misleading thing this repository could do with its own
output.
