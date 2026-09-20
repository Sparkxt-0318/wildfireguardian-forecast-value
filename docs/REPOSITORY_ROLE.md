# Repository role

What this repository is for after the v0.1 freeze, and — more importantly —
what it is not for.

---

## The pipeline

```text
          ingest forecasts / policy outcomes
          (docs/EXTERNAL_EXPERIMENT_INTERFACE.md)
                          |
                          v
          align skill with downstream outcomes
          (skill_metrics x decision_value, kept apart by construction)
                          |
                          v
          construct error x latency experiment grids
          (frontiers.grid, common random numbers)
                          |
                          v
          identify candidate break-even regions
          (frontiers.estimate -- every crossing, no monotonicity assumed)
                          |
                          v
          export world-level records
                          |
                          v
              wildfireguardian-evaluation
              (formal statistical inference)
```

The repository's job is to turn *forecasts and outcomes* into *a well-posed
question about break-even*, and to hand that question — with its pairing
structure intact and its unit of analysis labelled — to a library whose job is
answering it.

---

## What it owns

**The skill/value distinction.** The vocabulary (`docs/GLOSSARY.md`), the four
information classes (`forecast_classes.py`), and the frozen counterexample
that shows the two are not the same quantity.

**Degradation operators and latency semantics.** Exact, documented,
hand-checked. Latency as availability, never as a score penalty.

**Experiment-grid construction.** Error × latency sweeps with common random
numbers across cells, which is what makes cell-to-cell differences signal
rather than Monte-Carlo noise.

**Break-even region identification.** Candidate regions, every zero crossing,
monotonicity measured rather than assumed, and columns where no frontier
exists reported as such.

**World-level record export.** Records leave here with `world_id` intact and
the unit of analysis labelled, because that is the one thing a downstream
inference library cannot reconstruct if it is lost.

**The frozen constructed benchmark.** As a regression boundary, not as
evidence about the world.

---

## What it does not own

| not owned | who does | why not here |
|---|---|---|
| **Nature-model simulation** | `wildfireguardian-osse` | The wedge model exists to be hand-checkable, not realistic. A repository that both generates the truth and judges the forecast against it has no independence. |
| **Production wildfire forecasting** | main WildfireGuardian | Nothing here produces a forecast. The "forecasts" here are truth with arithmetic applied. |
| **Assisted mission search** | elsewhere | Out of scope entirely. |
| **Historical evidence retrieval** | elsewhere | This repository holds no corpus and makes no retrieval claims. |
| **Final statistical inference** | `wildfireguardian-evaluation` | See below. |
| **General exact semantic reference cases** | `wildfireguardian-benchmarks` | The hand-checked examples here cover *this* repository's semantics; general reference cases belong in one place. |

---

## Why inference is delegated

The local statistics package is a **lightweight diagnostic layer** and must
stay one. It keeps:

* paired world-level summaries;
* the cluster bootstrap;
* effect sizes and equivalence tools, as *demonstrations* of the protocol;
* the pseudoreplication diagnostic — the ICC / design-effect / naive-SE-ratio
  report — because that is a property of the experiment design this
  repository constructs, and the design is exactly what the number is about.

It does not grow. Formal inference for multi-world experiments —
multiplicity across grid cells, hierarchical structure across sources,
model-based estimation of break-even regions, decision-theoretic stopping —
belongs in `wildfireguardian-evaluation`, for two reasons:

1. **One place to get it wrong.** Inference methodology that lives in two
   repositories diverges, and the divergence surfaces as two different
   confidence intervals for the same experiment.
2. **Independence.** A repository that constructs the experiment grid should
   not also decide what counts as significant on it. The pseudoreplication
   error this repository documents is exactly the kind of thing an independent
   inference layer is there to catch.

So: **point estimates, pairing structure and grid geometry are exported;
confidence statements are not made here.**

---

## What must not be added here

* **More synthetic wildfire worlds.** The counterexample is complete. The
  next scientific evidence comes from the main empirical experiment and from
  OSSE, not from a fifth constructed case.
* **Further tuning of the frozen fixtures.** They are a regression boundary.
  Change them only for a genuine defect, and say so in the commit.
* **Operational interpretation of the benchmark's numbers.**
  `docs/CURRENT_RESULT_STATUS.md` lists the specific values that must not be
  quoted as requirements.
* **A local expansion of the statistics package.** See above.
* **Integration with OSSE or routing.** The interface is defined; wiring it
  up is a separate, later decision.
