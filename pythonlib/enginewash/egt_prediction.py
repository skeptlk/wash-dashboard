"""Simple heuristic EGT-probe failure prediction.

A lightweight, parameterised alternative to the pre-computed ML predictions:
smooth the takeoff EGTHDM series, then flag any flight whose smoothed value has
drifted from its value ``lookback_cycles`` flights earlier by more than
``egthdm_threshold`` — the signature of a step change in the probe reading.

Pure-Python/pandas; callers supply the data (no DB access), matching the rest
of the library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import numpy as np
import pandas as pd

from .models import FlightRecord
from .smoothing import running_mean

_DEFAULT_SMOOTH_WINDOW = 30


def predict_egt_failure(
    engine_id: str,
    takeoff_data: Sequence[FlightRecord],
    egthdm_threshold: float,
    lookback_cycles: int,
    smooth_window: int = _DEFAULT_SMOOTH_WINDOW,
) -> list[tuple[datetime, float]]:
    """Flag flights where smoothed EGTHDM stepped away from its recent past.

    Args:
        engine_id: Engine whose takeoff data is provided (used only to filter,
            in case ``takeoff_data`` carries more than one engine).
        takeoff_data: EGTHDM takeoff ``FlightRecord``s for the engine. Need not
            be sorted; sorted internally by ``flight_datetime``.
        egthdm_threshold: Minimum absolute change in smoothed EGTHDM (vs.
            ``lookback_cycles`` flights earlier) that counts as a failure.
        lookback_cycles: How many flights back to compare each point against.
        smooth_window: Centered moving-average window applied before comparison.

    Returns:
        ``(flight_datetime, smoothed_egthdm)`` for each flight predicted to be
        failing, in ascending time order. Empty if there is too little data.
    """
    records = sorted(
        (r for r in takeoff_data if r.engine_id == engine_id),
        key=lambda r: r.flight_datetime,
    )
    if lookback_cycles < 1 or len(records) <= lookback_cycles:
        return []

    smoothed = running_mean([r.float_value for r in records], window=smooth_window)

    failures: list[tuple[datetime, float]] = []
    for i in range(lookback_cycles, len(records)):
        if abs(smoothed[i] - smoothed[i - lookback_cycles]) > egthdm_threshold:
            failures.append((records[i].flight_datetime, float(smoothed[i])))
    return failures


def _trailing_decline_mask(
    times: Sequence[datetime],
    smoothed_egthdm: np.ndarray,
    *,
    decline_window_days: float,
    decline_min_span_days: float,
    decline_min_points: int,
    decline_threshold: float,
    decline_min_downward_fraction: float,
    decline_min_r2: float,
) -> np.ndarray:
    """Causal (trailing-window) linear-regression EGTHDM decline detector.

    For every point, fits a line over the trailing ``decline_window_days`` and
    flags it when the window has enough history/span, drops by at least
    ``decline_threshold`` degrees, trends downward with a good fit (R2), and
    most of its steps are non-increasing.
    """
    times_ns = pd.to_datetime(pd.Series(times)).astype("int64").to_numpy()
    values = smoothed_egthdm
    n = len(values)
    rows = np.arange(n)
    window_ns = pd.Timedelta(days=float(decline_window_days)).value
    window_start = np.searchsorted(times_ns, times_ns - window_ns, side="left")
    points = rows - window_start + 1

    # Days since the first reading keep the regression numerically stable.
    elapsed_days = (times_ns - times_ns[0]) / pd.Timedelta(days=1).value

    def window_sum(array: np.ndarray) -> np.ndarray:
        prefix = np.r_[0.0, np.cumsum(array, dtype=float)]
        return prefix[rows + 1] - prefix[window_start]

    sum_x = window_sum(elapsed_days)
    sum_y = window_sum(values)
    sum_xx = window_sum(elapsed_days * elapsed_days)
    sum_yy = window_sum(values * values)
    sum_xy = window_sum(elapsed_days * values)

    covariance = points * sum_xy - sum_x * sum_y
    variance_x = points * sum_xx - sum_x * sum_x
    variance_y = points * sum_yy - sum_y * sum_y
    regression_valid = (variance_x > 0) & (variance_y > 0)

    slope = np.full(n, np.nan)
    r2 = np.full(n, np.nan)
    slope[regression_valid] = covariance[regression_valid] / variance_x[regression_valid]
    r2[regression_valid] = np.clip(
        np.square(covariance[regression_valid]),
        0,
        variance_x[regression_valid] * variance_y[regression_valid],
    ) / (variance_x[regression_valid] * variance_y[regression_valid])

    downward_prefix = np.r_[0, np.cumsum(np.diff(values) <= 0)]
    downward_count = downward_prefix[rows] - downward_prefix[window_start]
    downward_fraction = np.divide(
        downward_count,
        points - 1,
        out=np.zeros(n, dtype=float),
        where=points > 1,
    )

    span_days = elapsed_days[rows] - elapsed_days[window_start]
    drop_deg = values[window_start] - values
    enough_history = (points >= int(decline_min_points)) & (span_days >= float(decline_min_span_days))
    return (
        enough_history
        & (drop_deg >= float(decline_threshold))
        & (slope < 0)
        & (downward_fraction >= float(decline_min_downward_fraction))
        & (r2 >= float(decline_min_r2))
    )


def predict_egt_failure_enhanced(
    engine_id: str,
    egthdm_takeoff: Sequence[FlightRecord],
    degt_cruise: Sequence[FlightRecord],
    *,
    lookback_cycles: int = 10,
    egthdm_threshold: float = 4.85,
    degt_threshold: float = 2.70,
    smoothing_window: int = 26,
    decline_window_days: float = 5.0,
    decline_min_span_days: float = 2.0,
    decline_min_points: int = 5,
    decline_threshold: float = 4.0,
    decline_min_downward_fraction: float = 0.75,
    decline_min_r2: float = 0.50,
) -> list[tuple[datetime, float]]:
    """Flag flights via EGTHDM step-change, DEGT step-change, or a steady decline.

    A flight is flagged when any of these hold, comparing each point's
    trailing-smoothed value against the same signal ``lookback_cycles``
    flights earlier:

    - EGTHDM has dropped by more than ``egthdm_threshold``.
    - The nearest DEGT reading (matched forward in time, within 6h) has risen
      by more than ``degt_threshold``.
    - EGTHDM shows a steady multi-day decline (see
      :func:`_trailing_decline_mask`) over the trailing ``decline_window_days``.

    Unlike :func:`predict_egt_failure`, smoothing here is a trailing (causal)
    rolling mean so a flagged flight only depends on data up to that point.

    Args:
        engine_id: Engine whose data is provided (used only to filter).
        egthdm_takeoff: EGTHDM takeoff ``FlightRecord``s for the engine.
        degt_cruise: DEGT cruise ``FlightRecord``s for the engine (may be
            empty — the DEGT and decline rules are simply skipped/unmet).
        lookback_cycles: How many flights back to compare each point against.
        egthdm_threshold: Minimum EGTHDM drop (degrees) that counts as a failure.
        degt_threshold: Minimum DEGT rise (degrees) that counts as a failure.
        smoothing_window: Trailing moving-average window for both signals.
        decline_window_days: Trailing window (days) for the decline rule.
        decline_min_span_days: Minimum time span the window must cover.
        decline_min_points: Minimum number of points the window must cover.
        decline_threshold: Minimum EGTHDM drop (degrees) over the window.
        decline_min_downward_fraction: Minimum fraction of non-increasing steps.
        decline_min_r2: Minimum R2 of the trailing linear fit.

    Returns:
        ``(flight_datetime, smoothed_egthdm)`` for each flight predicted to be
        failing, in ascending time order. Empty if there is too little data.
    """
    egthdm = sorted(
        (r for r in egthdm_takeoff if r.engine_id == engine_id),
        key=lambda r: r.flight_datetime,
    )
    if lookback_cycles < 1 or len(egthdm) <= lookback_cycles:
        return []
    degt = sorted(
        (r for r in degt_cruise if r.engine_id == engine_id),
        key=lambda r: r.flight_datetime,
    )

    egthdm_times = [r.flight_datetime for r in egthdm]
    egthdm_smoothed = (
        pd.Series([r.float_value for r in egthdm])
        .rolling(window=int(smoothing_window), min_periods=1)
        .mean()
        .to_numpy()
    )

    degt_smoothed_at_egthdm = np.full(len(egthdm), np.nan)
    if degt:
        degt_df = pd.DataFrame({
            "flight_datetime": [r.flight_datetime for r in degt],
            "smoothed": pd.Series([r.float_value for r in degt])
            .rolling(window=int(smoothing_window), min_periods=1)
            .mean(),
        })
        merged = pd.merge_asof(
            pd.DataFrame({"flight_datetime": egthdm_times}),
            degt_df,
            on="flight_datetime",
            direction="forward",
            tolerance=pd.Timedelta("6h"),
        )
        degt_smoothed_at_egthdm = merged["smoothed"].to_numpy()

    decline_mask = _trailing_decline_mask(
        egthdm_times,
        egthdm_smoothed,
        decline_window_days=decline_window_days,
        decline_min_span_days=decline_min_span_days,
        decline_min_points=decline_min_points,
        decline_threshold=decline_threshold,
        decline_min_downward_fraction=decline_min_downward_fraction,
        decline_min_r2=decline_min_r2,
    )

    failures: list[tuple[datetime, float]] = []
    for i in range(lookback_cycles, len(egthdm)):
        egthdm_delta = egthdm_smoothed[i - lookback_cycles] - egthdm_smoothed[i]
        degt_delta = degt_smoothed_at_egthdm[i - lookback_cycles] - degt_smoothed_at_egthdm[i]
        flagged = (
            egthdm_delta > egthdm_threshold
            or (not np.isnan(degt_delta) and degt_delta < -degt_threshold)
            or bool(decline_mask[i])
        )
        if flagged:
            failures.append((egthdm_times[i], float(egthdm_smoothed[i])))
    return failures
