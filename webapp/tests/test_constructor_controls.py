"""Date shortcuts and trend-only scaling, independent of the live database."""

import asyncio
from datetime import date
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from webapp.components.constructor_fig import add_series, empty_chart
from webapp.state.constructor import ConstructorState


@pytest.mark.parametrize("persisted", [False, True])
def test_scale_to_trend_ignores_outliers_and_respects_viewport(persisted):
    entries = [
        {"id": "GWFM@CRUISE", "name": "GWFM", "phase": "CRUISE"},
        {"id": "DEGT@CRUISE", "name": "DEGT", "phase": "CRUISE"},
        {"id": "EMPTY@CRUISE", "name": "EMPTY", "phase": "CRUISE"},
    ]
    fig = empty_chart("A320", "573444", entries)
    for row, smoothed in enumerate(
        [[100, -6, -5, np.nan], [1000, 20, 20, np.nan], [1, np.nan, np.nan, 2]], 1
    ):
        frame = pd.DataFrame({
            "flight_datetime": pd.date_range("2026-10-01", periods=4),
            "value": [-40, -6, -5, -20],
            "smoothed": smoothed,
        })
        add_series(fig, entries[row - 1], frame, [], row, 26)
    fig.layout.yaxis5.range = [-50, 50]
    if persisted:
        fig = go.Figure(json.loads(fig.to_json()))
    state = ConstructorState(_reflex_internal_init=True)
    state._chart_figure = fig
    state.has_chart = True
    state.timeline_start, state.timeline_end = "2026-10-02", "2026-10-03"
    state._apply_timeline()
    before = state._chart_figure.to_json()
    state.scale_to_trend()
    assert state.chart_figure.layout.yaxis.range == pytest.approx((-6.3, -4.7))
    assert state.chart_figure.layout.yaxis3.range == (19, 21)
    # Empty visible trend leaves its previous bounds; event axes stay fixed.
    assert state.chart_figure.layout.yaxis5.range == (-50, 50)
    assert state.chart_figure.layout.yaxis2.range == (0, 1)
    assert state.chart_figure.layout.xaxis.range == ("2026-10-02", "2026-10-03")
    assert not state.chart_figure.data
    assert state.chart_offset == len(fig.data)
    assert json.loads(state._chart_figure.to_json())["data"] == json.loads(before)["data"]
    # Plotly's regular autoscale still restores the full raw-data range.
    state.on_plot_relayout({"yaxis.autorange": True})
    assert state._chart_figure.layout.yaxis.range is None
    assert state._chart_figure.layout.yaxis.autorange


@pytest.mark.parametrize(
    "today,preset,start,end",
    [
        (date(2026, 10, 15), "All", "", ""),
        (date(2026, 10, 15), "1y", "2025-10-15", "2026-10-15"),
        (date(2026, 10, 15), "3mo", "2026-07-15", "2026-10-15"),
        (date(2026, 10, 15), "30d", "2026-09-15", "2026-10-15"),
        (date(2024, 2, 29), "1y", "2023-02-28", "2024-02-29"),
        (date(2026, 5, 31), "3mo", "2026-02-28", "2026-05-31"),
    ],
)
def test_date_presets_reset_zoom_and_support_calendar_boundaries(
    monkeypatch, today, preset, start, end
):
    class Today(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr("webapp.state.constructor.date", Today)
    state = ConstructorState(_reflex_internal_init=True)
    state.timeline_start, state.timeline_end = "2025-01-01", "2025-01-02"

    async def run():
        return [event async for event in state.set_date_preset(preset)]

    asyncio.run(run())
    assert (state.start_date, state.end_date) == (start, end)
    assert state.timeline_start == state.timeline_end == ""
    assert state.date_preset == preset
