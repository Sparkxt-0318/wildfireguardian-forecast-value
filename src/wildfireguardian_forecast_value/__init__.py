"""Wildfire forecast *decision value* laboratory.

This package exists to make one distinction explicit and computational:

    forecast skill  !=  forecast decision value

A forecast can improve traditional prediction metrics (RMSE, CSI, Brier)
without ever changing the action a protective decision maker should take.
A forecast can also carry substantial prediction error and still support the
same correct protective action.

Everything here runs on internal synthetic fixtures.  Nothing in this package
is calibrated against real wildfire behaviour, and no number produced by it
should be read as a real-world performance claim.  See ``docs/SCOPE.md``.
"""

from wildfireguardian_forecast_value._version import __version__

__all__ = ["__version__"]
