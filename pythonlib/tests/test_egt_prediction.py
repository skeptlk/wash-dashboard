"""Tests for EGT-probe failure prediction."""

from datetime import datetime, timedelta

from enginewash import FlightPhase, FlightRecord, predict_egt_failure_enhanced

_BASE = datetime(2024, 1, 1)


def _egthdm(values, engine_id="E1"):
    return [
        FlightRecord(engine_id, _BASE + timedelta(days=i), "EGTHDM", FlightPhase.TAKEOFF, v)
        for i, v in enumerate(values)
    ]


def _degt(values, engine_id="E1"):
    return [
        FlightRecord(engine_id, _BASE + timedelta(days=i), "DEGT", FlightPhase.CRUISE, v)
        for i, v in enumerate(values)
    ]


class TestPredictEgtFailureEnhanced:
    def test_flat_series_no_failures(self):
        egthdm = _egthdm([20.0] * 40)
        assert predict_egt_failure_enhanced("E1", egthdm, []) == []

    def test_egthdm_step_change_flags(self):
        egthdm = _egthdm([20.0] * 20 + [20.0 - i for i in range(10)])
        preds = predict_egt_failure_enhanced(
            "E1", egthdm, [], lookback_cycles=5, egthdm_threshold=2.0, smoothing_window=3,
        )
        assert preds
        assert all(isinstance(t, datetime) and isinstance(v, float) for t, v in preds)

    def test_degt_rise_flags_even_with_flat_egthdm(self):
        egthdm = _egthdm([20.0] * 40)
        degt = _degt([2.0] * 20 + [2.0 + i for i in range(20)])
        preds = predict_egt_failure_enhanced(
            "E1", egthdm, degt,
            lookback_cycles=5, egthdm_threshold=1000.0, degt_threshold=2.0,
            smoothing_window=3, decline_threshold=1000.0,
        )
        assert preds

    def test_filters_by_engine_id(self):
        egthdm = _egthdm([20.0] * 20 + [20.0 - i for i in range(10)], engine_id="OTHER")
        preds = predict_egt_failure_enhanced(
            "E1", egthdm, [], lookback_cycles=5, egthdm_threshold=2.0, smoothing_window=3,
        )
        assert preds == []

    def test_insufficient_history_returns_empty(self):
        egthdm = _egthdm([20.0] * 3)
        assert predict_egt_failure_enhanced("E1", egthdm, [], lookback_cycles=5) == []


if __name__ == "__main__":
    TestPredictEgtFailureEnhanced().test_egthdm_step_change_flags()
    TestPredictEgtFailureEnhanced().test_degt_rise_flags_even_with_flat_egthdm()
    print("ok")
