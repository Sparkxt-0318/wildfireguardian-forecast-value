"""Experiment configuration.

A study in this package is defined by a YAML file, and the *resolved* version
of that file -- every default filled in -- is written alongside the results as
a manifest.  The reason is narrow and practical: almost every number this
package produces is conditional on a loss function, a world distribution, a
policy class and a grid, and a result quoted without them is not
interpretable.  Writing the resolved config makes it impossible to have a
result whose provenance is a shell history.

Unknown keys are an **error**, not a warning.  A typo in ``burnover_loss``
that silently leaves the default in place is exactly the kind of failure that
produces a plausible, wrong number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from wildfireguardian_forecast_value._version import __version__
from wildfireguardian_forecast_value.decision_value.loss import RouteChoiceLoss
from wildfireguardian_forecast_value.degradation.combined import (
    CorrelatedErrorModel,
    Marginal,
    standard_pipeline,
)
from wildfireguardian_forecast_value.degradation.latency import LatencySpec
from wildfireguardian_forecast_value.frontiers.grid import SweepAxis
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import default_scenario

__all__ = ["StudyConfig", "load_config", "DEFAULTS", "write_manifest"]

DEFAULTS: dict = {
    "name": "study",
    "seed": 11,
    "scenario": {},
    "loss": {"time_cost_per_hour": 1.0, "burnover_loss": 50.0},
    "degradation": {"include_spotting": True, "p_miss": 0.35,
                    "displacement_relative_to_heading": True, "rate_clip": None,
                    "params": {}},
    "error_model": None,
    "latency": {"information_time": 0.6, "latency": 0.0},
    "policy": {"max_wait": 1.6},
    "study": {"n_worlds": 200},
    "sweep": {
        "x": {"name": "eps_theta", "kind": "degradation", "start": -0.5235987755982988,
              "stop": 0.5235987755982988, "num": 17,
              "label": "direction error (deg)", "display_scale": 57.29577951308232},
        "y": {"name": "latency", "kind": "latency", "start": 0.0, "stop": 1.8, "num": 19,
              "label": "forecast latency (h)", "display_scale": 1.0},
    },
    "statistics": {"n_boot": 2000, "confidence": 0.95, "equivalence_margin": 2.0,
                   "frontier_boot": 400},
    "output": {"dir": "experiments/runs/study"},
}

_TOP_KEYS = set(DEFAULTS)


def _merge(base: dict, over: dict, path: str = "") -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        where = f"{path}.{k}" if path else k
        if k not in base and path in ("", "scenario", "loss", "degradation", "policy",
                                      "study", "statistics", "output", "latency"):
            if path == "scenario":
                out[k] = v            # scenario keys are validated by the dataclass
                continue
            raise KeyError(f"unknown configuration key {where!r}; known keys: {sorted(base)}")
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _merge(base[k], v, where)
        else:
            out[k] = v
    return out


@dataclass
class StudyConfig:
    """Resolved configuration."""

    raw: dict = field(default_factory=lambda: dict(DEFAULTS))

    # -- accessors ----------------------------------------------------------
    @property
    def name(self) -> str:
        return str(self.raw["name"])

    @property
    def seed(self) -> int:
        return int(self.raw["seed"])

    @property
    def output_dir(self) -> Path:
        return Path(self.raw["output"]["dir"])

    def loss(self) -> RouteChoiceLoss:
        return RouteChoiceLoss(**self.raw["loss"])

    def scenario(self):
        kw = dict(self.raw["scenario"])
        return default_scenario(loss=self.loss(), **kw)

    def pipeline(self):
        d = dict(self.raw["degradation"])
        d.pop("params", None)
        clip = d.pop("rate_clip", None)
        return standard_pipeline(rate_clip=tuple(clip) if clip else None, **d)

    def degradation_params(self) -> dict:
        return dict(self.raw["degradation"].get("params") or {})

    def latency(self) -> LatencySpec:
        return LatencySpec(**self.raw["latency"])

    def max_wait(self) -> float:
        return float(self.raw["policy"]["max_wait"])

    def n_worlds(self) -> int:
        return int(self.raw["study"]["n_worlds"])

    def error_model(self) -> CorrelatedErrorModel | None:
        em = self.raw.get("error_model")
        if not em:
            return None
        channels = {k: Marginal.from_dict(v) for k, v in em["channels"].items()}
        corr = {}
        for entry in em.get("correlation", []) or []:
            a, b, rho = entry
            corr[(a, b)] = float(rho)
        return CorrelatedErrorModel(channels, corr or None)

    def axis(self, which: str) -> SweepAxis:
        d = dict(self.raw["sweep"][which])
        values = tuple(np.linspace(float(d["start"]), float(d["stop"]), int(d["num"])))
        return SweepAxis(name=d["name"], values=values, kind=d.get("kind", "degradation"),
                         label=d.get("label"), display_scale=float(d.get("display_scale", 1.0)))

    def stats(self) -> dict:
        return dict(self.raw["statistics"])

    def to_dict(self) -> dict:
        return {"package_version": __version__, "config": self.raw}


def load_config(path: str | Path | None) -> StudyConfig:
    """Load and resolve a YAML config; ``None`` gives the packaged defaults."""
    if path is None:
        return StudyConfig(json.loads(json.dumps(DEFAULTS)))
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"no such config file: {p}")
    with p.open("r", encoding="utf-8") as fh:
        user = yaml.safe_load(fh) or {}
    if not isinstance(user, dict):
        raise ValueError(f"{p} must contain a YAML mapping at the top level")
    unknown = set(user) - _TOP_KEYS
    if unknown:
        raise KeyError(f"unknown top-level key(s) {sorted(unknown)} in {p}; "
                       f"known keys: {sorted(_TOP_KEYS)}")
    return StudyConfig(_merge(json.loads(json.dumps(DEFAULTS)), user))


def write_manifest(cfg: StudyConfig, out_dir: Path, extra: dict | None = None) -> Path:
    """Write the resolved config plus run metadata next to the results."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = cfg.to_dict()
    payload["resolved_scenario"] = cfg.scenario().to_dict()
    payload["resolved_pipeline"] = cfg.pipeline().to_dict()
    em = cfg.error_model()
    payload["resolved_error_model"] = em.to_dict() if em else None
    if extra:
        payload.update(extra)
    path = out_dir / "manifest.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False, default=str)
    return path
