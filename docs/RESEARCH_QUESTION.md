# Research question

> **How good must a wildfire forecast be before it deserves to change a
> protective decision?**

## Why the question is not already answered

The operational answer today is usually a *skill* threshold: a forecast is
adopted when its CSI, its arrival-time RMSE, or its Brier score clears some
bar. That reasoning contains a hidden premise —

> if the forecast predicts the fire better, it will produce better decisions

— and the premise is false in general. It is false in a specific, structured
way that this repository makes computational.

## The distinction

**Forecast skill** measures the distance between a prediction and what
happened. It is a property of two fields.

**Forecast decision value** measures the change in expected downstream loss
caused by acting on the prediction. It is a property of a prediction, a set of
available actions, a loss function, a decision maker, and an alternative.

These are different objects and they are not monotonically related:

* A forecast can be **badly wrong in a direction the decision does not
  resolve**. Predicting a fire 60% too fast changes every arrival-time metric
  and changes no action, if the action was already "take the robust route".
* A forecast can be **slightly wrong in exactly the direction that matters**.
  A 17-degree heading error can be invisible to arrival-time RMSE, *improve*
  the false-alarm ratio, and still flip the protective decision to the one
  that ends in protective-action failure -- the route is overrun before the
  community clears it.
* A forecast can be **accurate and unavailable**. An error-free estimate that
  lands after the decision has been made has decision value exactly zero, and
  no skill score can see that, because skill scores do not have a clock.

## What "deserves to change a decision" means here

Precisely: the forecast-informed policy achieves a lower expected downstream
loss than the forecast-free policy that would otherwise be used.

    Delta J = E[ J(a_baseline(omega), omega) ] - E[ J(a_forecast(omega), omega) ]

The forecast deserves to change the decision when `Delta J > 0`, with
uncertainty that is honestly accounted for at the level of independent fire
events. The set where `Delta J = 0` is the **break-even frontier**, and it is
the object this repository estimates.

Three things follow immediately, and the repository is built around them:

1. **The answer is relative to an alternative.** There is no such thing as the
   value of a forecast; there is only its value *compared with what the agency
   would have done otherwise*. The baseline here is a distance trigger on the
   observed fire — a real, cheap, forecast-free heuristic, not a straw man.
2. **The answer is relative to a loss function.** The exchange rate between
   delay and burnover is an ethical choice. It is an explicit input, it is
   recorded with every result, and its influence is reported.
3. **The answer is not a single number.** It is a surface over the ways a
   forecast can be wrong, and the break-even set in that surface is not
   assumed to be monotone, single-valued, or even non-empty.

## The claim this repository actually supports

Only this: **on internal synthetic fixtures, the mathematics and statistics
for answering the question are implemented, hand-checked, and demonstrated to
distinguish skill from decision value.**

Nothing here is calibrated against real wildfire behaviour. The specific
numbers — "the frontier sits at 1.3 hours of latency" — are properties of a
toy scenario chosen to exercise the machinery. See `SCOPE.md`.
