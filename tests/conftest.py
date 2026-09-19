"""Shared fixtures.

Tests are organised around the three-role workflow described in ``AGENTS.md``:
``test_hand_checkable.py`` and ``test_cases.py`` are the independent
validator's, and they assert *claims* (what the repository says in its docs)
rather than implementation details.
"""

from __future__ import annotations

import numpy as np
import pytest

from wildfireguardian_forecast_value.degradation.combined import standard_pipeline
from wildfireguardian_forecast_value.decision_value.value import default_policies
from wildfireguardian_forecast_value.fields.front import FireSource, FireState
from wildfireguardian_forecast_value.synthetic_decisions.scenarios import default_scenario


@pytest.fixture
def wedge() -> FireSource:
    """Rate 2 km/h, due east, 45-degree half-angle, from the origin at t=0."""
    return FireSource(origin=(0.0, 0.0), ignition_time=0.0, spread_rate=2.0,
                      heading=0.0, half_angle=np.pi / 4)


@pytest.fixture
def spot() -> FireSource:
    return FireSource(origin=(6.0, 0.0), ignition_time=1.0, spread_rate=1.0, heading=0.0,
                      half_angle=np.pi, label="spot1", kind="spot")


@pytest.fixture
def two_source_state(wedge, spot) -> FireState:
    return FireState((wedge, spot))


@pytest.fixture
def scenario():
    return default_scenario()


@pytest.fixture
def pipeline():
    return standard_pipeline(p_miss=0.35)


@pytest.fixture
def policies(scenario):
    return default_policies(scenario, max_wait=0.0)
