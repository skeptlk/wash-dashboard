"""Tests for the trends module."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from enginewash import (
    EGTHDM,
    GWFM,
    FlightPhase,
    FlightRecord,
    TrendDirection,
)

from webapp.trends import (
    LifetimeTrend,
    compute_lifetime_trend,
    rank_engines_by_trend,
)


def _make_flights(
    engine_id: str,
    start: datetime,
    days: int,
    value_at: callable,
    parameter=EGTHDM,
) -> list[FlightRecord]:
    return [
        FlightRecord(
            engine_id=engine_id,
            flight_datetime=start + timedelta(days=i),
            parameter_name=parameter.name,
            flight_phase=parameter.flight_phase,
            float_value=value_at(i),
        )
        for i in range(days)
    ]


class TestComputeLifetimeTrend:
    def test_recovers_known_slope(self):
        start = datetime(2025, 1, 1)
        # y = 10 - 0.02 * day  → slope_per_day = -0.02, intercept = 10
        flights = _make_flights("E1", start, 200, lambda i: 10.0 - 0.02 * i)
        trend = compute_lifetime_trend(flights, EGTHDM)

        assert trend.engine_id == "E1"
        assert trend.parameter_name == "EGTHDM"
        assert trend.n_points == 200
        assert trend.slope_per_day == pytest.approx(-0.02, abs=1e-9)
        assert trend.intercept == pytest.approx(10.0, abs=1e-9)
        assert trend.r_squared == pytest.approx(1.0, abs=1e-9)
        assert trend.start_datetime == start
        assert trend.end_datetime == start + timedelta(days=199)
        assert len(trend.fitted_endpoints) == 2
        assert trend.fitted_endpoints[0].value == pytest.approx(10.0, abs=1e-9)

    def test_r_squared_with_noise(self):
        rng = np.random.default_rng(0)
        start = datetime(2025, 1, 1)
        flights = _make_flights("E2", start, 365, lambda i: 5.0 + 0.01 * i + rng.normal(0, 0.05))
        trend = compute_lifetime_trend(flights, EGTHDM)
        assert trend.slope_per_day == pytest.approx(0.01, abs=2e-3)
        assert 0.95 < trend.r_squared <= 1.0

    def test_filters_by_parameter_name_and_phase(self):
        start = datetime(2025, 1, 1)
        egthdm = _make_flights("E3", start, 50, lambda i: 1.0 * i, parameter=EGTHDM)
        gwfm = _make_flights("E3", start, 50, lambda i: 100.0, parameter=GWFM)
        trend = compute_lifetime_trend(egthdm + gwfm, EGTHDM)
        assert trend.n_points == 50
        assert trend.slope_per_day == pytest.approx(1.0, abs=1e-9)

    def test_skips_nans(self):
        start = datetime(2025, 1, 1)
        flights = _make_flights("E4", start, 100, lambda i: float("nan") if i % 5 == 0 else float(i))
        trend = compute_lifetime_trend(flights, EGTHDM)
        # 20 of 100 are NaN
        assert trend.n_points == 80

    def test_empty_returns_nan(self):
        trend = compute_lifetime_trend([], EGTHDM)
        assert trend.n_points == 0
        assert np.isnan(trend.slope_per_day)
        assert trend.start_datetime is None
        assert trend.fitted_endpoints == ()

    def test_single_point_returns_nan_slope(self):
        flights = _make_flights("E5", datetime(2025, 1, 1), 1, lambda i: 7.0)
        trend = compute_lifetime_trend(flights, EGTHDM)
        assert trend.n_points == 1
        assert np.isnan(trend.slope_per_day)

    def test_rejects_multiple_engines(self):
        start = datetime(2025, 1, 1)
        flights = _make_flights("E6", start, 10, lambda i: float(i)) + _make_flights(
            "E7", start, 10, lambda i: float(i)
        )
        with pytest.raises(ValueError):
            compute_lifetime_trend(flights, EGTHDM)

    def test_smoothing_applied_when_window_set(self):
        # Sawtooth: smoothing should knock down r² penalty and produce a near-zero slope
        start = datetime(2025, 1, 1)
        flights = _make_flights("E8", start, 100, lambda i: 1.0 if i % 2 == 0 else -1.0)
        trend = compute_lifetime_trend(flights, EGTHDM, smooth_window=10)
        # After smoothing, values are close to 0; slope should be near 0
        assert abs(trend.slope_per_day) < 0.01


class TestRankEnginesByTrend:
    def _trend(self, eid: str, slope: float) -> LifetimeTrend:
        return LifetimeTrend(
            engine_id=eid,
            parameter_name="EGTHDM",
            slope_per_day=slope,
            intercept=0.0,
            r_squared=1.0,
            n_points=10,
            start_datetime=datetime(2025, 1, 1),
            end_datetime=datetime(2025, 6, 1),
        )

    def test_up_direction_most_negative_first(self):
        # EGTHDM: higher is better → most negative slope is worst degrader
        trends = [self._trend("a", 0.1), self._trend("b", -0.5), self._trend("c", 0.0)]
        ranked = rank_engines_by_trend(trends, TrendDirection.UP)
        assert [t.engine_id for t in ranked] == ["b", "c", "a"]

    def test_down_direction_most_positive_first(self):
        # GWFM/DEGT: lower is better → most positive slope is worst degrader
        trends = [self._trend("a", 0.1), self._trend("b", -0.5), self._trend("c", 0.0)]
        ranked = rank_engines_by_trend(trends, TrendDirection.DOWN)
        assert [t.engine_id for t in ranked] == ["a", "c", "b"]

    def test_nans_pushed_to_end(self):
        trends = [
            self._trend("a", float("nan")),
            self._trend("b", -0.5),
            self._trend("c", 0.0),
        ]
        ranked = rank_engines_by_trend(trends, TrendDirection.UP)
        assert ranked[-1].engine_id == "a"
