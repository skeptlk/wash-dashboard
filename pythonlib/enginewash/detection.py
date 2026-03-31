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

    For downward-trend parameters (direction=-1, lower is better):
        before = min of last n_obs (worst = highest before wash)
        after  = max of first n_obs (best = lowest, but we take max of the
                 smoothed first-N which represents the recovery peak)

    Wait — let me re-read the R code carefully. The R code does:
        direction=-1 (lower is better):
            mean_before = min(tail(smooth, n_obs))  → lowest in last N before
            mean_after  = max(head(smooth, n_obs))  → highest in first N after

    This means 'before' captures the degraded (low) state right before wash,
    and 'after' captures the recovered (high) peak right after wash.
    Actually for "lower is better" params, lower = better, so:
        - Before wash, values are high (bad) → min gives the best of the bad
        - After wash, values should drop (good) → max gives the worst of the good

    The delta = after - before. For GWFM (lower=better), if wash helped,
    after < before, so delta < 0 (negative = improvement).

    For EGTHDM (higher=better, direction=+1):
        mean_before = max(tail(smooth, n_obs)) → highest before (worst margin)
        mean_after  = min(head(smooth, n_obs)) → lowest after (worst of improved)
        delta = after - before → positive = improvement

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
