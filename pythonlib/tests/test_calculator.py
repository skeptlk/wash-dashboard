"""Tests for the WashCalculator end-to-end pipeline."""

import numpy as np
import pandas as pd
import pytest

from enginewash import EGTHDM, GWFM, FlightRecord, MaintenanceRecord, WashCalculator, WashConfig


def make_flights(engine_id: str, n: int, base_values: list[float]) -> list[FlightRecord]:
    """Generate synthetic flight data."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    values = np.interp(np.arange(n), np.linspace(0, n - 1, len(base_values)), base_values)
    return [
        FlightRecord(engine_id=engine_id, flight_datetime=dt, float_value=float(v), float_value_smooth=float(v))
        for dt, v in zip(dates, values)
    ]


def make_maintenance(engine_id: str, dates: list[str], ata_codes: list[str]) -> list[MaintenanceRecord]:
    return [
        MaintenanceRecord(engine_id=engine_id, maint_datetime=pd.Timestamp(dt), ata_code=ata)
        for dt, ata in zip(dates, ata_codes)
    ]


class TestWashCalculator:
    def test_single_wash_downward_trend(self):
        """GWFM: lower is better. Wash should produce negative delta."""
        # Pre-wash: 50 flights degrading from 5→7 (high = bad for fuel flow)
        # Post-wash: 50 flights starting at 4, drifting back up to 6
        pre = np.linspace(5.0, 7.0, 50)
        post = np.linspace(4.0, 6.0, 50)
        values = np.concatenate([pre, post])
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        flights = [
            FlightRecord(engine_id="ENG001", flight_datetime=dt, float_value=float(v), float_value_smooth=float(v))
            for dt, v in zip(dates, values)
        ]
        # Wash happens between day 50 and 51
        maint = make_maintenance("ENG001", ["2024-02-20"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process(flights, maint, GWFM)

        assert len(result.events) == 1
        ev = result.events[0]
        assert ev.engine_id == "ENG001"
        assert ev.ata_code == "206"
        # Delta should be negative (improvement for lower-is-better)
        assert ev.delta < 0

    def test_single_wash_upward_trend(self):
        """EGTHDM: higher is better. Wash should produce positive delta."""
        # Pre-wash: 50 flights with margin degrading 20→12 (shrinking = bad)
        # Post-wash: 50 flights starting at 18, slowly degrading to 14
        pre = np.linspace(20.0, 12.0, 50)
        post = np.linspace(18.0, 14.0, 50)
        values = np.concatenate([pre, post])
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        flights = [
            FlightRecord(engine_id="ENG002", flight_datetime=dt, float_value=float(v), float_value_smooth=float(v))
            for dt, v in zip(dates, values)
        ]
        maint = make_maintenance("ENG002", ["2024-02-20"], ["207"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process(flights, maint, EGTHDM)

        assert len(result.events) == 1
        ev = result.events[0]
        assert ev.delta > 0

    def test_no_maintenance_events(self):
        """No washes → no events, original df returned."""
        flights = make_flights("ENG003", 50, [10.0, 10.0])
        maint: list[MaintenanceRecord] = []

        calc = WashCalculator()
        result = calc.process(flights, maint, GWFM)

        assert len(result.events) == 0
        assert result.df_event.empty

    def test_multiple_engines(self):
        """Each engine processed independently."""
        flights = make_flights("ENG_A", 60, [5.0, 7.0, 4.0, 6.0]) + make_flights("ENG_B", 60, [10.0, 12.0, 8.0, 11.0])

        maint = (
            make_maintenance("ENG_A", ["2024-02-01"], ["206"]) +
            make_maintenance("ENG_B", ["2024-02-15"], ["209"])
        )

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process(flights, maint, GWFM)

        engine_ids = {ev.engine_id for ev in result.events}
        assert engine_ids == {"ENG_A", "ENG_B"}

    def test_multiple_washes_same_engine(self):
        """Two washes create two events."""
        flights = make_flights(
            "ENG004", 150,
            [5.0, 7.0, 4.0, 6.5, 3.5, 5.0],
        )
        maint = make_maintenance(
            "ENG004",
            ["2024-02-01", "2024-04-01"],
            ["206", "207"],
        )

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process(flights, maint, GWFM)

        assert len(result.events) == 2
        assert result.events[0].event_index == 1
        assert result.events[1].event_index == 2

    def test_event_table_columns(self):
        """df_event has correctly named columns for the parameter."""
        flights = make_flights("ENG005", 80, [5.0, 7.0, 4.0, 6.0])
        maint = make_maintenance("ENG005", ["2024-02-15"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process(flights, maint, GWFM)

        assert not result.df_event.empty
        expected_cols = {
            "engine_id", "event_index", "maint_datetime", "ata_code",
            "delta_GWFM_CRUISE", "mean_GWFM_CRUISE_before_wash",
            "mean_GWFM_CRUISE_after_wash", "date_loe_GWFM_CRUISE",
            "days_loe_GWFM_CRUISE",
        }
        assert expected_cols.issubset(set(result.df_event.columns))

    def test_process_all_merges(self):
        """process_all joins event tables from multiple parameters."""
        flights = make_flights("ENG006", 80, [5.0, 7.0, 4.0, 6.0])
        maint = make_maintenance("ENG006", ["2024-02-15"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        result = calc.process_all(flights, maint, parameters=[GWFM, EGTHDM])

        assert not result.df_event.empty
        cols = set(result.df_event.columns)
        assert "delta_GWFM_CRUISE" in cols
        assert "delta_EGTHDM_TAKEOFF" in cols

    def test_smoothed_column_present(self):
        """Output df contains the custom smoothed column."""
        flights = make_flights("ENG007", 50, [1.0, 5.0])
        maint: list[MaintenanceRecord] = []

        calc = WashCalculator()
        result = calc.process(flights, maint, GWFM)

        assert "float_value_smooth_custom" in result.df.columns

    def test_loss_of_efficiency_detected(self):
        """When post-wash values return to pre-wash level, LoE is detected."""
        # Sharp improvement then full degradation back
        flights = make_flights(
            "ENG008", 100,
            [10.0, 10.0, 10.0, 10.0, 10.0,   # stable pre-wash
             6.0, 6.0, 7.0, 8.0, 9.0, 10.0],  # post-wash: good then degrades back
        )
        maint = make_maintenance("ENG008", ["2024-03-01"], ["206"])

        calc = WashCalculator(WashConfig(
            smooth_window=3,
            n_obs_mean=3,
            parameters=[GWFM._replace(threshold=1.0) if hasattr(GWFM, '_replace') else GWFM],
        ))
        # Use a low threshold to catch the re-degradation
        from enginewash.models import WashParameter, FlightPhase, TrendDirection
        param = WashParameter("GWFM", FlightPhase.CRUISE, TrendDirection.DOWN, threshold=1.0)
        result = calc.process(flights, maint, param)

        assert len(result.events) == 1
        ev = result.events[0]
        # With values returning to 10.0 and threshold=1, loss should be detected
        assert ev.has_loss
