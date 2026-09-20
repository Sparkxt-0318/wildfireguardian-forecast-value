# v0.1 freeze report

**`wildfireguardian-forecast-value`**
**Status: `CONSTRUCTED_BENCHMARK`. Frozen as the decision-value counterexample
and experiment-orchestration layer.**

Measured counts for this release are in
[`generated_metrics.md`](generated_metrics.md); no number in this report is
hand-maintained except the ones quoted from the frozen fixtures, which are
themselves regression-tested.

---

## 1. What has this repository actually demonstrated?

**One proposition, cleanly:**

> Conventional forecast skill is not sufficient, in general, to uniquely
> determine downstream decision value.

It demonstrates this by construction, which is the right instrument for
refuting a sufficiency claim. If two forecasts can have equal conventional
skill and materially different downstream losses, then skill does not
determine value — and one valid construction settles that, with no appeal to
how often it happens.

The construction exhibits six distinct phenomena, each frozen as a fixture and
asserted by a named test in `tests/test_conceptual_properties.py`:

| # | phenomenon | evidence in the benchmark |
|---|---|---|
| P1 | **Similar skill, different value** | ±15° heading errors differ by <0.02 CSI; mean `ΔJ` +19.4 h vs +2.6 h. At ±18° the signs are opposite: +19.0 h vs −2.2 h |
| P2 | **Accurate but late** | CSI 1.00, arrival-time RMSE 0, `ΔJ` **exactly 0** — the release is not in the information set at the decision time |
| P3 | **Crude but timely** | CSI 0.46, full decision value realised |
| P4 | **Forecast harm** | forecast-aware policy `ΔJ ≈ −49.9 h` against a forecast-free trigger that was already correct |
| P5 | **Baseline match** | a world distribution where the trigger is always right: `ΔJ` identically 0, equivalence declared at a ±1 h margin |
| P6 | **Multi-valued frontier** | columns with more than one `ΔJ = 0` crossing, under the short-wait construction |

The headline arrangement: across the four cases, **ranking the forecasts by
footprint CSI produces the reverse of ranking them by realised decision
value.** Every forecast that captures all of the available value scores worse
on CSI than every forecast that captures none of it.

It also produced durable secondary artefacts: an explicit forecast taxonomy
(`forecast_classes.py`), latency modelled as availability rather than as a
score penalty, a statistical protocol whose unit of analysis is the world, and
a quantified pseudoreplication diagnostic (ICC 0.75, design effect 30.4, naive
standard error 5.5× too small).

---

## 2. Which results are constructed?

**All of them.** Every result carries `result_status: CONSTRUCTED_BENCHMARK`
in its frozen fixture, and `tests/test_benchmark_fixtures.py` asserts it.

There is no empirical result in this repository, and no observation of any
real wildfire, forecast system, road network or evacuation. The "truth" is a
constant-rate circular wedge on a flat plane; the "forecasts" are that truth
with arithmetic operators applied to it.

Full statement: [`../docs/CURRENT_RESULT_STATUS.md`](../docs/CURRENT_RESULT_STATUS.md).

---

## 3. Which parameters were deliberately tuned?

About a dozen, several of them more than once, all **after seeing results**.
The complete record is
[`../docs/PARAMETER_PROVENANCE.md`](../docs/PARAMETER_PROVENANCE.md); the
substantive ones:

| parameter | tuned how |
|---|---|
| **route A via-point** `(9, 3)` | set so its bearing from the ignition is 18.43°. **Every heading threshold in this repository is arithmetic on that number.** |
| **route B corridor** `y = 11` | moved down from `y = 15`, where route B could never be cut and waiting was therefore free |
| **route B west via-point** `(-1, 11)` | added purely to make route B longer than route A again after the corridor move |
| **safe haven** `(16, 12)` | moved north from `(16, 8)`, which had been inside the fire wedge |
| **spread rate** `6.0` km/h | swept 5.0–7.0; set where route A's margin straddles zero |
| **wedge half-angle** `30°` | widened from 25° so the fire could reach route B at all |
| **trigger distance** `1.5` km | lowered from 2.5 km, where the trigger was already correct and there was no decision to improve |
| **waiting window** `1.6` h | raised from 0.8 h so latency costs something continuously instead of being one cliff |
| **skill horizon** `2.5` h | lowered from 4.0 h, where the fire left the grid and CSI saturated at 1.0 |
| **case heading offsets** `+18°`, `−17°` | selected by scanning to straddle the 18.43° bearing; the pairing was *found*, not predicted |

