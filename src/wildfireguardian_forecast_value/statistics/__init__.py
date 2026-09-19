"""World-level statistics for paired decision-value comparisons.

One rule governs this subpackage: **the world is the unit of analysis.**
Residents, receptors, grid cells and route samples are all *within* a world
and none of them is an independent observation.  See
``docs/STATISTICAL_PROTOCOL.md``.
"""

from wildfireguardian_forecast_value.statistics.bootstrap import (
    BootstrapResult,
    bootstrap_ci,
    cluster_bootstrap,
    paired_bootstrap_difference,
)
from wildfireguardian_forecast_value.statistics.effect_size import (
    EffectSizes,
    cohens_dz,
    effect_sizes,
    hedges_correction,
    probability_of_superiority,
    value_fraction_summary,
)
from wildfireguardian_forecast_value.statistics.equivalence import (
    EquivalenceResult,
    non_inferiority,
    tost,
)
from wildfireguardian_forecast_value.statistics.paired import (
    ClusteringDiagnostics,
    PairedSummary,
    aggregate_to_worlds,
    clustering_diagnostics,
    paired_summary,
)

__all__ = [
    "PairedSummary", "paired_summary", "aggregate_to_worlds",
    "ClusteringDiagnostics", "clustering_diagnostics",
    "BootstrapResult", "cluster_bootstrap", "bootstrap_ci", "paired_bootstrap_difference",
    "EffectSizes", "effect_sizes", "cohens_dz", "hedges_correction",
    "probability_of_superiority", "value_fraction_summary",
    "EquivalenceResult", "tost", "non_inferiority",
]
