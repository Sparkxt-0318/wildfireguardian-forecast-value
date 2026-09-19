"""Independent validation: hand-solvable examples and structural invariants."""

from wildfireguardian_forecast_value.validation.hand_examples import (
    HandExample,
    hand_examples,
    run_hand_examples,
)
from wildfireguardian_forecast_value.validation.invariants import (
    InvariantError,
    InvariantReport,
    check_baseline_is_forecast_free,
    check_identity_degradation,
    check_latency_semantics,
    check_no_clairvoyance,
    check_no_oracle_access,
    check_pairing,
    run_all_invariants,
)

__all__ = [
    "HandExample", "hand_examples", "run_hand_examples",
    "InvariantError", "InvariantReport", "run_all_invariants",
    "check_no_clairvoyance", "check_no_oracle_access", "check_baseline_is_forecast_free",
    "check_pairing", "check_identity_degradation", "check_latency_semantics",
]
