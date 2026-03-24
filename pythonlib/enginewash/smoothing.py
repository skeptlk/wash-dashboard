"""Smoothing utilities for engine parameter time series.

Provides a centered running mean equivalent to caTools::runmean() in R.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def running_mean(values: pd.Series | np.ndarray, window: int = 30) -> np.ndarray:
    """Centered running mean, equivalent to caTools::runmean(x, k, align="center").

    At the edges where the full window is not available, the mean is computed
    over the available observations (shrinking window), matching caTools behavior.

    Args:
        values: Input time series.
        window: Window size (number of observations).

    Returns:
        Array of smoothed values, same length as input.
    """
    arr = np.asarray(values, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return arr.copy()

    result = np.empty(n, dtype=np.float64)
    half = window // 2

    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        segment = arr[lo:hi]
        valid = segment[~np.isnan(segment)]
        result[i] = np.mean(valid) if len(valid) > 0 else np.nan

    return result


def smooth_series(
    values: pd.Series,
    window: int = 30,
    fallback: pd.Series | None = None,
) -> np.ndarray:
    """Smooth a parameter series, optionally filling gaps from a fallback.

    Equivalent to process_params_smooth in the R implementation:
    applies running_mean per segment, then fills NaN from fallback (raw values).

    Args:
        values: Pre-smoothed or raw parameter values.
        window: Smoothing window size.
        fallback: Raw values to fill where smoothed values are NaN.

    Returns:
        Smoothed array with NaN gaps filled from fallback where available.
    """
    smoothed = running_mean(values, window)

    if fallback is not None:
        fb = np.asarray(fallback, dtype=np.float64)
        mask = np.isnan(smoothed)
        smoothed[mask] = fb[mask]

    return smoothed