Marked `BENCHMARK_CONSTRUCTION` throughout. **Nothing is marked
`PREDECLARED_EMPIRICAL`**, because nothing was fixed in advance and tested
against data the author did not construct.

Constructing a counterexample this way is legitimate. Presenting it as a
measurement would not be, which is what §2 and the figure banners exist to
prevent.

---

## 4. What does the CSI/value counterexample establish?

That the implication **"higher conventional skill ⟹ better protective
decisions"** is false as a general rule, and false in more than one way:

* **Insensitivity.** Skill can degrade a long way with no decision
  consequence, when the error lands away from the decision boundary (case 1:
  CSI 1.00 → 0.57, decision value unchanged).
* **Hypersensitivity.** A smaller error, scoring *better* on CSI and on FAR,
  can flip the decision and destroy all the value (case 2: CSI 0.65, value
  fraction 1.00 → 0.00).
* **Sign, not magnitude.** +18° is free and −17° is catastrophic in the same
  construction. A metric on `|error|` cannot represent this.
* **Timing is not a skill dimension at all.** A release with perfect scores
  and no availability has decision value exactly zero, and no skill score has
  a clock (case 4).

It also establishes that the *direction of the error relative to the decision
boundary* is a first-class quantity that conventional verification does not
measure, and that any procedure ranking forecast systems by CSI alone is
making an assumption it has not tested.

---

## 5. What does it not establish?

Stated flatly, because each is an inference a reader may be tempted to draw:

* **Not the real-world prevalence** of skill/value divergence. The cases were
  built to exhibit it. It could be near-universal or vanishingly rare
  operationally; nothing here distinguishes those.
* **Not Korean operational thresholds.** No Korean fuels, terrain, wind
  climatology, road network, evacuation behaviour or agency doctrine is
  represented.
* **Not a required heading accuracy.**
* **Not a required latency.**
* **Not real wildfire forecast performance.** No real forecast was evaluated.
* **Not that forecasts are generally not worth having.** The benchmark
  contains large regions where the forecast is worth a great deal. Neither the
  favourable nor the unfavourable regions carry over.
* **Not the magnitude of anything.** `ΔJ ≈ 36 h` is a property of a chosen
  loss ratio and a chosen scenario.

Two structural limits are worth repeating: every `ΔJ` here is a **lower
bound**, because the policies are plug-in minimisers rather than optimal under
uncertainty (A-08); and the decision is made **once**, so a forecast's option
value is entirely absent (A-13).

---

## 6. Which synthetic thresholds must not be interpreted operationally?

