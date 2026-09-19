"""Combined, *correlated* forecast error.

Forecast error channels are not independent.  A model that is running the
fire too fast is usually also running it in the wrong direction (both follow
from a wind error); a model that has lost the plot badly enough to miss a spot
ignition is not simultaneously nailing the main front.  Sampling each channel
independently makes joint tail events -- exactly the events that flip
protective decisions -- vanishingly rare, and so understates how often a
forecast is decision-relevantly wrong.  This module makes the dependence an
explicit, inspectable object.

Construction
------------
A **Gaussian copula**:

1. draw ``z ~ N(0, R)`` where ``R`` is a correlation matrix over the named
   parameters;
2. map to uniforms ``u = Phi(z)``;
3. push each ``u_k`` through its own marginal's quantile function.

Why a copula rather than "just a multivariate normal": the channels do not
share a family.  ``eps_theta`` is roughly symmetric, ``spot_delay`` is
non-negative, and ``spot_miss_u`` must be *exactly* uniform on ``[0, 1]``
because :class:`~.spotting.SpotMiss` thresholds it.  A copula gives each
channel the marginal it needs while keeping one dependence structure.

Caveat the auditor must not skip
--------------------------------
``R`` is the correlation of the **latent** normals, not the Pearson
correlation of the sampled parameters.  The two coincide only where both
marginals are normal.  For a normal/half-normal pair, a latent ``rho = 0.8``
yields a smaller realised Pearson correlation.  If you need to report the
realised correlation, measure it from a sample --
:meth:`CorrelatedErrorModel.realised_correlation` does exactly that -- rather
than quoting ``R``.  ``docs/FORECAST_ERROR_MODEL.md`` records this, and
``docs/FAILURE_MODES.md`` lists it as F-02.

``rho = 0`` in a Gaussian copula means *independence*, which is a genuine
convenience of this construction; its matching limitation is that it cannot
express tail dependence.  Channels that fail together *only* in the tail are
not representable here (``docs/FAILURE_MODES.md``, F-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy import stats

from wildfireguardian_forecast_value.degradation.base import DegradationPipeline, SourceSelector
from wildfireguardian_forecast_value.degradation.direction import DirectionError
from wildfireguardian_forecast_value.degradation.displacement import SpatialDisplacement
from wildfireguardian_forecast_value.degradation.spotting import SpotDelay, SpotDisplacement, SpotMiss
from wildfireguardian_forecast_value.degradation.spread_rate import SpreadRateError
from wildfireguardian_forecast_value.rng import make_generator

__all__ = ["Marginal", "CorrelatedErrorModel", "standard_pipeline", "STANDARD_ORDER"]

#: Canonical operator order used by :func:`standard_pipeline`.
#:
#: Direction precedes displacement because ``SpatialDisplacement`` may be
#: expressed relative to the source heading and therefore reads it.  Every
#: other adjacent pair commutes (``tests/test_degradation_algebra.py``).
STANDARD_ORDER = (
    "direction_error",
    "spread_rate_error",
    "spatial_displacement",
    "spot_miss",
    "spot_delay",
    "spot_displacement",
)

_EPS = 1e-12


@dataclass(frozen=True)
class Marginal:
    """Marginal distribution for one error channel.

    Supported ``kind`` values and their parameters:

    ``"constant"``      ``value``
    ``"normal"``        ``mu``, ``sigma``
    ``"truncated_normal"`` ``mu``, ``sigma``, ``low``, ``high``
    ``"uniform"``       ``low``, ``high``
    ``"half_normal"``   ``sigma`` (non-negative; for delays)
    ``"exponential"``   ``scale`` (non-negative; for delays)
    ``"lognormal"``     ``mu``, ``sigma`` of the underlying normal
    """

    kind: str
    params: tuple[tuple[str, float], ...] = ()

    def __init__(self, kind: str, **params: float) -> None:
        object.__setattr__(self, "kind", str(kind))
        object.__setattr__(self, "params", tuple(sorted((k, float(v)) for k, v in params.items())))
        self._validate()

    @property
    def p(self) -> dict[str, float]:
        return dict(self.params)

    def _validate(self) -> None:
        p = self.p
        need = {
            "constant": {"value"},
            "normal": {"mu", "sigma"},
            "truncated_normal": {"mu", "sigma", "low", "high"},
            "uniform": {"low", "high"},
            "half_normal": {"sigma"},
            "exponential": {"scale"},
            "lognormal": {"mu", "sigma"},
        }
        if self.kind not in need:
            raise ValueError(f"unknown marginal kind {self.kind!r}; expected one of {sorted(need)}")
        missing = need[self.kind] - set(p)
        if missing:
            raise ValueError(f"marginal {self.kind!r} needs parameter(s) {sorted(missing)}")
        if self.kind in ("normal", "truncated_normal", "half_normal", "lognormal") and p.get("sigma", 1.0) < 0:
            raise ValueError("sigma must be >= 0")
        if self.kind == "uniform" and p["high"] < p["low"]:
            raise ValueError("uniform marginal needs high >= low")
        if self.kind == "truncated_normal" and p["high"] <= p["low"]:
            raise ValueError("truncated_normal needs high > low")
        if self.kind == "exponential" and p["scale"] < 0:
            raise ValueError("exponential scale must be >= 0")

    @property
    def is_degenerate(self) -> bool:
        p = self.p
        return self.kind == "constant" or (
            self.kind in ("normal", "half_normal", "lognormal") and p.get("sigma", 0.0) == 0.0
        ) or (self.kind == "uniform" and p["low"] == p["high"]) or (
            self.kind == "exponential" and p["scale"] == 0.0
        )

    def from_normal(self, z):
        """Transform standard-normal draws to this marginal.

        Normal and half-normal marginals are computed from ``z`` in closed
        form rather than through ``Phi`` then ``ppf``; the two agree to
        machine precision but the closed form keeps hand-checked fixtures
        exact (``truncated_normal`` cannot be done this way and goes through
        the quantile function).
        """
        z = np.asarray(z, dtype=float)
        p = self.p
        if self.kind == "constant":
            return np.full(z.shape, p["value"])
        if self.kind == "normal":
            return p["mu"] + p["sigma"] * z
        if self.kind == "half_normal":
            return p["sigma"] * np.abs(z)
        u = stats.norm.cdf(z)
        return self.from_uniform(u)

    def from_uniform(self, u):
        """Quantile transform of uniforms on ``[0, 1]``."""
        u = np.clip(np.asarray(u, dtype=float), _EPS, 1.0 - _EPS)
        p = self.p
        if self.kind == "constant":
            return np.full(u.shape, p["value"])
        if self.kind == "uniform":
            return p["low"] + (p["high"] - p["low"]) * u
        if self.kind == "normal":
            return stats.norm.ppf(u, loc=p["mu"], scale=p["sigma"]) if p["sigma"] > 0 else np.full(u.shape, p["mu"])
        if self.kind == "half_normal":
            return stats.halfnorm.ppf(u, scale=p["sigma"]) if p["sigma"] > 0 else np.zeros(u.shape)
        if self.kind == "exponential":
            return stats.expon.ppf(u, scale=p["scale"]) if p["scale"] > 0 else np.zeros(u.shape)
        if self.kind == "lognormal":
            return stats.lognorm.ppf(u, s=p["sigma"], scale=np.exp(p["mu"]))
        if self.kind == "truncated_normal":
            sigma = p["sigma"]
            if sigma <= 0:
                return np.full(u.shape, float(np.clip(p["mu"], p["low"], p["high"])))
            a = (p["low"] - p["mu"]) / sigma
            b = (p["high"] - p["mu"]) / sigma
            return stats.truncnorm.ppf(u, a, b, loc=p["mu"], scale=sigma)
        raise AssertionError(f"unhandled marginal kind {self.kind!r}")  # pragma: no cover

    def to_dict(self) -> dict:
        return {"kind": self.kind, **self.p}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Marginal":
        d = dict(d)
        kind = d.pop("kind")
        return cls(kind, **d)

    # Convenience constructors ------------------------------------------------
    @classmethod
    def constant(cls, value: float) -> "Marginal":
        return cls("constant", value=value)

    @classmethod
    def normal(cls, mu: float = 0.0, sigma: float = 1.0) -> "Marginal":
        return cls("normal", mu=mu, sigma=sigma)

    @classmethod
    def unit_uniform(cls) -> "Marginal":
        return cls("uniform", low=0.0, high=1.0)


class CorrelatedErrorModel:
    """Joint sampler for named error channels under a Gaussian copula."""

    def __init__(
        self,
        marginals: Mapping[str, Marginal],
        correlations: Mapping[tuple[str, str], float] | np.ndarray | None = None,
    ) -> None:
        if not marginals:
            raise ValueError("a CorrelatedErrorModel needs at least one channel")
        self.names: tuple[str, ...] = tuple(marginals.keys())
        self.marginals: dict[str, Marginal] = dict(marginals)
        self._R = self._build_correlation(correlations)

    # -- correlation matrix --------------------------------------------------
    def _build_correlation(self, correlations) -> np.ndarray:
        n = len(self.names)
        idx = {name: i for i, name in enumerate(self.names)}
        if correlations is None:
            return np.eye(n)
        if isinstance(correlations, np.ndarray):
            R = np.array(correlations, dtype=float)
            if R.shape != (n, n):
                raise ValueError(f"correlation matrix must be {n}x{n}, got {R.shape}")
        else:
            R = np.eye(n)
            for (a, b), rho in correlations.items():
                if a not in idx or b not in idx:
                    raise KeyError(f"correlation names {(a, b)} not among channels {self.names}")
                if not (-1.0 <= float(rho) <= 1.0):
                    raise ValueError(f"correlation for {(a, b)} must be in [-1, 1], got {rho!r}")
                R[idx[a], idx[b]] = R[idx[b], idx[a]] = float(rho)
        if not np.allclose(R, R.T, atol=1e-12):
            raise ValueError("correlation matrix must be symmetric")
        if not np.allclose(np.diag(R), 1.0, atol=1e-12):
            raise ValueError("correlation matrix must have unit diagonal")
        eig = np.linalg.eigvalsh(R)
        if eig.min() < -1e-8:
            raise ValueError(
                "correlation matrix is not positive semi-definite (min eigenvalue "
                f"{eig.min():.3e}). Pairwise correlations cannot be chosen independently; "
                "e.g. corr(a,b)=corr(b,c)=0.9 forces corr(a,c) >= 0.62."
            )
        return R

    @property
    def correlation_matrix(self) -> np.ndarray:
        return self._R.copy()

    # -- sampling ------------------------------------------------------------
    def sample_latent(self, n: int, seed) -> np.ndarray:
        """Latent standard-normal draws with correlation ``R``, shape ``(n, k)``."""
        rng = make_generator(seed)
        k = len(self.names)
        # Eigendecomposition rather than Cholesky: R may be singular by design
        # (a channel duplicated at rho = 1 is legitimate), and Cholesky is not.
        vals, vecs = np.linalg.eigh(self._R)
        vals = np.clip(vals, 0.0, None)
        L = vecs @ np.diag(np.sqrt(vals))
        z = rng.standard_normal((int(n), k))
        return z @ L.T

    def sample(self, n: int, seed) -> dict[str, np.ndarray]:
        """Draw ``n`` joint error vectors.  Returns one array per channel."""
        z = self.sample_latent(n, seed)
        return {name: np.asarray(self.marginals[name].from_normal(z[:, i]), dtype=float)
                for i, name in enumerate(self.names)}

    def sample_records(self, n: int, seed) -> list[dict[str, float]]:
        """Same draws, as a list of parameter dicts ready for a pipeline."""
        cols = self.sample(n, seed)
        return [{name: float(cols[name][i]) for name in self.names} for i in range(int(n))]

    def realised_correlation(self, n: int = 20_000, seed: int = 0) -> np.ndarray:
        """Monte-Carlo Pearson correlation of the *sampled* parameters.

        Use this, not :attr:`correlation_matrix`, when reporting the
        correlation between channels.  Degenerate channels (zero variance)
        yield ``nan`` rows rather than a divide-by-zero.
        """
        cols = self.sample(n, seed)
        M = np.stack([cols[name] for name in self.names], axis=1)
        sd = M.std(axis=0)
        out = np.full((len(self.names), len(self.names)), np.nan)
        good = sd > 0
        if good.sum() >= 1:
            sub = np.corrcoef(M[:, good], rowvar=False)
            sub = np.atleast_2d(sub)
            gi = np.where(good)[0]
            for a, ia in enumerate(gi):
                for b, ib in enumerate(gi):
                    out[ia, ib] = sub[a, b]
        return out

    def to_dict(self) -> dict:
        return {
            "channels": {k: v.to_dict() for k, v in self.marginals.items()},
            "correlation": self._R.tolist(),
            "channel_order": list(self.names),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "CorrelatedErrorModel":
        order = list(d.get("channel_order") or d["channels"].keys())
        marg = {k: Marginal.from_dict(d["channels"][k]) for k in order}
        R = np.array(d["correlation"], dtype=float) if "correlation" in d else None
        return cls(marg, R)

    @classmethod
    def independent(cls, marginals: Mapping[str, Marginal]) -> "CorrelatedErrorModel":
        """Explicitly independent channels.

        Named rather than defaulted so that "we assumed independence" always
        appears in the manifest instead of being the shape of the silence.
        """
        return cls(marginals, None)


def standard_pipeline(
    include_spotting: bool = True,
    p_miss: float = 0.0,
    displacement_relative_to_heading: bool = True,
    rate_clip: tuple[float, float] | None = None,
) -> DegradationPipeline:
    """The canonical operator chain, in :data:`STANDARD_ORDER`."""
    ops = [
        DirectionError(selector=SourceSelector.primary()),
        SpreadRateError(clip_to=rate_clip),
        SpatialDisplacement(
            selector=SourceSelector.primary(),
            mode="polar",
            relative_to_heading=displacement_relative_to_heading,
        ),
    ]
    if include_spotting:
        ops += [SpotMiss(p_miss=p_miss), SpotDelay(), SpotDisplacement(mode="polar")]
    pipe = DegradationPipeline(ops)
    order = [op.name for op in pipe]
    assert order == [n for n in STANDARD_ORDER if n in order], f"pipeline order drifted: {order}"
    return pipe
