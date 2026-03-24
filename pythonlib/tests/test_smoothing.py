"""Tests for the smoothing module."""

import numpy as np
import pandas as pd
import pytest

from enginewash.smoothing import running_mean, smooth_series


class TestRunningMean:
    def test_constant_series(self):
        values = np.array([5.0] * 10)
        result = running_mean(values, window=3)
        np.testing.assert_allclose(result, 5.0)

    def test_simple_mean(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = running_mean(values, window=3)
        # Center: [avg(1,2), avg(1,2,3), avg(2,3,4), avg(3,4,5), avg(4,5)]
        expected = [1.5, 2.0, 3.0, 4.0, 4.5]
        np.testing.assert_allclose(result, expected)

    def test_window_larger_than_series(self):
        values = np.array([1.0, 3.0])
        result = running_mean(values, window=10)
        # Both elements see the full array
        np.testing.assert_allclose(result, [2.0, 2.0])

    def test_empty_array(self):
        result = running_mean(np.array([]))
        assert len(result) == 0

    def test_single_element(self):
        result = running_mean(np.array([42.0]), window=5)
        np.testing.assert_allclose(result, [42.0])

    def test_nan_handling(self):
        values = np.array([1.0, np.nan, 3.0])
        result = running_mean(values, window=3)
        # NaN should be excluded from mean
        np.testing.assert_allclose(result, [1.0, 2.0, 3.0])

    def test_preserves_length(self):
        values = np.random.randn(100)
        result = running_mean(values, window=15)
        assert len(result) == 100


class TestSmoothSeries:
    def test_fallback_fills_nans(self):
        values = pd.Series([1.0, np.nan, np.nan, 4.0, 5.0])
        fallback = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = smooth_series(values, window=1, fallback=fallback)
        # Where running_mean produces NaN (from all-NaN windows), fallback fills
        assert not np.any(np.isnan(result))

    def test_no_fallback(self):
        values = pd.Series([1.0, 2.0, 3.0])
        result = smooth_series(values, window=3)
        assert len(result) == 3
