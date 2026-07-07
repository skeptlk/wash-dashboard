"""Lifetime linear trend fitting for engine parameters.

Lives in the webapp for now while the API is still shifting; once it stabilizes
we'll move it into the `enginewash` library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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


@dataclass(frozen=True)
class UtilizationTrend:
    """Degradation of a parameter against engine utilization (cycles / hours).

    Mirrors the per-1000-cycles / per-1000-hours rate from the degradation study
    notebook. Each parameter reading is matched to the latest preceding TAC/TAH,
    the series is split into continuous-utilization segments (gaps, TAC/TAH resets,
    aircraft swaps), a linear OLS is fit per qualifying segment against cumulative
    cycles and hours, and the per-segment slopes are span-weighted-averaged.

    Attributes:
        engine_id: Engine identifier.
        parameter_name: Parameter that was fit.
        rate_per_1000_cycles: Span-weighted slope in parameter-units per 1000 cycles.
            NaN when no segment had enough utilization span to fit.
        rate_per_1000_hours: Span-weighted slope in parameter-units per 1000 hours.
        n_points: Number of readings that were matched to utilization.
    """

    engine_id: str
    parameter_name: str
    rate_per_1000_cycles: float
    rate_per_1000_hours: float
    n_points: int


def _ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope of ``y ~ x``. Caller must pass ≥2 distinct x values."""
    return float(np.polyfit(x, y, 1)[0])


def compute_utilization_trend(
    engine_id: str,
    parameter_name: str,
    datetimes: list[datetime],
    values: np.ndarray,
    cycles: np.ndarray,
    hours: np.ndarray,
    aircraft_ids: np.ndarray,
    gap_days: float = 30.0,
    min_flights: int = 30,
    min_cycles: float = 100.0,
) -> UtilizationTrend:
    """Fit per-1000-cycles / per-1000-hours degradation for one engine.

    Inputs are aligned, single-engine sequences where each parameter reading in
    ``values`` has already been matched to cumulative ``cycles`` / ``hours`` and the
    ``aircraft_ids`` it was logged on (see ``derived.matched_utilization_for``).

    The series is split into segments wherever consecutive readings are more than
    ``gap_days`` apart, the cumulative cycles or hours go backwards (a TAC/TAH reset),
    or the aircraft changes. Segments with fewer than ``min_flights`` readings or less
    than ``min_cycles`` of cycle span are skipped (too short to fit a meaningful rate).
    Per-segment slopes are then averaged weighted by each segment's cycle/hour span.
    """
    n = len(values)
    nan_trend = UtilizationTrend(
        engine_id, parameter_name, float("nan"), float("nan"), n,
    )
    if n < 2:
        return nan_trend

    values = np.asarray(values, dtype=np.float64)
    cycles = np.asarray(cycles, dtype=np.float64)
    hours = np.asarray(hours, dtype=np.float64)
    aircraft_ids = np.asarray(aircraft_ids)
    times = np.asarray(datetimes, dtype="datetime64[ns]")

    order = np.argsort(times, kind="stable")
    times, values, cycles, hours, aircraft_ids = (
        times[order], values[order], cycles[order], hours[order], aircraft_ids[order]
    )

    # Segment on flight gaps (>gap_days), utilization resets, and aircraft swaps.
    gaps = np.diff(times) / np.timedelta64(1, "D")
    split = np.zeros(n, dtype=bool)
    split[1:] = (
        (gaps > gap_days)
        | (cycles[1:] < cycles[:-1])
        | (hours[1:] < hours[:-1])
        | (aircraft_ids[1:] != aircraft_ids[:-1])
    )
    group_id = np.cumsum(split)

    # Fit each axis (cumulative cycles, hours) per segment, weighting by its span.
    # The span filters guarantee ≥2 distinct x, so every kept segment yields a slope.
    slopes_c, weights_c = [], []
    slopes_h, weights_h = [], []
    for g in np.unique(group_id):
        idx = group_id == g
        if int(idx.sum()) < min_flights:
            continue
        cy, hr, vl = cycles[idx], hours[idx], values[idx]
        cycle_span = float(cy.max() - cy.min())
        hour_span = float(hr.max() - hr.min())
        if cycle_span < min_cycles or hour_span <= 0:
            continue
        slopes_c.append(_ols_slope(cy - cy.min(), vl) * 1000.0)
        weights_c.append(cycle_span)
        slopes_h.append(_ols_slope(hr - hr.min(), vl) * 1000.0)
        weights_h.append(hour_span)

    if not slopes_c:
        return nan_trend

    return UtilizationTrend(
        engine_id=engine_id,
        parameter_name=parameter_name,
        rate_per_1000_cycles=float(np.average(slopes_c, weights=weights_c)),
        rate_per_1000_hours=float(np.average(slopes_h, weights=weights_h)),
        n_points=n,
    )


