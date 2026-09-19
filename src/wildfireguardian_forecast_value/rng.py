"""Seed discipline.

Every stochastic object in this package takes an explicit integer seed and
derives its generator through :func:`spawn`.  Two rules:

1.  No module ever touches the global ``numpy.random`` state.
2.  Derived streams are obtained by *spawning* a :class:`numpy.random.SeedSequence`,
    never by adding an offset to an integer seed.  Offsetting seeds makes
    nominally independent streams collide in ways that silently correlate
    "independent" worlds -- which is precisely the error this package warns
    about in its statistics module.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

__all__ = ["make_generator", "spawn", "spawn_many"]


def make_generator(seed: int | np.random.SeedSequence | np.random.Generator) -> np.random.Generator:
    """Return a ``Generator`` from a seed, seed sequence, or existing generator."""
    if isinstance(seed, np.random.Generator):
        return seed
    if isinstance(seed, np.random.SeedSequence):
        return np.random.default_rng(seed)
    if isinstance(seed, (int, np.integer)):
        if seed < 0:
            raise ValueError(f"seed must be non-negative, got {seed}")
        return np.random.default_rng(np.random.SeedSequence(int(seed)))
    raise TypeError(f"cannot build a generator from {type(seed)!r}")


def spawn(seed: int | np.random.SeedSequence, key: str) -> np.random.Generator:
    """Derive a named independent stream from ``seed``.

    ``key`` is hashed into the spawn key so that the stream for, say,
    ``"world-draw"`` is stable regardless of how many other streams the caller
    happens to create first.
    """
    base = seed if isinstance(seed, np.random.SeedSequence) else np.random.SeedSequence(int(seed))
    # Stable, platform-independent digest of the key.
    digest = 0
    for ch in key:
        digest = (digest * 1_000_003 + ord(ch)) % (2**63)
    child = np.random.SeedSequence(entropy=base.entropy, spawn_key=tuple(base.spawn_key) + (digest,))
    return np.random.default_rng(child)


def spawn_many(seed: int | np.random.SeedSequence, keys: Sequence[str]) -> dict[str, np.random.Generator]:
    """Derive several named independent streams at once."""
    return {k: spawn(seed, k) for k in keys}
