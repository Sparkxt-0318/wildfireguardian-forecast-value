"""Degradation operator interface.

A **degradation operator** is a deterministic map

    T_p : FireState -> FireState

indexed by a vector ``p`` of named real-valued *perturbation parameters*.
The split between "operator" (deterministic) and "error model" (stochastic,
:mod:`~.combined`) is deliberate:

* every operator can be hand-checked at a fixed ``p``;
* correlation between error channels lives in exactly one place, so it is
  impossible to accidentally sample two channels independently just because
  they are applied by two different operators;
* a frontier sweep varies ``p`` on a grid without touching any RNG.

Each operator declares ``param_names``.  The union of those names over a
pipeline is the pipeline's parameter vector, and that is what
:class:`~.combined.CorrelatedErrorModel` draws.

Targeting
---------
Operators act on a *subset* of sources chosen by :class:`SourceSelector`
(by ``kind``, by explicit labels, or all).  Defaults are set so that
"degrade the fire's heading" cannot silently delete a spot fire and
"the spot fire was missed" cannot silently delete the main fire.

Commutativity
-------------
The canonical operators in this package write to **disjoint fields** of
:class:`~wildfireguardian_forecast_value.fields.front.FireSource`
(rate / heading / origin / ignition time / existence), so they commute --
except :class:`~.displacement.SpatialDisplacement` with
``relative_to_heading=True``, which reads ``heading`` and therefore does not
commute with :class:`~.direction.DirectionError`.
:class:`DegradationPipeline` fixes a deterministic order regardless, and
``tests/test_degradation_algebra.py`` asserts both facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from wildfireguardian_forecast_value.fields.front import FireSource, FireState

__all__ = [
    "SourceSelector",
    "DegradationOperator",
    "DegradationPipeline",
    "identity_params",
]


@dataclass(frozen=True)
class SourceSelector:
    """Chooses which sources an operator touches."""

    kinds: tuple[str, ...] | None = None
    labels: tuple[str, ...] | None = None

    def matches(self, source: FireSource) -> bool:
        if self.labels is not None and source.label not in self.labels:
            return False
        if self.kinds is not None and source.kind not in self.kinds:
            return False
        return True

    def select(self, state: FireState) -> tuple[FireSource, ...]:
        return tuple(s for s in state.sources if self.matches(s))

    def to_dict(self) -> dict:
        return {
            "kinds": list(self.kinds) if self.kinds is not None else None,
            "labels": list(self.labels) if self.labels is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping | None) -> "SourceSelector":
        if d is None:
            return cls()
        return cls(
            kinds=tuple(d["kinds"]) if d.get("kinds") else None,
            labels=tuple(d["labels"]) if d.get("labels") else None,
        )

    @classmethod
    def primary(cls) -> "SourceSelector":
        return cls(kinds=("primary",))

    @classmethod
    def spots(cls) -> "SourceSelector":
        return cls(kinds=("spot",))


class DegradationOperator:
    """Base class.  Subclasses implement :meth:`_apply_to_source` or :meth:`apply`."""

    #: Stable operator name, used in manifests and result frames.
    name: str = "identity"
    #: Names of the scalar perturbation parameters this operator consumes.
    param_names: tuple[str, ...] = ()

    def __init__(self, selector: SourceSelector | None = None) -> None:
        self.selector = selector if selector is not None else SourceSelector()

    # -- parameter handling ------------------------------------------------
    def identity_params(self) -> dict[str, float]:
        """Parameter values for which the operator is the identity map.

        Every operator must have such a point; it is what "no degradation"
        means, and ``tests/test_degradation_algebra.py`` checks it for each
        registered operator.
        """
        raise NotImplementedError

    def _read(self, params: Mapping[str, float]) -> dict[str, float]:
        missing = [k for k in self.param_names if k not in params]
        if missing:
            raise KeyError(
                f"operator {self.name!r} requires parameter(s) {missing}; got {sorted(params)}"
            )
        return {k: float(params[k]) for k in self.param_names}

    # -- application -------------------------------------------------------
    def apply(self, state: FireState, params: Mapping[str, float]) -> FireState:
        """Apply the operator to the selected sources of ``state``."""
        values = self._read(params)
        out: list[FireSource] = []
        for src in state.sources:
            if self.selector.matches(src):
                new = self._apply_to_source(src, values)
                if new is not None:
                    out.append(new)
            else:
                out.append(src)
        return FireState(tuple(out))

    def _apply_to_source(self, source: FireSource, values: Mapping[str, float]) -> FireSource | None:
        """Return the degraded source, or ``None`` to delete it."""
        raise NotImplementedError

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        return {"operator": self.name, "selector": self.selector.to_dict(), **self._config()}

    def _config(self) -> dict:
        return {}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        cfg = self._config()
        inner = ", ".join(f"{k}={v!r}" for k, v in cfg.items())
        return f"{type(self).__name__}({inner})"


@dataclass
class DegradationPipeline:
    """An ordered sequence of operators applied as one map."""

    operators: tuple[DegradationOperator, ...] = ()

    def __init__(self, operators: Iterable[DegradationOperator] = ()) -> None:
        self.operators = tuple(operators)

    @property
    def param_names(self) -> tuple[str, ...]:
        seen: list[str] = []
        for op in self.operators:
            for p in op.param_names:
                if p not in seen:
                    seen.append(p)
        return tuple(seen)

    def identity_params(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for op in self.operators:
            out.update(op.identity_params())
        return out

    def apply(self, state: FireState, params: Mapping[str, float] | None = None) -> FireState:
        p = dict(self.identity_params())
        if params:
            p.update({k: float(v) for k, v in params.items()})
        unknown = set(p) - set(self.param_names)
        if unknown:
            raise KeyError(
                f"parameters {sorted(unknown)} are not consumed by this pipeline "
                f"(consumed: {list(self.param_names)}). Refusing to silently ignore them."
            )
        for op in self.operators:
            state = op.apply(state, p)
        return state

    def __len__(self) -> int:
        return len(self.operators)

    def __iter__(self):
        return iter(self.operators)

    def to_dict(self) -> dict:
        return {"operators": [op.to_dict() for op in self.operators]}


def identity_params(pipeline: DegradationPipeline | Sequence[DegradationOperator]) -> dict[str, float]:
    """Identity parameter vector for a pipeline or a bare sequence of operators."""
    if isinstance(pipeline, DegradationPipeline):
        return pipeline.identity_params()
    out: dict[str, float] = {}
    for op in pipeline:
        out.update(op.identity_params())
    return out
