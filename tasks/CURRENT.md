# Current

**Status: v0.1 FROZEN.**

This repository is closed to new synthetic wildfire worlds. The counterexample
is complete, classified (`docs/CURRENT_RESULT_STATUS.md`), provenanced
(`docs/PARAMETER_PROVENANCE.md`) and frozen as immutable fixtures
(`experiments/benchmark_fixtures/`). The release report is
`reports/V0_1_FREEZE_REPORT.md`.

## What happens next, and where

The next scientific evidence comes from **outside this repository**:

* **main WildfireGuardian** — empirical Korean-system stress test;
* **`wildfireguardian-osse`** — independent hidden-world experiment;
* **`wildfireguardian-evaluation`** — formal statistical inference;
* **`wildfireguardian-benchmarks`** — general exact semantic reference cases.

This repository's job is to ingest records from the first two, align skill with
downstream outcomes, construct error x latency grids, identify candidate
break-even regions, and export world-level records to the third. See
`docs/REPOSITORY_ROLE.md`.

## Work that is in scope here when the inputs exist

1. **Wire up the record reader** to real Source A / Source B outputs. The
   contract is defined and executable
   (`docs/EXTERNAL_EXPERIMENT_INTERFACE.md`,
   `src/.../interfaces/experiment_record.py`); nothing is integrated yet, by
   instruction.
2. **Grid construction over ingested records** rather than over synthetic
   degradation parameters. The axis machinery is agnostic; what changes is
   where the error coordinates come from.
3. **Export format for `wildfireguardian-evaluation`**, carrying the pairing
   structure and `world_id` intact.

## Work that is explicitly NOT in scope here

* A fifth constructed case, or any further synthetic world.
* Re-tuning the frozen fixtures for anything but a genuine defect.
* Growing the local statistics package.
* Any operational interpretation of the benchmark's numeric thresholds.

## Open questions, carried forward

These were live at the freeze and remain worth answering — but with **external
evidence**, not with more constructed worlds:

1. **How often does the skill/value divergence occur operationally?** The
   benchmark establishes possibility only. This is Source A's question.
2. **How large is it when it occurs?** Source B's question: OSSE has the real
   counterfactual arm that the empirical stress test lacks.
3. **Is the hard wedge edge load-bearing for the case-2 flip?** (A-02.) A
   smooth front should turn the cliff into a gradient. If the flip vanishes
   entirely, the "small error flips the decision" wording needs weakening —
   the mechanism survives either way. Best answered in OSSE, which has a real
   spread model.
4. **How much of the measured value is an artefact of the plug-in policy?**
   (A-08, F-06.) Every `Delta J` here is a lower bound and the size of the gap
   is unknown. An ensemble-consuming policy would measure it.

## Known rough edges, recorded not fixed

* The frontier figure draws only the first crossing in a multi-valued column,
  with a marker. A multi-valued frontier deserves a better visual treatment.
* The skill-versus-value scatter re-runs a full paired study per point; it is
  the slowest part of `demo` and is trivially parallelisable.
* Skill rasterisation dominates `evaluate_world` when skill is on (~4.5 ms vs
  ~1.7 ms). Sweeps switch it off; a coarser skill grid would make it
  affordable to keep on.
