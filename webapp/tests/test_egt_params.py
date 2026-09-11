"""Regression coverage for the curve shown under EGT model predictions."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from enginewash import FlightPhase, FlightRecord, predict_egt_failure_enhanced

# Load the pure parameter helper without starting the network-backed data loader.
_spec = importlib.util.spec_from_file_location(
    "egt_params", Path(__file__).resolve().parents[1] / "webapp/data/egt_params.py"
)
egt_params = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(egt_params)


@pytest.mark.parametrize("window", [3, 26, 40])
@pytest.mark.parametrize("clipped", [False, True])
def test_prediction_points_match_displayed_curve(window, clipped):
    values = [50.0] * 25 + [50.0 - 2 * i for i in range(20)] + [45.0] * 25
    times = pd.date_range("2025-01-01 02:13:17", periods=len(values), freq="6h")
    bundle = SimpleNamespace(takeoff_df=pd.DataFrame({
        "engine_id": "E1", "flight_datetime": times, "egthdm": values,
    }).iloc[::-1])  # Source rows need not be ordered.
    entry = {"df_attr": "takeoff_df", "column": "egthdm"}
    start, end = (times[30], times[55]) if clipped else (None, None)
    xs, ys, curve = egt_params.smoothed_series_for(
        bundle, "E1", entry, window, start, end,
    )
    records = [
        FlightRecord("E1", t, "EGTHDM", FlightPhase.TAKEOFF, y)
        for t, y in zip(times, values)
    ]
    predictions = predict_egt_failure_enhanced(
        "E1", records, [], smoothing_window=window,
        lookback_cycles=3, egthdm_threshold=1.0,
    )
    displayed = dict(zip(xs, curve))
    visible_predictions = [(t, y) for t, y in predictions if t in displayed]
    assert visible_predictions
    for t, y in visible_predictions:
        assert displayed[t] == pytest.approx(y, abs=1e-12)

    assert ys == [values[times.get_loc(t)] for t in xs]
    if clipped:
        full_xs, _, full_curve = egt_params.smoothed_series_for(bundle, "E1", entry, window)
        full = dict(zip(full_xs, full_curve))
        assert xs[0] == start
        assert xs[-1] == end
        assert curve == [full[t] for t in xs]


def test_smoothing_uses_only_past_flights_and_handles_empty_range():
    times = pd.date_range("2025-01-01", periods=4, freq="D")
    bundle = SimpleNamespace(takeoff_df=pd.DataFrame({
        "engine_id": "E1", "flight_datetime": times, "egthdm": [10, 20, 30, 1000],
    }))
    entry = {"df_attr": "takeoff_df", "column": "egthdm"}
    _, _, curve = egt_params.smoothed_series_for(bundle, "E1", entry, 3, end=times[2])
    assert curve == [10, 15, 20]
    assert egt_params.smoothed_series_for(bundle, "missing", entry, 3) == ([], [], [])
    assert egt_params.smoothed_series_for(
        bundle, "E1", entry, 3, start=times[-1] + pd.Timedelta(days=1)
    ) == ([], [], [])


def test_line_breaks_at_week_long_gaps_without_changing_observations():
    times = list(pd.to_datetime([
        "2025-01-01", "2025-01-07 23:59:59", "2025-01-14 23:59:59",
        "2025-04-01", "2025-04-02",
    ], format="mixed"))
    values = [1, 2, 3, 4, 5]
    line_x, line_y, gaps = egt_params.line_with_gaps(times, values)
    assert gaps == [(times[1], times[2]), (times[2], times[3])]
    assert line_x == [times[0], times[1], None, times[2], None, times[3], times[4]]
    assert line_y == [1, 2, None, 3, None, 4, 5]
    assert times[2] == pd.Timestamp("2025-01-14 23:59:59")
    assert values == [1, 2, 3, 4, 5]
    assert egt_params.line_with_gaps([], []) == ([], [], [])