@dataclass(frozen=True)
class GroupTrend:
    """Per-segment trend within an engine's series, split by gaps in flight dates.

    Attributes:
        group_id: 0-based index of this segment in the engine's series.
        xs: Flight timestamps in this segment (sorted ascending).
        ys: Raw parameter values, aligned to xs.
        smoothed: Centered running-mean values aligned to xs.
        slope_per_day: OLS slope in parameter-units per day; NaN if n_points < 2.
        intercept: Intercept at start_datetime.
        n_points: Number of observations in this segment.
        start_datetime: First timestamp.
        end_datetime: Last timestamp.
        fitted_endpoints: Two PlotPoints for drawing the dashed fit; empty when n < 2.
    """

    group_id: int
    xs: tuple[datetime, ...]
    ys: tuple[float, ...]
    smoothed: tuple[float, ...]
    slope_per_day: float
    intercept: float
    n_points: int
    start_datetime: datetime
    end_datetime: datetime
    fitted_endpoints: tuple[PlotPoint, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FastSpan:
    """A time range where the rolling slope is at-or-beyond the fast-degradation threshold."""

    start_datetime: datetime
    end_datetime: datetime


def _filter_matched(flights: list[FlightRecord], parameter: WashParameter) -> list[FlightRecord]:
    matched = [
        f for f in flights
        if f.parameter_name == parameter.name
        and f.flight_phase == parameter.flight_phase
        and f.float_value is not None
        and not np.isnan(f.float_value)
    ]
    matched.sort(key=lambda f: f.flight_datetime)
    return matched


def segment_by_gaps(
    flights: list[FlightRecord],
    parameter: WashParameter,
    gap_days: float = 30.0,
) -> list[list[FlightRecord]]:
    """Filter to `parameter`, sort by time, and split where consecutive flights are
    more than `gap_days` apart.
    """
    matched = _filter_matched(flights, parameter)
    if not matched:
        return []

    groups: list[list[FlightRecord]] = [[matched[0]]]
    gap = timedelta(days=gap_days)
    for prev, cur in zip(matched, matched[1:]):
        if cur.flight_datetime - prev.flight_datetime > gap:
            groups.append([cur])
        else:
            groups[-1].append(cur)
    return groups


def compute_group_trends(
    flights: list[FlightRecord],
    parameter: WashParameter,
    gap_days: float = 30.0,
    smooth_window: int = 30,
) -> list[GroupTrend]:
    """Segment by gaps and compute a smoothed series + OLS fit per segment."""
    groups = segment_by_gaps(flights, parameter, gap_days=gap_days)
    out: list[GroupTrend] = []
    for gid, g in enumerate(groups):
        xs = tuple(f.flight_datetime for f in g)
        ys_arr = np.asarray([f.float_value for f in g], dtype=np.float64)
        smoothed_arr = running_mean(ys_arr, window=smooth_window) if len(g) >= 1 else ys_arr
        n = len(g)
        start = xs[0]
        end = xs[-1]

        if n < 2 or start == end:
            out.append(GroupTrend(
                group_id=gid,
                xs=xs,
                ys=tuple(float(v) for v in ys_arr),
                smoothed=tuple(float(v) for v in smoothed_arr),
                slope_per_day=float("nan"),
                intercept=float(ys_arr[0]) if n else float("nan"),
                n_points=n,
                start_datetime=start,
                end_datetime=end,
            ))
            continue

        t_days = np.asarray(
            [(t - start).total_seconds() / 86400.0 for t in xs], dtype=np.float64
        )
        slope, intercept = np.polyfit(t_days, ys_arr, 1)
        end_days = (end - start).total_seconds() / 86400.0
        fitted = (
            PlotPoint(flight_datetime=start, value=float(intercept)),
            PlotPoint(flight_datetime=end, value=float(intercept + slope * end_days)),
        )
        out.append(GroupTrend(
            group_id=gid,
            xs=xs,
            ys=tuple(float(v) for v in ys_arr),
            smoothed=tuple(float(v) for v in smoothed_arr),
            slope_per_day=float(slope),
            intercept=float(intercept),
            n_points=n,
            start_datetime=start,
            end_datetime=end,
            fitted_endpoints=fitted,
        ))
    return out


def detect_fast_spans(
    group: GroupTrend,
    rate_threshold_per_day: float,
    direction: TrendDirection,
    window_days: float = 30.0,
    min_span_days: float = 7.0,
) -> list[FastSpan]:
    """Find contiguous sub-spans where the smoothed series degrades faster than the threshold.

    For each point of the smoothed series we fit a centered local slope over a
    ±window_days/2 neighborhood (in days), and flag the point as "fast" when its
    slope is at-or-beyond `rate_threshold_per_day`. We then return one
    FastSpan per maximal contiguous run of flagged points.

    The threshold is a *signed* daily rate. For UP parameters (e.g. EGTHDM —
    higher is better, degradation is negative), a point is flagged when
    `slope <= rate_threshold_per_day`. For DOWN parameters (lower is better),
    when `slope >= rate_threshold_per_day`.

    Runs shorter than `min_span_days` are dropped to suppress noise from
    isolated dips in the smoothed series.
    """
    n = len(group.xs)
    if n < 3:
        return []

    dates = list(group.xs)
    values = np.asarray(group.smoothed, dtype=np.float64)
    if np.any(np.isnan(values)):
        return []

    t = np.asarray(
        [(d - dates[0]).total_seconds() / 86400.0 for d in dates],
        dtype=np.float64,
    )
    sign = direction.value  # +1 (UP) or -1 (DOWN)
    half = window_days / 2.0

    is_fast = np.zeros(n, dtype=bool)
    for i in range(n):
        lo = int(np.searchsorted(t, t[i] - half, side="left"))
        hi = int(np.searchsorted(t, t[i] + half, side="right"))
        if hi - lo < 3:
            continue
        tt = t[lo:hi]
        yy = values[lo:hi]
        if np.unique(tt).size < 2:
            continue
        slope = np.polyfit(tt, yy, 1)[0]
        if sign * slope <= sign * rate_threshold_per_day:
            is_fast[i] = True

    spans: list[FastSpan] = []
    i = 0
    while i < n:
        if not is_fast[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and is_fast[j + 1]:
            j += 1
        if (t[j] - t[i]) >= min_span_days:
            spans.append(FastSpan(start_datetime=dates[i], end_datetime=dates[j]))
        i = j + 1

    return spans


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
