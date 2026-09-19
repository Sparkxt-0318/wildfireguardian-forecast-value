"""The independent-validation layer: every closed-form example must hold.

These are the checks a reader can redo on paper.  When one fails, the
derivation printed by ``wg-forecast-value validate -v`` says exactly what the
answer should have been and why.
"""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.validation.hand_examples import hand_examples


@pytest.mark.parametrize("example", hand_examples(), ids=lambda e: e.key)
def test_hand_example(example):
    ok, got, expected = example.run()
    assert ok, (
        f"\n{example.title}\n{example.derivation}\n"
        f"expected: {np.asarray(expected, dtype=float)}\n"
        f"got:      {np.asarray(got, dtype=float)}"
    )


def test_every_example_has_a_derivation():
    """A hand-checkable example without a worked derivation is not hand-checkable."""
    for e in hand_examples():
        assert len(e.derivation.strip().splitlines()) >= 3, e.key
        assert "=" in e.derivation, e.key


def test_example_keys_are_unique():
    keys = [e.key for e in hand_examples()]
    assert len(set(keys)) == len(keys)
