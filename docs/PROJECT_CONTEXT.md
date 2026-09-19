# Project context

## What this repository is

An experimental-mathematics and statistics workbench for one question:
**how good must a wildfire forecast be before it deserves to change a
protective decision?** (`RESEARCH_QUESTION.md`.)

It is a *methods* repository. It runs entirely on internal synthetic fixtures
and deliberately depends on no other WildfireGuardian repository.

## How the pieces fit

```
  world distribution          forecast degradation           decision
  (synthetic_decisions)  ->   (degradation)            ->    (synthetic_decisions)
        truth omega              forecast state,                action a
                                 issued at s,
                                 available at s+delta
                                      |                            |
                                      v                            v
                                 skill_metrics                 decision_value
                                 (never read by                J(a, omega)
                                  any decision)                Delta J per world
                                                                   |
                                                                   v
                                                             statistics  ->  frontiers
                                                             (world-level)   (Delta J = 0)
```

The single most important structural fact: **`skill_metrics` and
`decision_value` do not import each other.** No score influences an action, and
no action influences a score. The two can therefore be shown to move
independently, which is the repository's whole purpose.

## Package map

| Package | Responsibility |
|---|---|
| `fields/` | Plane geometry conventions, the wedge fire model, the arrival-time field, rasterisation. |
| `degradation/` | Degradation operators, latency/availability semantics, the Gaussian-copula correlated error model. |
| `skill_metrics/` | Traditional prediction scores. Isolated by construction. |
| `synthetic_decisions/` | Routes, policies, worlds, and the four hand-designed cases. |
| `decision_value/` | The loss `J(a, omega)` and the paired-world `Delta J` evaluation. |
| `statistics/` | World-level paired inference: cluster bootstrap, effect sizes, equivalence, clustering diagnostics. |
| `frontiers/` | Sweeping `Delta J` over a parameter grid and extracting the `Delta J = 0` set without assuming monotonicity. |
| `plotting/` | Figures, with a validated diverging/categorical palette. |
| `validation/` | Hand-solvable closed-form examples and structural invariants. |
| `cli/` | `wg-forecast-value`, configuration, manifests, reporting. |
| `outcomes.py` | `Outcome` lives at the root so physics and valuation need not depend on each other. |

## Reading order

1. `RESEARCH_QUESTION.md` — what is being asked and why it is not trivial.
2. `DECISION_VALUE.md` — the definitions, the four cases, the frontier.
3. `FORECAST_ERROR_MODEL.md` — what each operator does and what it assumes.
4. `STATISTICAL_PROTOCOL.md` — the unit of analysis and what the intervals mean.
5. `ASSUMPTIONS.md` and `FAILURE_MODES.md` — where this is wrong or could mislead.
6. `VALIDATION.md` — the closed-form checks anyone can redo on paper.

## Provenance of every number

Every command that writes results also writes `manifest.json`: the fully
resolved configuration, the scenario, the pipeline, and the error model. A
result without a manifest is not a result. Figures carry a footer stating that
the fixtures are synthetic.
