# Scope

## In scope (v0.1)

* **Forecast degradation operators** with explicit, documented semantics:
  spread-rate error, direction error, spatial displacement, temporal latency,
  and three modes of spotting failure, composable with correlated error.
* **Latency modelled as availability**, with separate information and
  availability clocks, and a decision maker who may wait.
* **A synthetic decision laboratory**: small, hand-checkable evacuation
  scenarios with two routes, a forecast-free trigger baseline, a plug-in
  forecast policy, and a clairvoyant upper bound.
* **A generic downstream loss** `J(a, omega)` with an explicit, swappable
  exchange rate between travel time and burnover.
* **Paired world-level statistics**: cluster bootstrap, effect sizes,
  confidence intervals, equivalence and non-inferiority testing, and
  clustering diagnostics that quantify the "residents are not events" error.
* **Break-even frontier estimation** with bootstrap bands, making no
  monotonicity assumption.
* **Figures** demonstrating that skill and decision value come apart.
* **A CLI** with reproducible manifests.

## Explicitly out of scope (v0.1)

| Out of scope | Why, and what would change if it were added |
|---|---|
| **Any real wildfire data** | This repository is about the *method*. Real data brings calibration, validation and provenance questions that would swamp the methodological point. Every number here is synthetic. |
| **Integration with other WildfireGuardian repositories** (OSSE, routing) | Requested explicitly. Nothing here imports or assumes another repository's interfaces. The `Outcome` / `LossModel` seam is where such an integration would attach. |
| **Physically realistic fire spread** (Rothermel, terrain, fuel moisture, wind fields) | The wedge model is chosen for hand-checkability. A realistic spread model would make every fixture opaque and would not change any conclusion about skill-versus-value. It would change the *shape* of the frontier. |
| **False-alarm spotting** (a forecast inventing a spot fire that did not occur) | The error model is currently asymmetric: spots can be missed, delayed or displaced, but not fabricated. This understates the cost of over-warning. Recorded as F-08. |
| **Ensemble and probabilistic forecasts as first-class objects** | `ensemble_burn_probability` and the Brier score exist, but no policy consumes a probability. A risk-averse or expected-loss-minimising-over-ensemble policy would extract more value from the same forecast (A-08). |
| **Sequential / re-decidable problems** | The decision is made once, at a fixed time. Real evacuation is a sequence of revisable decisions, where the value of a forecast includes its option value. This is the single largest conceptual gap. |
| **Multiple communities, resource allocation, fairness** | One community, one decision. Distributional questions ("whose route gets cut") are not representable. |
| **Cost of running the forecast system** | `Delta J` is gross value, not net of procurement or compute. |
| **Decision-maker behaviour** (trust, compliance, alert fatigue) | Policies here are mechanical. A forecast that is right but disbelieved has zero realised value, and nothing here models that. |

## What a reader may and may not conclude

**May:** that the distinction between skill and decision value is real,
quantifiable, and large; that the machinery to quantify it works and is
validated against closed-form answers; that a break-even frontier can be
estimated with honest uncertainty.

**May not:** anything about how good any real wildfire forecast is, what
latency any real agency should demand, or where any real break-even sits.
