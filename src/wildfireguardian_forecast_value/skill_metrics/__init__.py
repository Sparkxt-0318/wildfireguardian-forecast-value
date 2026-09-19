"""Traditional forecast-skill metrics.

Deliberately isolated from :mod:`~wildfireguardian_forecast_value.decision_value`:
nothing in this subpackage is allowed to influence an action, and nothing in
the decision-value subpackage imports from here.  The point of the repository
is that the two can move independently.
"""

from wildfireguardian_forecast_value.skill_metrics.categorical import (
    ContingencyTable,
    brier_score,
    brier_skill_score,
    categorical_scores,
    contingency_table,
    ensemble_burn_probability,
)
from wildfireguardian_forecast_value.skill_metrics.continuous import (
    ArrivalTimeMetrics,
    angular_error,
    arrival_time_metrics,
    circular_mae,
    rate_metrics,
)

__all__ = [
    "ContingencyTable", "contingency_table", "categorical_scores",
    "brier_score", "brier_skill_score", "ensemble_burn_probability",
    "ArrivalTimeMetrics", "arrival_time_metrics", "angular_error",
    "circular_mae", "rate_metrics",
]
