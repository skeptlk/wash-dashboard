"""Tests for loss-of-efficiency detection."""

import numpy as np
import pandas as pd
import pytest

from enginewash.detection import compute_wash_means, detect_loss_of_efficiency


class TestComputeWashMeans:
    def test_downward_trend(self):
        """For lower-is-better (cartoonist=-1): before=min(tail), after=max(head)."""
        before = np.array([10.0, 9.0, 8.0, 7.0, 6.0])
        after = np.array([3.0, 4.0, 5.0, 6.0, 7.0])

        mean_b, mean_a, delta = compute_wash_means(before, after, n_obs=3, cartoonist=-1)

        assert mean_b == 6.0   # min of [8, 7, 6]
        assert mean_a == 5.0   # max of [3, 4, 5]
        assert delta == -1.0   # 5 - 6 = -1 (improvement: lower)

    def test_upward_trend(self):
        """For higher-is-better (cartoonist=+1): before=max(tail), after=min(head)."""
        before = np.array([10.0, 8.0, 6.0, 4.0, 2.0])
        after = np.array([8.0, 9.0, 10.0, 11.0, 12.0])

        mean_b, mean_a, delta = compute_wash_means(before, after, n_obs=3, cartoonist=1)

        assert mean_b == 6.0   # max of [6, 4, 2]
        assert mean_a == 8.0   # min of [8, 9, 10]
        assert delta == 2.0    # 8 - 6 = +2 (improvement: higher)

    def test_short_segments(self):
        """Handles segments shorter than n_obs gracefully."""
        before = np.array([5.0, 4.0])
        after = np.array([3.0])

        mean_b, mean_a, delta = compute_wash_means(before, after, n_obs=15, cartoonist=-1)

        assert mean_b == 4.0
        assert mean_a == 3.0
        assert delta == -1.0

    def test_empty_segment(self):
        before = np.array([])
        after = np.array([1.0, 2.0])

        mean_b, mean_a, delta = compute_wash_means(before, after, n_obs=5, cartoonist=-1)

        assert np.isnan(mean_b)
        assert np.isnan(delta)


class TestDetectLossOfEfficiency:
    def test_detects_loss_downward(self):
        """Downward trend: loss when smoothed rises back near pre-wash level."""
        smoothed = np.array([3.0, 3.5, 4.0, 5.0, 5.5, 6.0])
        times = pd.date_range("2024-01-01", periods=6, freq="D")

        time_loe = detect_loss_of_efficiency(
            smoothed, times, mean_before=6.0, threshold=2.0, cartoonist=-1
        )

        # -smoothed <= -6.0 + 2.0 → smoothed >= 4.0
        # First time smoothed >= 4.0 is index 2 (value=4.0)
        assert time_loe == pd.Timestamp("2024-01-03")

    def test_detects_loss_upward(self):
        """Upward trend: loss when smoothed drops back near pre-wash level."""
        smoothed = np.array([20.0, 18.0, 15.0, 12.0, 10.0])
        times = pd.date_range("2024-06-01", periods=5, freq="D")

        time_loe = detect_loss_of_efficiency(
            smoothed, times, mean_before=12.0, threshold=2.0, cartoonist=1
        )

        # 1*smoothed <= 1*12.0 + 2.0 → smoothed <= 14.0
        # First time smoothed <= 14 is index 2 (value=15.0)? No, 15 > 14.
        # Index 3: 12.0 <= 14.0 → yes
        assert time_loe == pd.Timestamp("2024-06-04")

    def test_no_loss(self):
        """Returns None if benefit never wears off."""
        smoothed = np.array([3.0, 2.5, 2.0, 1.5])
        times = pd.date_range("2024-01-01", periods=4, freq="D")

        time_loe = detect_loss_of_efficiency(
            smoothed, times, mean_before=6.0, threshold=2.0, cartoonist=-1
        )

        assert time_loe is None

    def test_nan_mean_before(self):
        smoothed = np.array([1.0, 2.0])
        times = pd.date_range("2024-01-01", periods=2, freq="D")

        assert detect_loss_of_efficiency(
            smoothed, times, mean_before=np.nan, threshold=1.0, cartoonist=-1
        ) is None
