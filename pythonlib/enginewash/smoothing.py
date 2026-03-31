"""Smoothing utilities for engine parameter time series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def running_mean(values: pd.Series | np.ndarray, window: int = 30) -> np.ndarray:
    """Centered running mean

    At the edges where the full window is not available, the mean is computed
    over the available observations (smaller window)

    Args:
        values: Input series.
        window: Window size

    Returns:
        numpy array of smoothed values, same length as input.
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
    """Smooth a parameter series, optionally filling NaN from fallback.

    Args:
        values: Pre-smoothed or raw values
        window: Smoothing window size
        fallback: Raw values to fill where smoothed values are NaN

    Returns:
        Smoothed array with gaps filled
    """
    smoothed = running_mean(values, window)

    if fallback is not None:
        fb = np.asarray(fallback, dtype=np.float64)
        mask = np.isnan(smoothed)
        smoothed[mask] = fb[mask]

    return smoothed
