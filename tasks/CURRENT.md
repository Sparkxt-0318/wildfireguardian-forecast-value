# Current

**Status: v0.1 complete.** The definition of done in the brief is met; see
`COMPLETED.md` for the evidence and `ROADMAP.md` for what comes next.

## Immediate next step

**R1 — sequential, revisable decisions** (`ROADMAP.md`). It is the single
assumption (A-13) whose relaxation would most change the conclusions: with a
revisable decision, a late forecast is not worth zero, it is worth whatever it
saves on the next decision, and the whole latency axis of the primary figure
would change meaning.

Suggested first move, small enough to be reversible: add a second decision
point at `t_d + Δ` and let the forecast policy defer. That requires a
`Decision` that can say "decide again later", and a loss that prices the
deferral through the same arrival-time arithmetic that prices waiting today.

## Open questions, in priority order

1. **Is the hard wedge edge load-bearing for Case 2?** (A-02, R4.) If a smooth
   front turns the Case 2 cliff into a gradient, the "small error flips the
   decision" claim needs re-wording — not withdrawing, since the *mechanism*
   survives, but the word "flips" would be doing work the model no longer
   supports.
2. **How much of the measured `Delta J` is an artefact of the plug-in policy?**
   (A-08, R3.) Everything reported here is a lower bound. The size of the gap
   is unknown and is a result in itself.
3. **What does the frontier look like against `log(r̂/r)` instead of `ε_r`?**
   (F-14.) The asymmetry of the multiplicative parameterisation may be doing
   visual work that the physics does not.
4. ~~**Does the sign of `Delta J` survive a change in the loss ratio?**~~
   **Answered.** Run at `L/c_t` in `{0.05, 0.1, 0.12, 0.15, 0.2, 0.5, 1, 5,
   10, 50, 200}` on 200 worlds: the sign is positive throughout, a 4000-fold
   range. Magnitude scales close to linearly above `L/c_t = 5`. The realised
   *fraction* of VPI dips sharply around `L/c_t ~ 0.12` (to 0.30, from 0.92),
   which is where the detour cost and the burnover cost become comparable and
   the decision is genuinely finely balanced — the interesting regime, and the
   one where a forecast has the least room to help. Still outstanding: the same
   sweep across the **full frontier grid** rather than at a single forecast
   setting, which would show whether the frontier's *shape* moves even though
   its sign does not.

## Known rough edges

* `frontier_short_wait.yaml` produces columns with two zero crossings, which
  is deliberate — it is the regression fixture for non-monotonicity — but the
  frontier figure then draws only the first crossing with a marker. A
  multi-valued frontier deserves a better visual treatment than a marker.
* The skill-versus-value scatter re-runs a full paired study per point. It is
  the slowest part of `demo` and is trivially parallelisable.
* `RasterGrid` skill computation dominates `evaluate_world` when skill is on
  (4.5 ms versus 1.7 ms). Sweeps switch it off, but a coarser skill grid would
  make it affordable to keep on.