| value | what it actually is |
|---|---|
| **≈ 1.33 h** latency (frontier's flat section) | where a chosen 1.6 h waiting window, 0.6 h information time and 1.0 h decision time intersect a robust route made cuttable at ≈0.95 h of delay |
| **≈ 0.48 h** latency at −15° | the same arithmetic near the route corner |
| **≈ −19°** direction error, beyond which no break-even exists | `heading + half_angle < 18.43°` — arithmetic on a route corner's bearing and a chosen 30° half-angle |
| **±17–18°** case heading offsets | chosen to straddle that same 18.43° bearing |
| **0.5 h** case-4 latency | chosen to straddle the decision time |
| **`L/c_t = 50`** | a declared ethical exchange rate |
| **ICC 0.75, design effect 30.4** | properties of a 40-receptor community in a shared-fate scenario; the *mechanism* generalises, the number does not |

Every figure carries a `CONSTRUCTED SYNTHETIC BENCHMARK` banner and a footnote
saying the axis values are not operational requirements
(`tests/test_plotting.py::TestBenchmarkProvenanceOnFigures`).

---

## 7. Which future inputs will come from the main repository?

**Source A — empirical Korean-system stress-test outputs**, as records with
`source_type: MAIN_EMPIRICAL_STRESS_TEST`.

Real system, real decisions, real outcomes. High evidentiary weight for
*occurrence*; heavily confounded for *magnitude*, because policies were not
randomised and the counterfactual arm is generally unobserved. These records
can answer "does the divergence occur in the operational system, and at what
rate".

Contract: [`../docs/EXTERNAL_EXPERIMENT_INTERFACE.md`](../docs/EXTERNAL_EXPERIMENT_INTERFACE.md).

---

## 8. Which future inputs will come from OSSE?

**Source B — independent hidden-world experiment outputs**, as records with
`source_type: OSSE_HIDDEN_WORLD`.

Truth known to the experiment and hidden from the policies, so the
counterfactual arm is real and the comparison genuinely paired. High
evidentiary weight for *magnitude*; lower for *external validity*, because the
world is simulated. Crucially, OSSE is **independent of this repository** —
this repository must not also generate the truth it judges forecasts against.

Same record contract. The four constraints it enforces (mandatory `world_id`
distinct from `event_id`; both forecast clocks or neither; availability
unknowable without a decision time; a failed record must state a
`failure_reason`) exist because each corresponds to an error this repository
spent v0.1 learning to avoid.

---

## 9. What will be delegated to the evaluation library?

**All formal statistical inference**, to `wildfireguardian-evaluation`:
multiplicity across grid cells, hierarchical structure across sources,
model-based estimation of break-even regions, decision-theoretic stopping, and
any confidence statement about a multi-world experiment.

This repository **exports** point estimates, pairing structure, grid geometry
and world-level records with the unit of analysis labelled. It does **not**
make the confidence claims on them.

What is deliberately **retained** here, as a lightweight diagnostic layer that
does not grow: paired world-level summaries, the cluster bootstrap, effect
sizes and equivalence tools as demonstrations of the protocol, and the
**pseudoreplication diagnostic** — ICC, design effect, effective sample size,
naive-versus-correct standard error. That last one stays because it is a
property of the experiment design *this* repository constructs.

Two reasons for the split: one place to get inference methodology wrong rather
than two; and a repository that builds the experiment grid should not also
decide what counts as significant on it.

---

## 10. What new work should NOT be added here?

* **More synthetic wildfire worlds.** The counterexample is complete. A fifth
  constructed case adds no evidence.
* **Further tuning of the frozen fixtures.** They are a regression boundary.
  Change them only for a genuine defect, and say so in the commit.
* **Operational interpretation of the benchmark's numbers.** §6 lists the
  specific values.
* **Expansion of the local statistics package.** Inference goes to
  `wildfireguardian-evaluation`.
* **Nature-model simulation** (`wildfireguardian-osse`), **production
  forecasting** (main repository), **assisted mission search**, **historical
  evidence retrieval**, or **general exact semantic reference cases**
  (`wildfireguardian-benchmarks`).
* **Integration with OSSE or routing.** The interface is defined; wiring it up
  is a separate, later decision.

Full statement: [`../docs/REPOSITORY_ROLE.md`](../docs/REPOSITORY_ROLE.md).

---

## Freeze mechanics

| mechanism | what it holds in place |
|---|---|
| `experiments/benchmark_fixtures/*.json` | every case arm's geometry, truth, forecast, availability, skill, actions, loss, `ΔJ`, hand derivation and intended interpretation |
| `wg-forecast-value freeze-benchmarks` | recomputes and compares; never rewrites without `--write` |
| `tests/test_benchmark_fixtures.py` | the same comparison, in CI |
| `tests/test_conceptual_properties.py` | the six phenomena, by name |
| `tests/test_freeze_documents.py` | the freeze documents still say what the freeze requires |
| `tests/test_release_metrics.py` | no document states a hand-maintained count |
| figure banners | provenance travels on the figure, which outlives the document |

## What changed in the freeze

Terminology (the ambiguous phrase `perfect forecast` retired in favour of four
explicit classes, with deprecated aliases retained), mortality language removed
from prose and source, the
test-count discrepancy resolved by generating counts instead of typing them,
results reclassified and figures banner-stamped, thresholds de-operationalised,
fixtures frozen, provenance recorded, and the external input contract defined
without integrating anything.

**After this release: no further synthetic wildfire worlds are developed in
this repository.** The next scientific evidence comes from the main
WildfireGuardian empirical experiment and the independent OSSE experiment.
