"""The external experiment record.

One row = **one policy outcome in one world/event**, produced by an external
experiment and consumed here for skill-versus-value alignment.

Two things this schema is designed to make impossible:

1. **Losing the unit of analysis.**  ``world_id`` is mandatory and separate
   from ``event_id``.  Records that share a ``world_id`` are *not* independent
   observations, and every statistic this repository computes collapses to the
   world before doing anything else.  A producer that emits one row per
   resident and leaves ``world_id`` constant is doing the right thing; a
   producer that puts a unique ``world_id`` on every resident is destroying the
   only information that makes the inference honest.

2. **Losing the two clocks.**  ``forecast_issue_time`` and
   ``forecast_availability_time`` are both mandatory and are allowed to be
   ``None`` only together (a policy that used no forecast).  A record with an
   availability time but no issue time cannot distinguish latency from
   staleness, which is the distinction the whole latency treatment rests on
   (``docs/FAILURE_MODES.md``, F-12).

Everything else is deliberately loose.  ``skill_metrics`` is a free-form
mapping because different producers score differently and this repository must
not dictate a scoring convention it will then be accused of having chosen to
suit itself.  ``loss`` is a single number in producer-declared units, with the
units named in ``loss_units``, because the exchange rate is the producer's
ethical choice and not this repository's.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

__all__ = [
    "ExperimentRecord",
    "RecordValidationError",
    "REQUIRED_FIELDS",
    "SOURCE_TYPES",
    "read_records",
    "records_to_frame",
    "validate_records",
]

#: Accepted producers.  Extending this list is a deliberate act: a new source
#: type means a new provenance story, and `source_type` is what stops records
#: of different evidentiary weight from being pooled silently.
SOURCE_TYPES = (
    "MAIN_EMPIRICAL_STRESS_TEST",   # Source A: main WildfireGuardian repository
    "OSSE_HIDDEN_WORLD",            # Source B: wildfireguardian-osse
    "CONSTRUCTED_BENCHMARK",        # this repository's own frozen fixtures
)

REQUIRED_FIELDS = (
    "world_id", "event_id", "source_type", "policy_id",
    "forecast_id", "forecast_issue_time", "forecast_availability_time",
    "skill_metrics", "action", "loss", "mission_success", "failure_reason",
)


class RecordValidationError(ValueError):
    """A record does not satisfy the input contract."""


@dataclass(frozen=True)
class ExperimentRecord:
    """One policy outcome in one world/event."""

    #: The unit of analysis.  Rows sharing a world are dependent.
    world_id: str
    #: An occurrence within a world (an ignition, an incident, a receptor group).
    event_id: str
    #: One of :data:`SOURCE_TYPES`.  Records of different source types are
    #: never pooled without an explicit decision.
    source_type: str
    #: Which decision policy produced ``action``.  Baseline and forecast-aware
    #: arms of the same world carry the same ``world_id`` and different
    #: ``policy_id``; that is what makes the comparison paired.
    policy_id: str
    #: Identifies the forecast product, or ``None`` for a forecast-free policy.
    forecast_id: str | None
    #: Information time ``s``: what the forecast could know.  Hours on the
    #: producer's clock, or ``None`` for a forecast-free policy.
    forecast_issue_time: float | None
    #: ``s + delta``: when the product could first be acted on.  ``None`` only
    #: together with ``forecast_issue_time``.
    forecast_availability_time: float | None
    #: Producer-defined scores.  Never read by any decision in this repository.
    skill_metrics: Mapping[str, float]
    #: The action taken.
    action: str
    #: Realised downstream loss, smaller is better, in ``loss_units``.
    loss: float
    #: Whether the protective action achieved its objective.
    mission_success: bool
    #: Why not, when ``mission_success`` is false; ``None`` when it is true.
    failure_reason: str | None

    # -- optional, but strongly encouraged -------------------------------
    #: When the decision was made.  Without it, latency cannot be turned into
    #: availability and this repository can only take the producer's word for
    #: whether a forecast was usable.
    decision_time: float | None = None
    #: Units of ``loss``; free text, but it must be stated.
    loss_units: str = "unspecified"
    #: One of the four classes in
    #: :mod:`wildfireguardian_forecast_value.forecast_classes`, when known.
    forecast_class: str | None = None
    #: Anything else the producer wants to carry through.
    extra: Mapping[str, Any] = field(default_factory=dict)

    # -- validation ------------------------------------------------------
    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in ("world_id", "event_id", "policy_id"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v:
                raise RecordValidationError(f"{name} must be a non-empty string, got {v!r}")
        if self.source_type not in SOURCE_TYPES:
            raise RecordValidationError(
                f"source_type must be one of {SOURCE_TYPES}, got {self.source_type!r}. "
                "Records of different provenance are not pooled implicitly."
            )
        issue, avail = self.forecast_issue_time, self.forecast_availability_time
        if (issue is None) != (avail is None):
            raise RecordValidationError(
                "forecast_issue_time and forecast_availability_time must be supplied "
                "together or omitted together. One without the other cannot "
                "distinguish latency from staleness."
            )
        if issue is not None:
            if avail < issue:
                raise RecordValidationError(
                    f"forecast_availability_time ({avail}) precedes forecast_issue_time "
                    f"({issue}): the product would arrive before it was made."
                )
            if self.forecast_id is None:
                raise RecordValidationError(
                    "a record with forecast timestamps must name a forecast_id"
                )
        elif self.forecast_id is not None:
            raise RecordValidationError(
                "a record naming a forecast_id must carry its issue and availability times"
            )
        if not isinstance(self.skill_metrics, Mapping):
            raise RecordValidationError("skill_metrics must be a mapping")
        for k, v in self.skill_metrics.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise RecordValidationError(f"skill_metrics[{k!r}] must be numeric, got {v!r}")
        if not isinstance(self.action, str) or not self.action:
            raise RecordValidationError("action must be a non-empty string")
        if not isinstance(self.loss, (int, float)) or isinstance(self.loss, bool):
            raise RecordValidationError(f"loss must be numeric, got {self.loss!r}")
        if not isinstance(self.mission_success, bool):
            raise RecordValidationError("mission_success must be a bool")
        if self.mission_success and self.failure_reason:
            raise RecordValidationError(
                f"mission_success is true but failure_reason is {self.failure_reason!r}"
            )
        if not self.mission_success and not self.failure_reason:
            raise RecordValidationError(
                "a failed record must say why; failure_reason is how a study "
                "distinguishes protective-action failure from an unrelated loss"
            )
        if self.forecast_class is not None:
            from wildfireguardian_forecast_value.forecast_classes import ForecastClass

            if self.forecast_class not in {c.value for c in ForecastClass}:
                raise RecordValidationError(
                    f"forecast_class must be one of "
                    f"{[c.value for c in ForecastClass]}, got {self.forecast_class!r}"
                )

    # -- availability ----------------------------------------------------
    @property
    def latency(self) -> float | None:
        """``availability - issue``, or ``None`` for a forecast-free record."""
        if self.forecast_issue_time is None:
            return None
        return float(self.forecast_availability_time) - float(self.forecast_issue_time)

    def information_age_at_decision(self) -> float | None:
        """``decision_time - issue`` -- staleness, which is not latency."""
        if self.forecast_issue_time is None or self.decision_time is None:
            return None
        return float(self.decision_time) - float(self.forecast_issue_time)

    def was_available(self) -> bool | None:
        """Whether the product could have been acted on, or ``None`` if unknowable.

        ``None`` when the producer omitted ``decision_time``: availability is
        not a property of the forecast alone.
        """
        if self.forecast_availability_time is None:
            return False
        if self.decision_time is None:
            return None
        return float(self.forecast_availability_time) <= float(self.decision_time)

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["skill_metrics"] = dict(self.skill_metrics)
        d["extra"] = dict(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: Mapping) -> "ExperimentRecord":
        known = {f for f in cls.__dataclass_fields__}
        missing = [f for f in REQUIRED_FIELDS if f not in d]
        if missing:
            raise RecordValidationError(f"record is missing required field(s): {missing}")
        payload = {k: v for k, v in d.items() if k in known}
        unknown = {k: v for k, v in d.items() if k not in known}
        if unknown:
            extra = dict(payload.get("extra") or {})
            extra.update(unknown)
            payload["extra"] = extra
        return cls(**payload)


def validate_records(records: Iterable[Mapping | ExperimentRecord]) -> list[ExperimentRecord]:
    """Validate a batch, reporting the row index of the first failure."""
    out: list[ExperimentRecord] = []
    for i, r in enumerate(records):
        try:
            out.append(r if isinstance(r, ExperimentRecord) else ExperimentRecord.from_dict(r))
        except RecordValidationError as exc:
            raise RecordValidationError(f"record {i}: {exc}") from exc
    return out


def read_records(path: str | Path) -> Iterator[ExperimentRecord]:
    """Read JSON Lines (one record per line).  Blank lines are skipped."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                yield ExperimentRecord.from_dict(json.loads(line))
            except (RecordValidationError, json.JSONDecodeError) as exc:
                raise RecordValidationError(f"{p}:{i + 1}: {exc}") from exc


def records_to_frame(records: Iterable[ExperimentRecord]):
    """Tidy frame, one row per record, with the unit of analysis tagged.

    Skill metrics are flattened to ``skill_*`` columns.  The frame carries
    ``attrs["unit_of_analysis"] = "world"`` for the same reason
    :func:`...decision_value.value.results_to_frame` does: nothing downstream
    should have to guess.
    """
    import pandas as pd

    rows = []
    for r in records:
        d = r.to_dict()
        skill = d.pop("skill_metrics")
        d.pop("extra")
        d.update({f"skill_{k}": v for k, v in skill.items()})
        d["latency"] = r.latency
        d["was_available"] = r.was_available()
        rows.append(d)
    df = pd.DataFrame(rows)
    df.attrs["unit_of_analysis"] = "world"
    df.attrs["contract"] = "docs/EXTERNAL_EXPERIMENT_INTERFACE.md"
    return df
