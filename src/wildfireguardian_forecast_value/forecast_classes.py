"""The four information classes a "forecast" in this repository can belong to.

The phrase *perfect forecast* is ambiguous and this repository no longer uses
it.  It can mean at least two different things that have different decision
values, and conflating them is the easiest way to overstate what a forecast
could ever be worth:

* an estimate with **no error about the present**, which still cannot know
  about an ignition that has not happened yet; and
* an oracle that **knows the realised future**, including future spotting.

Only the second is an upper bound on decision value, and no real forecast
system can approach it.  The four classes below are exhaustive for this
package and every forecast object carries one.

.. list-table::
   :header-rows: 1

   * - class
     - information set
     - realisable?
   * - ``PRESENT_STATE_ORACLE``
     - exact fire state at information time ``s``; nothing after ``s``
     - no (an error-free observation), but it is a *meaningful* bound on
       observation quality
   * - ``CONDITIONAL_FORECAST``
     - a function of information available at ``s``, with no degradation
       applied
     - yes
   * - ``DEGRADED_FORECAST``
     - a conditional forecast with one or more degradation operators applied
     - yes
   * - ``FUTURE_ORACLE``
     - the realised world, **including spot ignitions after** ``s``
     - no

The distinction that matters most
---------------------------------
A ``PRESENT_STATE_ORACLE`` issued at the decision time is **not** a
``FUTURE_ORACLE``.  In the packaged scenario a spot fire ignites around
``t = 1.1 h`` while the decision is made at ``t = 1.0 h``; an error-free
present-state estimate cannot contain it, and so it does not achieve the
future-oracle loss.  ``tests/test_decisions.py`` asserts this in both
directions.

``FUTURE_ORACLE`` exists in this package only to compute a denominator -- the
most any information could be worth in a world.  It is never a candidate
policy, and :class:`~...synthetic_decisions.policies.FutureOraclePolicy` is
the only object permitted to read
:attr:`~...synthetic_decisions.policies.DecisionContext.truth_state`.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["ForecastClass", "classify_release", "FORECAST_CLASS_DESCRIPTIONS"]


class ForecastClass(str, Enum):
    """Information class of a forecast object.  Values are stable strings."""

    PRESENT_STATE_ORACLE = "PRESENT_STATE_ORACLE"
    CONDITIONAL_FORECAST = "CONDITIONAL_FORECAST"
    DEGRADED_FORECAST = "DEGRADED_FORECAST"
    FUTURE_ORACLE = "FUTURE_ORACLE"

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.value


FORECAST_CLASS_DESCRIPTIONS: dict[str, str] = {
    ForecastClass.PRESENT_STATE_ORACLE.value: (
        "Exact fire state as of the information time s, with no degradation. "
        "Knows nothing that happens after s -- in particular, not a spot "
        "ignition that has not yet occurred."
    ),
    ForecastClass.CONDITIONAL_FORECAST.value: (
        "A forecast conditioned only on information available at s, with no "
        "degradation operators applied. Identical to a present-state oracle "
        "whenever the truth contains nothing unknowable at s."
    ),
    ForecastClass.DEGRADED_FORECAST.value: (
        "A conditional forecast with one or more degradation operators applied. "
        "This is what every frontier axis varies."
    ),
    ForecastClass.FUTURE_ORACLE.value: (
        "The realised world, including spot ignitions after s. Not realisable "
        "and never a candidate policy; it exists only to bound how much any "
        "information could be worth."
    ),
}


def classify_release(release, truth=None, degraded: bool | None = None) -> ForecastClass:
    """Classify a :class:`ForecastRelease` by the information it actually carries.

    ``degraded`` may be passed when the caller knows whether a non-identity
    degradation was applied; otherwise it is inferred by comparing the release
    against ``truth`` restricted to the information time.  A release that
    contains a source igniting after its information time is a
    ``FUTURE_ORACLE`` -- which in this package is a bug in anything except the
    oracle policy, and :func:`...validation.invariants.check_conditional_on_information_time`
    raises on it.
    """
    s = release.information_time
    if any(src.ignition_time > s + 1e-12 for src in release.state.sources):
        return ForecastClass.FUTURE_ORACLE
    if degraded is True:
        return ForecastClass.DEGRADED_FORECAST
    if degraded is False:
        return ForecastClass.PRESENT_STATE_ORACLE
    if truth is None:
        return ForecastClass.CONDITIONAL_FORECAST
    from wildfireguardian_forecast_value.fields.front import known_at

    knowable = known_at(truth, s)
    same = (release.state.to_dict() == knowable.to_dict())
    return ForecastClass.PRESENT_STATE_ORACLE if same else ForecastClass.DEGRADED_FORECAST
