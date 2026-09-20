# Parameter provenance

Which parameters in this repository were **chosen or adjusted to expose the
phenomenon**, and which were not.

Every parameter below is marked:

| marker | meaning |
|---|---|
| **`BENCHMARK_CONSTRUCTION`** | Selected or tuned, after seeing results, so that the intended phenomenon is visible. Post-hoc. |
| `STRUCTURAL` | Fixed by the model's definition or by a convention, not tuned against outcomes. |
| `ARBITRARY_BUT_DECLARED` | A free choice that had to be made; not tuned, and stated so it can be varied. |

**Nothing here is `PREDECLARED_EMPIRICAL`.** No parameter in this repository
was fixed in advance of seeing results and then tested against data the author
did not construct. Treating any of it as a pre-registered empirical finding
would be wrong.

This document exists because post-hoc construction is only a problem when it is
concealed. Constructing a counterexample is a legitimate and necessary
activity; presenting a constructed counterexample as a measurement is not.

---

## Route geometry — `BENCHMARK_CONSTRUCTION`

| parameter | value | how it was arrived at |
|---|---|---|
| community | `(2, 8)` km | chosen so the escape routes, not the town, are what the fire threatens |
| safe haven | `(16, 12)` km | **moved during construction.** It was originally at `(16, 8)`, which sat inside the fire wedge — the "safe haven" was not safe and route B's margin was finite for the wrong reason. Moved north until it was outside the wedge for the nominal world. |
| route A via-point | `(9, 3)` km | tuned so route A's minimum bearing from the ignition is `atan2(3, 9) = 18.43°`. **Every heading-error threshold in this repository is arithmetic on that number.** |
| route B corridor | `y = 11`, via `(-1, 11)` and `(16, 11)` | **tuned twice.** First at `y = 15`, where route B could never be cut and waiting was therefore free; lowered to `y = 11` so the wedge reaches it and a ~0.95 h delay closes it. The western via-point `(-1, 11)` was added purely to make route B longer than route A (22.24 km vs 20.0 km) after the corridor change had made it shorter. |
| travel speed | `20` km/h | `ARBITRARY_BUT_DECLARED`; a congested-evacuation figure, not calibrated |
| route sample spacing | `0.05` km | `STRUCTURAL`; discretisation, with a known one-sided error (A-05) |

## Fire parameters — `BENCHMARK_CONSTRUCTION`

| parameter | value | how it was arrived at |
|---|---|---|
| nominal spread rate | `6.0` km/h | **tuned.** Swept over 5.0–7.0 km/h and set where route A's safety margin is a fraction of an hour either side of zero. At 5.0 km/h route A is never overrun and there is no decision; at 7.0 km/h it is always overrun and the trigger fires unaided. |
| fast-world rate (case 2b) | `7.0` km/h | **tuned**, selected from the same sweep as the value at which the proximity trigger fires on its own — which is exactly what makes the "forecast harm" case possible |
| wedge half-angle | `30°` | **tuned from 25°.** Widened so the fire could reach route B's corridor at all; at 25° route B was uncuttable. |
| nominal heading | `+5°` | `ARBITRARY_BUT_DECLARED`, roughly east |
| heading spread, rate spread | `6°`, `0.12` log | `ARBITRARY_BUT_DECLARED`; chosen to give a mix of decisive and indecisive worlds |
| spot probability / origin / timing | `0.5`, `(11, 6)`, `+1.1 h` | **tuned** so the spot ignites *after* the decision time, which is what makes a present-state oracle demonstrably different from a future oracle |

## Timing and waiting — `BENCHMARK_CONSTRUCTION`

