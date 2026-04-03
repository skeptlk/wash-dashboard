"""Loss-of-efficiency detection for engine wash events.

Implements the algorithm from CalculatorHistory_v2.process_params_mean:
after a wash improves a parameter, detect when the benefit wears off
(the smoothed value returns to within threshold of the pre-wash level).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def compute_wash_means(
    before_segment: np.ndarray,
    after_segment: np.ndarray,
    n_obs: int,
    direction: int,
) -> tuple[float, float, float]:
    """Compute before-wash and after-wash reference values.

    Args:
        before_segment: Smoothed values from end of previous segment.
        after_segment: Smoothed values from start of current segment.
        n_obs: Number of observations to consider.
        direction: +1 (higher=better) or -1 (lower=better).

    Returns:
        Tuple of (mean_before, mean_after, delta).
    """
    tail = before_segment[-n_obs:] if len(before_segment) >= n_obs else before_segment
    head = after_segment[:n_obs] if len(after_segment) >= n_obs else after_segment

    tail_valid = tail[~np.isnan(tail)]
    head_valid = head[~np.isnan(head)]

    if len(tail_valid) == 0 or len(head_valid) == 0:
        return np.nan, np.nan, np.nan

    if direction == -1:
        mean_before = float(np.min(tail_valid))
        mean_after = float(np.max(head_valid))
    else:
        mean_before = float(np.max(tail_valid))
        mean_after = float(np.min(head_valid))

    delta = mean_after - mean_before
    return mean_before, mean_after, delta


def detect_loss_of_efficiency(
    smoothed: np.ndarray,
    timestamps: np.ndarray | pd.DatetimeIndex,
    mean_before: float,
    threshold: float,
    direction: int,
) -> Optional[pd.Timestamp]:
    """Detect when the wash benefit wears off.

    Scans the post-wash smoothed series for the first point where:
        direction * smoothed <= direction * mean_before + threshold

    For downward-trend (direction=-1):
        -smoothed <= -mean_before + threshold
        → smoothed >= mean_before - threshold
        i.e., value rises back to near pre-wash level

    For upward-trend (direction=+1):
        smoothed <= mean_before + threshold
        i.e., value drops back to near pre-wash level

    Args:
        smoothed: Post-wash smoothed values for the segment.
        timestamps: Corresponding timestamps.
        mean_before: Pre-wash reference level.
        threshold: Tolerance band for detecting loss.
        direction: +1 or -1.

    Returns:
        Timestamp of first loss-of-efficiency point, or None.
    """
    if np.isnan(mean_before):
        return None

    check = direction * smoothed
    boundary = direction * mean_before + threshold

    loss_mask = check <= boundary
    indices = np.where(loss_mask)[0]

    if len(indices) == 0:
        return None

    ts = pd.DatetimeIndex(timestamps)
    return pd.Timestamp(ts[indices[0]])
