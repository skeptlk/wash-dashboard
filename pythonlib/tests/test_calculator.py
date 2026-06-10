"""Tests for the WashCalculator end-to-end pipeline."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from enginewash import (
    EGTHDM,
    GWFM,
    FlightPhase,
    FlightRecord,
    MaintenanceRecord,
    UtilizationRecord,
    WashCalculator,
    WashConfig,
)


def make_flights(
    engine_id: str,
    n: int,
    base_values: list[float],
    parameter_name: str = "GWFM",
    flight_phase: FlightPhase = FlightPhase.CRUISE,
) -> list[FlightRecord]:
    """Generate synthetic flight data."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    values = np.interp(np.arange(n), np.linspace(0, n - 1, len(base_values)), base_values)
    return [
        FlightRecord(
            engine_id=engine_id,
            flight_datetime=dt.to_pydatetime(),
            parameter_name=parameter_name,
            flight_phase=flight_phase,
            float_value=float(v),
            float_value_smooth=float(v),
        )
        for dt, v in zip(dates, values)
    ]


def make_maintenance(engine_id: str, dates: list[str], ata_codes: list[str]) -> list[MaintenanceRecord]:
    return [
        MaintenanceRecord(engine_id=engine_id, maint_datetime=datetime.fromisoformat(dt), ata_code=ata)
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
            FlightRecord(
                engine_id="ENG001", flight_datetime=dt.to_pydatetime(),
                parameter_name="GWFM", flight_phase=FlightPhase.CRUISE,
                float_value=float(v), float_value_smooth=float(v),
            )
            for dt, v in zip(dates, values)
        ]
        # Wash happens between day 50 and 51
        maint = make_maintenance("ENG001", ["2024-02-20"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        summaries = calc.process(flights, maint, GWFM)

        assert len(summaries) == 1
        ev = summaries[0].results[0]
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
            FlightRecord(
                engine_id="ENG002", flight_datetime=dt.to_pydatetime(),
                parameter_name="EGTHDM", flight_phase=FlightPhase.TAKEOFF,
                float_value=float(v), float_value_smooth=float(v),
            )
            for dt, v in zip(dates, values)
        ]
        maint = make_maintenance("ENG002", ["2024-02-20"], ["207"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        summaries = calc.process(flights, maint, EGTHDM)

        assert len(summaries) == 1
        ev = summaries[0].results[0]
        assert ev.delta > 0

    def test_no_maintenance_events(self):
        """No washes → no events, empty summaries."""
        flights = make_flights("ENG003", 50, [10.0, 10.0])
        maint: list[MaintenanceRecord] = []

        calc = WashCalculator()
        summaries = calc.process(flights, maint, GWFM)

        assert summaries == []

    def test_multiple_engines(self):
        """Each engine processed independently."""
        flights = make_flights("ENG_A", 60, [5.0, 7.0, 4.0, 6.0]) + make_flights("ENG_B", 60, [10.0, 12.0, 8.0, 11.0])

        maint = (
            make_maintenance("ENG_A", ["2024-02-01"], ["206"]) +
            make_maintenance("ENG_B", ["2024-02-15"], ["209"])
        )

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        summaries = calc.process(flights, maint, GWFM)

        engine_ids = {s.engine_id for s in summaries}
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
        summaries = calc.process(flights, maint, GWFM)

        assert len(summaries) == 2
        assert summaries[0].event_index == 1
        assert summaries[1].event_index == 2

    def test_summary_structure(self):
        """Summaries contain expected fields and nested WashEvent results."""
        flights = make_flights("ENG005", 80, [5.0, 7.0, 4.0, 6.0])
        maint = make_maintenance("ENG005", ["2024-02-15"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        summaries = calc.process(flights, maint, GWFM)

        assert len(summaries) == 1
        s = summaries[0]
        assert s.engine_id == "ENG005"
        assert s.event_index == 1
        assert s.ata_code == "206"
        assert s.maint_datetime is not None
        assert len(s.results) == 1
        assert s.results[0].parameter == GWFM

    def test_process_all_groups_parameters(self):
        """process_all filters flights by parameter_name/flight_phase and groups into summaries."""
        gwfm_flights = make_flights(
            "ENG006", 80, [5.0, 7.0, 4.0, 6.0],
            parameter_name="GWFM", flight_phase=FlightPhase.CRUISE,
        )
        egthdm_flights = make_flights(
            "ENG006", 80, [20.0, 12.0, 18.0, 14.0],
            parameter_name="EGTHDM", flight_phase=FlightPhase.TAKEOFF,
        )
        flights = gwfm_flights + egthdm_flights
        maint = make_maintenance("ENG006", ["2024-02-15"], ["206"])

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        summaries = calc.process_all(flights, maint, parameters=[GWFM, EGTHDM])

        assert len(summaries) == 1
        s = summaries[0]
        param_names = {r.parameter.name for r in s.results}
        assert "GWFM" in param_names
        assert "EGTHDM" in param_names

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
        summaries = calc.process(flights, maint, param)

        assert len(summaries) == 1
        ev = summaries[0].results[0]
        # With values returning to 10.0 and threshold=1, loss should be detected
        assert ev.has_loss


def _loe_param(threshold: float = 1.0):
    """Low-threshold GWFM variant used to force LoE detection in the fixtures below."""
    from enginewash.models import FlightPhase, TrendDirection, WashParameter
    return WashParameter("GWFM", FlightPhase.CRUISE, TrendDirection.DOWN, threshold=threshold)


def _make_loe_fixture(engine_id: str = "ENGU01"):
    """Build flights+maintenance that reliably produce a detected LoE several days after the wash.

    100 daily flights from 2024-01-01. Pre-wash (flights 0..59) is stable at 10.0.
    Wash is anchored to 2024-03-01 (flight 60). Post-wash (flights 60..99) starts
    at 5.0, holds for 20 days, then ramps back up to 10.0 — so with threshold=1.0
    on a DOWN parameter (max(pre) - threshold = 9), LoE lands near the end of the
    post-wash segment.
    """
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    pre = np.full(60, 10.0)
    post_flat = np.full(20, 5.0)
    post_ramp = np.linspace(5.0, 10.0, 20)
    values = np.concatenate([pre, post_flat, post_ramp])

    flights = [
        FlightRecord(
            engine_id=engine_id,
            flight_datetime=dt.to_pydatetime(),
            parameter_name="GWFM",
            flight_phase=FlightPhase.CRUISE,
            float_value=float(v),
            float_value_smooth=float(v),
        )
        for dt, v in zip(dates, values)
    ]
    maint = make_maintenance(engine_id, ["2024-03-01"], ["206"])
    return flights, maint


def _linear_utilization(
    engine_id: str,
    start: datetime,
    n_days: int,
    cycles_per_day: int,
    hours_per_day: float,
    cycles_base: int = 1000,
    hours_base: float = 2000.0,
) -> list[UtilizationRecord]:
    """One record per day with linearly growing cumulative cycles/hours.

    Day i: total_cycles = cycles_base + cycles_per_day * i,
           total_hours  = hours_base  + hours_per_day  * i.
    """
    return [
        UtilizationRecord(
            engine_id=engine_id,
            total_cycles=cycles_base + cycles_per_day * i,
            total_hours=hours_base + hours_per_day * i,
            departure_datetime=start + pd.Timedelta(days=i, hours=-2),
            arrival_datetime=start + pd.Timedelta(days=i),
        )
        for i in range(n_days)
    ]


class TestUtilizationIntegration:
    def test_populates_cycles_and_hours_loss_of_efficiency(self):
        """With utilization records covering wash and LoE dates, fields equal the slope-scaled day delta."""
        engine_id = "ENGU01"
        flights, maint = _make_loe_fixture(engine_id)
        utilization = _linear_utilization(
            engine_id,
            start=datetime(2024, 1, 1),
            n_days=100,
            cycles_per_day=5,
            hours_per_day=10.0,
        )

        calc = WashCalculator(WashConfig(smooth_window=3, n_obs_mean=3))
        summaries = calc.process(flights, maint, _loe_param(), utilizations=utilization)

        assert len(summaries) == 1
        ev = summaries[0].results[0]
        assert ev.has_loss
        assert ev.maint_datetime is not None

        days_diff = (ev.time_loss_of_efficiency.date() - ev.maint_datetime.date()).days
        assert ev.cycles_loss_of_efficiency == 5 * days_diff
        assert ev.hours_loss_of_efficiency == int(round(10.0 * days_diff))
        assert ev.cycles_loss_of_efficiency > 0
        assert ev.hours_loss_of_efficiency > 0
        assert ev.maint_datetime.date() >= date(2024, 3, 1)

    def test_no_utilization_leaves_fields_none(self):
        """Calling process() without utilization keeps cycles/hours_loss_of_efficiency as None."""
        engine_id = "ENGU02"
        flights, maint = _make_loe_fixture(engine_id)

        calc = WashCalculator(WashConfig(smooth_window=3, n_obs_mean=3))
        summaries = calc.process(flights, maint, _loe_param())

        assert len(summaries) == 1
        ev = summaries[0].results[0]
        assert ev.has_loss  # LoE still detected
        assert ev.cycles_loss_of_efficiency is None
        assert ev.hours_loss_of_efficiency is None

    def test_utilization_missing_dates_leaves_fields_none(self):
        """If utilization records exist but not for the wash/LoE date, fields are None (R left_join NA)."""
        engine_id = "ENGU03"
        flights, maint = _make_loe_fixture(engine_id)
        # Records only for an unrelated date range
        utilization = _linear_utilization(
            engine_id,
            start=datetime(2023, 1, 1),
            n_days=10,
            cycles_per_day=5,
            hours_per_day=10.0,
        )

        calc = WashCalculator(WashConfig(smooth_window=3, n_obs_mean=3))
        summaries = calc.process(flights, maint, _loe_param(), utilizations=utilization)

        ev = summaries[0].results[0]
        assert ev.cycles_loss_of_efficiency is None
        assert ev.hours_loss_of_efficiency is None

    def test_process_all_threads_utilization(self):
        """process_all forwards utilization to each per-parameter pass."""
        engine_id = "ENGU04"
        flights, maint = _make_loe_fixture(engine_id)
        utilization = _linear_utilization(
            engine_id,
            start=datetime(2024, 1, 1),
            n_days=100,
            cycles_per_day=5,
            hours_per_day=10.0,
        )

        calc = WashCalculator(WashConfig(smooth_window=3, n_obs_mean=3))
        summaries = calc.process_all(
            flights, maint, parameters=[_loe_param()], utilizations=utilization,
        )

        assert len(summaries) == 1
        results = summaries[0].results
        assert any(r.cycles_loss_of_efficiency is not None for r in results)
        assert any(r.hours_loss_of_efficiency is not None for r in results)
