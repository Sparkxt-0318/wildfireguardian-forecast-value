"""Forecast degradation operators, latency semantics, and correlated error."""

from wildfireguardian_forecast_value.degradation.base import (
    DegradationOperator,
    DegradationPipeline,
    SourceSelector,
    identity_params,
)
from wildfireguardian_forecast_value.degradation.combined import (
    STANDARD_ORDER,
    CorrelatedErrorModel,
    Marginal,
    standard_pipeline,
)
from wildfireguardian_forecast_value.degradation.direction import DirectionError, WidenFront
from wildfireguardian_forecast_value.degradation.displacement import SpatialDisplacement
from wildfireguardian_forecast_value.degradation.latency import (
    ForecastRelease,
    ForecastStream,
    LatencySpec,
    issue_times,
    make_release,
)
from wildfireguardian_forecast_value.degradation.spotting import (
    SpotDelay,
    SpotDisplacement,
    SpotMiss,
)
from wildfireguardian_forecast_value.degradation.spread_rate import SpreadRateError, log_ratio_error

__all__ = [
    "DegradationOperator", "DegradationPipeline", "SourceSelector", "identity_params",
    "CorrelatedErrorModel", "Marginal", "standard_pipeline", "STANDARD_ORDER",
    "DirectionError", "WidenFront", "SpatialDisplacement",
    "ForecastRelease", "ForecastStream", "LatencySpec", "make_release", "issue_times",
    "SpotMiss", "SpotDelay", "SpotDisplacement",
    "SpreadRateError", "log_ratio_error",
]
