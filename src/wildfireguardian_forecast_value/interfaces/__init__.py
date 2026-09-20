"""Input contracts for experiment records produced elsewhere.

Defining the contract is **not** integrating the producers.  Nothing in this
subpackage imports, invokes, or assumes the availability of any other
WildfireGuardian repository, and the freeze task that created it explicitly
forbids integration.  What it does is fix the shape of the records this
repository will one day ingest, executably, so the contract cannot drift while
nobody is looking.

See ``docs/EXTERNAL_EXPERIMENT_INTERFACE.md``.
"""

from wildfireguardian_forecast_value.interfaces.experiment_record import (
    REQUIRED_FIELDS,
    SOURCE_TYPES,
    ExperimentRecord,
    RecordValidationError,
    read_records,
    records_to_frame,
    validate_records,
)

__all__ = [
    "ExperimentRecord", "RecordValidationError", "REQUIRED_FIELDS", "SOURCE_TYPES",
    "read_records", "records_to_frame", "validate_records",
]
