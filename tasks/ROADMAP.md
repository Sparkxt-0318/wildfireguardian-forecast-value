# Roadmap

> **v0.1 is frozen.** The items below are preserved as the analysis that was
> live at the freeze. Most of them have since been **reassigned to other
> repositories** — see `docs/REPOSITORY_ROLE.md`. Nothing in R1–R5 is to be
> built here as another synthetic world.

---

## v0.1 — methods foundation *(complete, frozen)*

Degradation operators with explicit semantics · latency as availability ·
synthetic decision laboratory · paired world-level statistics · non-monotone
frontier estimation with uncertainty · hand-solvable validation · CLI with
manifests. See `COMPLETED.md`.

---

## Reassigned: relaxing the assumptions that most constrain the conclusions

Each item names the assumption or failure mode it addresses, and **where the
work now belongs**. These are no longer this repository's to build.

### R1 — Sequential, revisable decisions

**Now owned by:** `wildfireguardian-osse` (it has the world model); this repository consumes the records. *(A-13; the largest conceptual gap)*
The decision is currently made once. Real protective decisions are revisable,
and a forecast's **option value** — the ability to wait and re-decide — is
entirely absent. Expect this to *increase* measured decision value
substantially, and to change the shape of the latency axis: with a revisable
decision, a late forecast is not worthless, it is worth whatever it saves on
the *next* decision.

### R2 — False-alarm spotting

**Now owned by:** `wildfireguardian-osse`. *(F-08)*
Spots can currently be missed, delayed or displaced, never fabricated. The
model therefore systematically favours forecasts over the trigger. Adding a
phantom-spot operator should shrink the blue region of the frontier figure,
and the size of that shrinkage is itself a result.

### R3 — Ensemble-consuming policies

**Now owned by:** main WildfireGuardian (policies) with records evaluated here. *(A-08, F-06)*
Every `Delta J` here is a lower bound, because the plug-in policy is the
weakest honest use of a deterministic forecast. A risk-averse or
expected-loss-over-ensemble policy would extract more from the same forecast.
The gap between plug-in and ensemble value is the value of *communicating
uncertainty*, which is a question worth asking directly.

### R4 — A smooth front

**Now owned by:** `wildfireguardian-osse`. *(A-02)*
Replace the wedge with an elliptical or probability-of-burn front and re-run
every case. Cases 1, 3 and 4 should survive unchanged; Case 2 should soften
from a cliff into a gradient. If Case 2 vanishes entirely, the hard edge was
load-bearing and the repository must say so prominently.

### R5 — Tail-dependent error

**Now owned by:** `wildfireguardian-osse` / `wildfireguardian-evaluation`. *(A-15, F-03)*
Swap the Gaussian copula for a t-copula and re-estimate the frontier. Joint
catastrophes — fast *and* misdirected *and* spot missed — are exactly the
events that flip decisions, and the Gaussian copula cannot represent them.

---

## v0.3 — richer decision structure

* **More than two actions**, including shelter-in-place and staged departure.
  Two actions make every flip binary; three make the decision boundary a
  surface.
* **Multiple communities** and resource contention, which introduces
  distributional questions the current single-community loss cannot express.
* **Decision-maker behaviour** — compliance, trust, alert fatigue. A forecast
  that is right and disbelieved has zero realised value, and nothing here
  models that.
* **Net value**, subtracting the cost of running the forecast system.

---

## Integration *(interface defined at the freeze; wiring deferred)*

The seam is now explicit: `docs/EXTERNAL_EXPERIMENT_INTERFACE.md` and
`src/wildfireguardian_forecast_value/interfaces/experiment_record.py`. An
external experiment supplies records; this repository aligns skill with
outcomes, builds grids, and exports world-level records to
`wildfireguardian-evaluation`.

Nothing in `src/` imports another WildfireGuardian repository, and
`tests/test_external_interface.py::TestNoIntegration` asserts it.

---

## Standing work

* Keep `experiments/manifests/` runnable. A manifest that no longer runs is a
  broken claim.
* Re-run `wg-forecast-value demo` whenever the scenario or the policies change,
  and commit the regenerated figures. Then re-run `freeze-benchmarks` and
  `release-metrics`: a changed fixture is a changed claim, and no count is
  hand-maintained.
* Every new assumption gets an `A-nn`; every new way to be misled an `F-nn`;
  every contested choice a `D-nn`.
