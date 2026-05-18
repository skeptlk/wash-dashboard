"""Tests for WashCalculator.build_plot()."""

from datetime import datetime

import numpy as np
import pandas as pd

from enginewash import (
    GWFM,
    FlightPhase,
    FlightRecord,
    MaintenanceRecord,
    PlotCurve,
    PlotPoint,
    PlotSegment,
    WashCalculator,
    WashConfig,
    WashEventMarkers,
    WashPlot,
)


def _flights(engine_id: str, values: np.ndarray, start: str = "2024-01-01") -> list[FlightRecord]:
    dates = pd.date_range(start, periods=len(values), freq="D")
    return [
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


class TestBuildPlot:
    def test_single_engine_single_wash_shape(self):
        pre = np.linspace(5.0, 7.0, 50)
        post = np.linspace(4.0, 6.0, 50)
        flights = _flights("ENG001", np.concatenate([pre, post]))
        maint = [MaintenanceRecord("ENG001", datetime(2024, 2, 20), "206")]

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        plot = calc.build_plot(flights, maint, GWFM)

        assert isinstance(plot, WashPlot)

        assert len(plot.curves) == 3
        kinds = {(c.kind, c.engine_id) for c in plot.curves}
        assert kinds == {
            ("raw", "ENG001"),
            ("smooth", "ENG001"),
            ("smooth_custom", "ENG001"),
        }

        for curve in plot.curves:
            assert isinstance(curve, PlotCurve)
            assert all(isinstance(p, PlotPoint) for p in curve.points)

        raw = next(c for c in plot.curves if c.kind == "raw")
        assert len(raw.points) == 100
        assert raw.points[0].value == 5.0
        assert raw.points[49].value == 7.0

        # Smoothing curves are split at the wash boundary — one None-valued
        # break point per wash; data points still total 100.
        for kind in ("smooth", "smooth_custom"):
            curve = next(c for c in plot.curves if c.kind == kind)
            none_count = sum(1 for p in curve.points if p.value is None)
            assert none_count == 1
            assert len(curve.points) == 101

    def test_wash_markers_populated(self):
        pre = np.linspace(5.0, 7.0, 50)
        post = np.linspace(4.0, 6.0, 50)
        flights = _flights("ENG001", np.concatenate([pre, post]))
        maint = [MaintenanceRecord("ENG001", datetime(2024, 2, 20), "206")]

        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        plot = calc.build_plot(flights, maint, GWFM)

        assert len(plot.markers) == 1
        m = plot.markers[0]
        assert isinstance(m, WashEventMarkers)
        assert m.engine_id == "ENG001"
        assert m.event_index == 1

        assert isinstance(m.wash_event_point, PlotPoint)
        assert m.wash_event_point.flight_datetime >= datetime(2024, 2, 20)

        assert isinstance(m.before_segment, PlotSegment)
        assert m.before_segment.start_datetime < m.before_segment.end_datetime
        assert m.before_segment.end_datetime == m.wash_event_point.flight_datetime

        assert isinstance(m.after_segment, PlotSegment)
        assert m.after_segment.start_datetime == m.wash_event_point.flight_datetime
        assert m.after_segment.start_datetime < m.after_segment.end_datetime

        # Down-trend parameter: post-wash mean should be lower than pre-wash mean
        assert m.after_segment.value < m.before_segment.value

        # Value points: actual flight where each extremum was observed.
        assert isinstance(m.before_value_point, PlotPoint)
        assert m.before_value_point.value == m.before_segment.value
        assert (
            m.before_segment.start_datetime
            <= m.before_value_point.flight_datetime
            <= m.before_segment.end_datetime
        )

        assert isinstance(m.after_value_point, PlotPoint)
        assert m.after_value_point.value == m.after_segment.value
        assert (
            m.after_segment.start_datetime
            <= m.after_value_point.flight_datetime
            <= m.after_segment.end_datetime
        )

    def test_loss_of_efficiency_point_when_detected(self):
        pre = np.linspace(7.0, 7.0, 30)
        dip = np.linspace(4.0, 4.0, 10)
        recover = np.linspace(7.0, 7.0, 60)
        flights = _flights("ENG001", np.concatenate([pre, dip, recover]))
        maint = [MaintenanceRecord("ENG001", datetime(2024, 1, 31), "206")]

        calc = WashCalculator(WashConfig(smooth_window=3, n_obs_mean=3))
        plot = calc.build_plot(flights, maint, GWFM)
        m = plot.markers[0]

        assert m.loss_of_efficiency_point is not None
        assert isinstance(m.loss_of_efficiency_point, PlotPoint)
        assert m.loss_of_efficiency_point.flight_datetime > m.wash_event_point.flight_datetime

    def test_no_wash_returns_empty_markers(self):
        flights = _flights("ENG001", np.linspace(5.0, 6.0, 50))
        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        plot = calc.build_plot(flights, [], GWFM)

        assert plot.markers == ()
        assert len(plot.curves) == 3
        # No washes → no segment breaks; every curve is contiguous.
        for curve in plot.curves:
            assert len(curve.points) == 50
            assert all(p.value is not None for p in curve.points)

    def test_multi_engine_curves_per_engine(self):
        f1 = _flights("ENG001", np.linspace(5.0, 7.0, 50))
        f2 = _flights("ENG002", np.linspace(4.0, 6.0, 50))
        calc = WashCalculator(WashConfig(smooth_window=5, n_obs_mean=5))
        plot = calc.build_plot(f1 + f2, [], GWFM)

        assert len(plot.curves) == 6
        engines_with_raw = {c.engine_id for c in plot.curves if c.kind == "raw"}
        assert engines_with_raw == {"ENG001", "ENG002"}