| parameter | value | how it was arrived at |
|---|---|---|
| decision time | `1.0` h | `ARBITRARY_BUT_DECLARED`, but every latency number is relative to it |
| information time | `0.6` h | **tuned** so that the latency axis has room below the availability cliff |
| waiting window `max_wait` | `1.6` h | **tuned.** At `0.8` h the forecast simply became unavailable partway up the axis and `Delta J` collapsed to exactly zero, producing a flat plateau rather than a frontier. Raised to `1.6` h so that waiting itself becomes costly and the frontier slopes. The `0.8` h configuration is kept deliberately as `experiments/manifests/frontier_short_wait.yaml`, because it is the one that produces multi-valued columns. |
| departure span | `0.25` h | `ARBITRARY_BUT_DECLARED`; gives within-world variation so the clustering diagnostic is non-degenerate |
| trigger distance | `1.5` km | **tuned from 2.5 km.** At 2.5 km the trigger fired in the nominal world and was already correct, so there was no decision for a forecast to improve. |

## Heading offsets in the cases — `BENCHMARK_CONSTRUCTION`

| case | offset | how it was arrived at |
|---|---|---|
| case 1 | `+18°` | **selected from a scan** of `+14°…+22°`. Any of them works; `+18°` was chosen to pair with case 2's magnitude. |
| case 2 | `−17°` | **selected from a scan** of `−16°…−20°`. `−16°` does *not* flip the decision and `−17°` does, because the wedge's upper edge crosses the route corner's `18.43°` bearing between them. The pairing with case 1 — smaller magnitude, better CSI, worse decision — is the constructed headline, and it was found by scanning, not predicted. |
| case 3 | `+10°`, `+60%` rate, 3 km displacement | **selected from a scan** of combined degradations for the largest CSI degradation that still selects the correct action |
| case 4 | `+9°`, `+35%` rate; latency `0.5` h | **tuned.** The latency straddles the decision time by construction; the degradation was chosen to be clearly worse on CSI than the late arm while still selecting the correct action. |

## Loss — `ARBITRARY_BUT_DECLARED`

| parameter | value | note |
|---|---|---|
| `time_cost_per_hour` | `1.0` | fixes the unit of `J` as hours of equivalent delay; `STRUCTURAL` |
| `burnover_loss` | `50.0` | the ethical exchange rate. Not tuned against outcomes, and its influence was measured afterwards rather than assumed: the sign of `Delta J` is stable across `L/c_t` from 0.05 to 200 (`experiments/manifests/loss_sensitivity_*.yaml`). The realised value fraction does collapse near `L/c_t ≈ 0.12`, and the default 50 is not near that regime. |
| near-miss convexity | off | `ARBITRARY_BUT_DECLARED`; available for sensitivity work |

## Grid and skill horizon — `BENCHMARK_CONSTRUCTION`

| parameter | value | how it was arrived at |
|---|---|---|
| skill grid | `110 × 110` over `[-2, 20] × [-4, 18]` km | `ARBITRARY_BUT_DECLARED`, but categorical skill depends on it (F-04) |
| skill horizon | `2.5` h | **tuned from 4.0 h.** At 4.0 h the fire had left the grid, CSI saturated at 1.0, and a large spread-rate error scored as a perfect footprint. This was a real error caught during construction and is recorded as F-04. |

## Statistical parameters — `STRUCTURAL` / `ARBITRARY_BUT_DECLARED`

| parameter | value | note |
|---|---|---|
| worlds per study / per sweep cell | 200 / 120 | `ARBITRARY_BUT_DECLARED`; a compute choice, and the reason p-values here are meaningless |
| bootstrap replicates | 2000 / 400 | `ARBITRARY_BUT_DECLARED` |
| seeds | `11`, `23` | `ARBITRARY_BUT_DECLARED`; not selected over other seeds — the benchmark's phenomena are deterministic per case, and the sweeps were not re-run to find a favourable seed |
| equivalence margin | none | deliberately has no default (D-15); it is a policy input |

---

## Honest summary

The scenario geometry, the fire speed, the wedge width, the trigger radius, the
waiting window, the skill horizon and the case heading offsets were **all
adjusted after seeing results**, in order to make the phenomena visible and
hand-checkable. Roughly a dozen parameters were moved, several of them more
than once, and the sequence is recorded above.

This is appropriate for building a counterexample and inappropriate for
claiming a measurement. The classification in
`docs/CURRENT_RESULT_STATUS.md` follows directly from this document.
