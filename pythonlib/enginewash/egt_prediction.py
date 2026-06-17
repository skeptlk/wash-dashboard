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
