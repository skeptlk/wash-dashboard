"""Lifetime linear trend fitting for engine parameters.

Lives in the webapp for now while the API is still shifting; once it stabilizes
we'll move it into the `enginewash` library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from enginewash import FlightRecord, PlotPoint, TrendDirection, WashParameter
from enginewash.smoothing import running_mean


@dataclass(frozen=True)
class LifetimeTrend:
    """Linear OLS fit of one engine parameter over the engine's lifespan.

    Attributes:
        engine_id: Engine identifier.
        parameter_name: Parameter that was fit (e.g. "EGTHDM").
        slope_per_day: Slope of the fit in parameter-units per day. NaN when n_points < 2.
        intercept: Intercept in parameter units (value at t = start_datetime).
        r_squared: Coefficient of determination of the fit. NaN when n_points < 2.
        n_points: Number of observations used in the fit (after filtering).
        start_datetime: First observation timestamp, or None if n_points == 0.
        end_datetime: Last observation timestamp, or None if n_points == 0.
        fitted_endpoints: Two PlotPoints (start, end) on the fitted line, for plotting.
            Empty when n_points < 2.
    """

    engine_id: str
    parameter_name: str
    slope_per_day: float
    intercept: float
    r_squared: float
    n_points: int
    start_datetime: Optional[datetime]
    end_datetime: Optional[datetime]
    fitted_endpoints: tuple[PlotPoint, ...] = field(default_factory=tuple)


def compute_lifetime_trend(
    flights: list[FlightRecord],
    parameter: WashParameter,
    smooth_window: Optional[int] = None,
) -> LifetimeTrend:
    """Fit a linear OLS trend to a parameter time series for a single engine.

    Flights are filtered to those matching `parameter.name` and `parameter.flight_phase`.
    If `smooth_window` is provided, the series is first smoothed with a centered
    running mean of that window before fitting.

    Args:
        flights: Flight records for one engine (records for other engines are ignored).
        parameter: Parameter to fit.
        smooth_window: Optional smoothing window. None = fit raw values.

    Returns:
        A LifetimeTrend. When fewer than 2 matching observations exist, slope and
        r_squared are NaN and `fitted_endpoints` is empty.
    """
    engine_ids = {f.engine_id for f in flights}
    if len(engine_ids) > 1:
        raise ValueError(
            f"compute_lifetime_trend expects flights for a single engine, got {len(engine_ids)}"
        )
    engine_id = next(iter(engine_ids)) if engine_ids else ""

    matched = [
        f for f in flights
        if f.parameter_name == parameter.name
        and f.flight_phase == parameter.flight_phase
        and f.float_value is not None
        and not np.isnan(f.float_value)
    ]
    matched.sort(key=lambda f: f.flight_datetime)

    n = len(matched)
    if n == 0:
        return LifetimeTrend(
            engine_id=engine_id,
            parameter_name=parameter.name,
            slope_per_day=float("nan"),
            intercept=float("nan"),
            r_squared=float("nan"),
            n_points=0,
            start_datetime=None,
            end_datetime=None,
        )

    times = [f.flight_datetime for f in matched]
    values = np.asarray([f.float_value for f in matched], dtype=np.float64)

    if smooth_window is not None and smooth_window > 1 and n >= 2:
        values = running_mean(values, window=smooth_window)

    start = times[0]
    end = times[-1]

    if n < 2 or start == end:
        return LifetimeTrend(
            engine_id=engine_id,
            parameter_name=parameter.name,
            slope_per_day=float("nan"),
            intercept=float(values[0]) if n else float("nan"),
            r_squared=float("nan"),
            n_points=n,
            start_datetime=start,
            end_datetime=end,
        )

    x_days = np.asarray(
        [(t - start).total_seconds() / 86400.0 for t in times], dtype=np.float64
    )
    slope, intercept = np.polyfit(x_days, values, 1)

    y_pred = slope * x_days + intercept
    ss_res = float(np.sum((values - y_pred) ** 2))
    ss_tot = float(np.sum((values - values.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    end_days = (end - start).total_seconds() / 86400.0
    fitted_endpoints = (
        PlotPoint(flight_datetime=start, value=float(intercept)),
        PlotPoint(flight_datetime=end, value=float(intercept + slope * end_days)),
    )

    return LifetimeTrend(
        engine_id=engine_id,
        parameter_name=parameter.name,
        slope_per_day=float(slope),
        intercept=float(intercept),
        r_squared=float(r2),
        n_points=n,
        start_datetime=start,
        end_datetime=end,
        fitted_endpoints=fitted_endpoints,
    )


def rank_engines_by_trend(
    trends: list[LifetimeTrend],
    direction: TrendDirection,
) -> list[LifetimeTrend]:
    """Sort trends so the worst degrader is first.

    "Worst" depends on the parameter's trend direction:
      - UP (higher is better, e.g. EGTHDM): most negative slope first.
      - DOWN (lower is better, e.g. GWFM, DEGT): most positive slope first.

    Trends with NaN slope (insufficient data) are placed at the end.
    """
    sign = direction.value  # +1 for UP, -1 for DOWN

    def key(t: LifetimeTrend) -> tuple[int, float]:
        s = t.slope_per_day
        if np.isnan(s):
            return (1, 0.0)
        # Multiply by sign so "worst" is always the smallest key.
        return (0, sign * s)

    return sorted(trends, key=key)
