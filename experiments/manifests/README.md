# Experiment manifests

Ready-to-run configurations. Each is a complete description of a study; the
CLI resolves it, fills in defaults, and writes the resolved version next to
the results as `manifest.json`.

```bash
wg-forecast-value run-toy-study experiments/manifests/<name>.yaml
wg-forecast-value sweep         experiments/manifests/<name>.yaml
wg-forecast-value estimate-frontier experiments/runs/<name>/sweep.parquet
```

| manifest | what it is for |
|---|---|
| `default_study.yaml` | The reference paired world-level study: a `PRESENT_STATE_ORACLE` (undegraded, but still conditioned on the information time), 200 worlds. Produces the clustering diagnostics quoted in the README. |
| `frontier_direction_latency.yaml` | **The primary demonstration.** The (direction error × latency) sweep behind `figures/frontier_direction_latency.png`. |
| `frontier_short_wait.yaml` | The same sweep with a shorter `max_wait`, which produces **columns with two zero crossings**. Kept as the regression fixture for the non-monotone frontier path (F-10): if the estimator ever starts assuming a single crossing, this is what catches it. |
| `correlated_error_system.yaml` | Value of a forecast *system* rather than of one error magnitude: a correlated error vector is drawn per world. Direction and rate errors are coupled (both follow a wind error) and a spread-rate bias is correlated with missing a spot fire. |
| `rate_error_frontier.yaml` | Frontier in (spread-rate error × latency). Included because `eps_r` is the asymmetric coordinate (F-14) — compare its shape against a sweep in `log(r̂/r)` before reading the asymmetry as physical. |
| `loss_sensitivity_low.yaml`, `loss_sensitivity_high.yaml` | The same study at loss ratios of 10 and 200 instead of 50. Run all three and report the range over which the **sign** of `Delta J` is stable, not just the point estimate (F-07). |

Note that `error_model` and `degradation.params` answer different questions.
A drawn error model asks *what is this forecast system worth*; fixed
parameters ask *what is an error of exactly this size worth*. Only the second
belongs on a frontier axis.
