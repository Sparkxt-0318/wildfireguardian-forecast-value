# External experiment interface

The input contract for experiment records this repository will eventually
consume. **Defining the contract is not integrating the producers**, and
nothing here imports, invokes or assumes any other WildfireGuardian
repository. The contract is executable —
`src/wildfireguardian_forecast_value/interfaces/experiment_record.py` — so it
cannot drift while nobody is looking.

---

## The two sources

### Source A — main WildfireGuardian

**Empirical Korean-system stress-test outputs.** Real system, real decisions,
real outcomes. `source_type: MAIN_EMPIRICAL_STRESS_TEST`.

The evidentiary weight is high and the confounding is high with it: policies
were not randomised, forecasts and conditions are correlated with each other
and with everything else, and the counterfactual arm is whatever the agency
would have done, which is generally unobserved. Records from this source
answer "does the phenomenon occur in the operational system", not "how large is
it".

### Source B — WildfireGuardian OSSE

**Independent hidden-world experiment outputs.** `source_type:
OSSE_HIDDEN_WORLD`.

The truth is known to the experiment and hidden from the policies, so the
counterfactual arm is real and the comparison is genuinely paired. The
evidentiary weight for *magnitude* is therefore much higher than Source A's,
and for *external validity* much lower, because the world is simulated.

### This repository's own fixtures

`source_type: CONSTRUCTED_BENCHMARK`. Present in the vocabulary so that frozen
benchmark records can flow through the same pipeline as a regression check —
**never** so they can be pooled with measurements. See
`docs/CURRENT_RESULT_STATUS.md`.

**Records of different `source_type` are never pooled without an explicit
decision.** That is what the field is for.

---

## The record

One row = **one policy outcome in one world/event**.

```yaml
world_id:                    # str, required. THE UNIT OF ANALYSIS.
event_id:                    # str, required. An occurrence within a world.
source_type:                 # str, required. MAIN_EMPIRICAL_STRESS_TEST |
                             #   OSSE_HIDDEN_WORLD | CONSTRUCTED_BENCHMARK
policy_id:                   # str, required. Which decision rule acted.
forecast_id:                 # str | null. null for a forecast-free policy.
forecast_issue_time:         # float | null. Information time s.
forecast_availability_time:  # float | null. s + delta.
skill_metrics:               # {str: float}, required. Producer-defined. May be {}.
action:                      # str, required. The action taken.
loss:                        # float, required. Smaller is better.
mission_success:             # bool, required.
failure_reason:              # str | null. Required when mission_success is false.

# optional, strongly encouraged
decision_time:               # float | null. When the action was chosen.
loss_units:                  # str. Default "unspecified" -- please override.
forecast_class:              # str | null. One of the four in forecast_classes.py
extra:                       # {str: any}. Anything else, carried through.
```

Serialised as **JSON Lines**, one record per line.

---

## The four constraints the contract enforces, and why

A schema that only listed field names would let every mistake this repository
spent v0.1 learning about back in. These four are validated, and a violating
record is rejected rather than coerced.

### 1. `world_id` is mandatory and distinct from `event_id`

Rows sharing a `world_id` are **not independent observations**. Every
statistic computed here collapses to the world first
(`docs/STATISTICAL_PROTOCOL.md`).

A producer emitting one row per resident with a constant `world_id` is doing
the right thing. A producer putting a unique `world_id` on every resident is
destroying the only information that makes the inference honest, and no
downstream analysis can recover it. In this repository's own scenario that
error would understate standard errors by about 5.5×.

### 2. Both forecast clocks, or neither

`forecast_issue_time` and `forecast_availability_time` must be supplied
together. One without the other cannot distinguish **latency**
(`availability − issue`) from **staleness** (`decision − issue`), and those are
different numbers with different consequences (F-12). A record whose
availability precedes its issue time is rejected: that product would arrive
before it was made.

### 3. Availability is not a property of the forecast alone

`was_available()` returns `None` — not `False` — when `decision_time` is
absent. Whether a product was usable depends on when the decision was made,
and a producer that omits the decision time has not supplied enough to answer
it. Guessing would silently convert "we don't know" into "it wasn't there".

### 4. A failed record must say why

`failure_reason` is required when `mission_success` is false, because a study
has to distinguish **protective-action failure** — the route was cut, the
action did not achieve its objective — from a loss that happened for unrelated
reasons. Without it, every bad outcome looks like a forecast problem.

---

## What is deliberately loose

**`skill_metrics` is free-form.** Different producers score differently, and
this repository must not dictate a scoring convention it would then be accused
of having chosen to suit itself. It is flattened to `skill_*` columns and is
**never read by any decision** — the same separation that
`skill_metrics` and `decision_value` have in this package (D-09).

**`loss` is one number in producer-declared units.** The exchange rate between
delay and harm is the producer's ethical choice, not this repository's (F-07).
`loss_units` must be stated so that incommensurable losses are not averaged.

**`action` is an opaque string.** No action vocabulary is imposed.

---

## What this repository will do with the records

Ingest → align skill with downstream outcomes → construct error × latency
grids → identify candidate break-even regions → export world-level records
to `wildfireguardian-evaluation`. See `docs/REPOSITORY_ROLE.md`.

It will **not** perform the formal inference on them. Point estimates,
pairing structure and grid construction are exported; confidence statements
are `wildfireguardian-evaluation`'s.

---

## Example

```json
{"world_id": "w-0041", "event_id": "ign-3", "source_type": "OSSE_HIDDEN_WORLD",
 "policy_id": "proximity_trigger", "forecast_id": null,
 "forecast_issue_time": null, "forecast_availability_time": null,
 "skill_metrics": {}, "action": "route_b", "loss": 1.25,
 "mission_success": true, "failure_reason": null,
 "decision_time": 1.0, "loss_units": "hours_equivalent_delay"}
{"world_id": "w-0041", "event_id": "ign-3", "source_type": "OSSE_HIDDEN_WORLD",
 "policy_id": "forecast_plug_in", "forecast_id": "fx-12z",
 "forecast_issue_time": 0.6, "forecast_availability_time": 1.1,
 "skill_metrics": {"csi": 0.61, "arrival_rmse": 0.42}, "action": "route_a",
 "loss": 51.0, "mission_success": false, "failure_reason": "route_failure",
 "decision_time": 1.0, "loss_units": "hours_equivalent_delay",
 "forecast_class": "DEGRADED_FORECAST"}
```

Same `world_id`, two `policy_id`s: that is what makes the comparison paired.
The second record's product became available at 1.1 h for a decision made at
1.0 h, so `was_available()` is `False` and its skill scores are irrelevant to
the action — which is the Case 4 phenomenon, arriving from outside.

---

## Reading it

```python
from wildfireguardian_forecast_value.interfaces import read_records, records_to_frame

records = list(read_records("osse_run_017.jsonl"))
frame = records_to_frame(records)     # attrs["unit_of_analysis"] == "world"
```

Validation is eager: a malformed record raises `RecordValidationError` naming
the file, line and problem, rather than producing a frame with a quiet `NaN` in
it.

---

## Stability

`schema_version` 1. Adding optional fields is backwards compatible; unknown
fields are preserved in `extra` rather than dropped. Removing a required field,
changing the meaning of `world_id`, or relaxing any of the four constraints
above is a breaking change and needs a version bump and a note here.
