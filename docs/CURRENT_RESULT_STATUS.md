# Current result status

**Every result in this repository is classified `CONSTRUCTED_BENCHMARK`.**
**No result in this repository is classified `EMPIRICAL_RESULT`.**

That classification is machine-readable: it is stamped into every frozen
fixture in `experiments/benchmark_fixtures/`, asserted by
`tests/test_benchmark_fixtures.py::test_fixture_is_labelled_as_constructed`,
and printed on every figure as `CONSTRUCTED SYNTHETIC BENCHMARK`.

---

## The two classifications

| classification | meaning |
|---|---|
| **`CONSTRUCTED_BENCHMARK`** | A fixture built to make a phenomenon visible and checkable. Its parameters were chosen — in several cases explicitly tuned — so that the phenomenon appears. It demonstrates that something is **possible** and gives a regression boundary. It measures nothing about the world. |
| **`EMPIRICAL_RESULT`** | A measurement from a pre-declared experiment against data the analyst did not construct. This repository contains none. |

The distinction is not a formality. A constructed benchmark and an empirical
result can look identical in a table, and the difference between "we built a
case where X happens" and "X happens" is the whole of the scientific content.

---

## What the four cases and the frontier establish

The four cases (`docs/DECISION_VALUE.md`) and the break-even frontier
establish exactly one proposition:

> **Conventional forecast skill is not sufficient, in general, to uniquely
> determine downstream decision value.**

This is a *counterexample* result, and counterexamples are the one thing a
constructed fixture establishes cleanly. The existence of a single valid
construction in which two forecasts with equal conventional skill produce
materially different downstream losses is enough to refute the universal claim
"better skill implies better decisions". No amount of prevalence data is
needed, and none is offered.

Concretely, the benchmark exhibits:

* two forecasts of near-identical footprint CSI whose mean decision values
  differ by an order of magnitude, one of them with the **better** CSI and the
  **better** false-alarm ratio producing the worse decision;
* a high-skill release with **exactly zero** decision value because it is not
  available at the decision time;
* a low-skill release with full decision value because it is;
* a forecast-aware policy that is strictly worse than a forecast-free trigger;
* a break-even set that is not a monotone single-valued function of forecast
  error.

Each is frozen as a fixture with its hand derivation, and each is asserted by a
named test in `tests/test_conceptual_properties.py`.

---

## What the cases do NOT establish

Stated flatly, because these are the inferences a reader is most likely to draw
and every one of them is unsupported by anything in this repository.

**These results do NOT establish the real-world prevalence of the phenomenon.**
The cases were constructed to exhibit it. They say nothing about how often
skill and decision value diverge in operational wildfire forecasting — that
could be almost always or almost never, and this repository cannot distinguish
those. Answering it requires the empirical stress test in the main
WildfireGuardian repository and the independent hidden-truth experiment in
`wildfireguardian-osse`.

**These results do NOT establish Korean operational thresholds.** Nothing here
is calibrated to Korean fuels, terrain, wind climatology, road networks,
evacuation behaviour, agency doctrine, or decision timelines. The scenario is a
flat plane with two straight-ish roads.

**These results do NOT establish a required heading accuracy.** The
approximately 18-degree figures in the cases are properties of a wedge whose
half-angle was set to 30 degrees and a route whose corner sits at a bearing of
18.43 degrees from the ignition. Move the corner and the number moves with it.

**These results do NOT establish a required latency.** The latency breakpoints
are properties of a constructed decision time, a constructed waiting window,
and a robust route that was deliberately made cuttable at a particular delay.

**These results do NOT establish real wildfire forecast performance.** No real
forecast was evaluated. The "forecasts" here are exact truth with arithmetic
operators applied to it.

**These results do NOT establish that forecasts are generally not worth
having.** The benchmark contains regions where the forecast is worth a great
deal. Neither the favourable nor the unfavourable regions carry over.

---

## Numbers that must not be read operationally

The following appear in this repository's outputs and are **properties of the
constructed geometry**:

| value | what it actually is |
|---|---|
| ~1.33 h latency at the frontier's flat section | where a constructed 1.6 h waiting window, a 0.6 h information time and a 1.0 h decision time happen to intersect a robust route made cuttable at ~0.95 h of delay |
| ~0.48 h latency at −15° | the same, at a column where the wedge edge is close to the route corner |
| ~−19° direction error, beyond which no break-even exists | `heading + half_angle < 18.43°`, i.e. arithmetic on a route corner's bearing and a chosen 30° half-angle |
| ±17–18° heading errors in cases 1 and 2 | chosen to straddle that same 18.43° bearing |
| 0.5 h latency in case 4 | chosen to straddle the decision time |
| loss ratio `L/c_t = 50` | an ethical exchange rate chosen for the fixture |

Full provenance for each is in `docs/PARAMETER_PROVENANCE.md`, including which
were tuned and in which direction.

**Any of these quoted as an operational requirement is a misreading of this
repository**, and the figures carry a banner saying so.

---

## Why the benchmark is still worth freezing

A counterexample that is reproducible, hand-derivable, and regression-tested is
a durable scientific object. It:

* refutes a sufficiency claim that is widely assumed in forecast evaluation;
* gives the empirical experiments a **null hypothesis worth testing** —
  "does this divergence occur at operationally relevant rates?" — rather than a
  vague suspicion;
* fixes the vocabulary (`docs/GLOSSARY.md`, `forecast_classes.py`) and the
  statistical protocol (`docs/STATISTICAL_PROTOCOL.md`) that the empirical work
  will need;
* provides a regression boundary, so that when the machinery is later pointed
  at real records, a change in its behaviour is detectable.

What it does not do is measure anything. That is the next repositories' job;
see `docs/REPOSITORY_ROLE.md` and `docs/EXTERNAL_EXPERIMENT_INTERFACE.md`.
