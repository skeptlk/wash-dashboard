"""Build chart-ready WashPlot from processed pipeline output."""

from __future__ import annotations

import pandas as pd

from .models import (
    PlotCurve,
    PlotPoint,
    PlotSegment,
    WashEvent,
    WashEventMarkers,
    WashPlot,
)


# (kind, source column, split_at_segments)
_CURVE_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("raw", "float_value", False),
    ("smooth", "float_value_smooth", True),
    ("smooth_custom", "float_value_smooth_custom", True),
)


def build_wash_plot(
    engine_dfs: list[tuple[str, pd.DataFrame]],
    events: list[WashEvent],
    n_obs_mean: int,
) -> WashPlot:
    """Assemble a WashPlot from per-engine processed DataFrames and events.

    Segmented plot curves per engine (raw, smooth, smooth_custom) plus
    WashEventMarkers list for each wash event.
    """
    events_by_engine: dict[str, list[WashEvent]] = {}
    for event in events:
        events_by_engine.setdefault(event.engine_id, []).append(event)

    curves: list[PlotCurve] = []
    markers: list[WashEventMarkers] = []
    for engine_id, eng_df in engine_dfs:
        segments = {int(idx): grp for idx, grp in eng_df.groupby("event_cum")}

        for kind, col, split in _CURVE_COLUMNS:
            curves.append(_build_curve(eng_df, col, kind, engine_id, split))

        for event in events_by_engine.get(engine_id, []):
            markers.append(_build_wash_markers(event, segments, n_obs_mean, engine_id))

    return WashPlot(curves=tuple(curves), markers=tuple(markers))


def _build_curve(
    eng_df: pd.DataFrame,
    value_col: str,
    kind: str,
    engine_id: str,
    split_at_segments: bool,
) -> PlotCurve:
    cols = ["flight_datetime", value_col]
    if split_at_segments:
        cols.append("event_cum")
    sub = eng_df[cols].dropna(subset=[value_col])

    points: list[PlotPoint] = []
    prev_seg: int | None = None
    if split_at_segments:
        for dt, v, seg in zip(sub["flight_datetime"], sub[value_col], sub["event_cum"]):
            if prev_seg is not None and seg != prev_seg:
                points.append(PlotPoint(flight_datetime=dt.to_pydatetime(), value=None))
            points.append(PlotPoint(flight_datetime=dt.to_pydatetime(), value=float(v)))
            prev_seg = seg
    else:
        for dt, v in zip(sub["flight_datetime"], sub[value_col]):
            points.append(PlotPoint(flight_datetime=dt.to_pydatetime(), value=float(v)))
    return PlotCurve(kind=kind, engine_id=engine_id, points=tuple(points))


def _build_wash_markers(
    ev: WashEvent,
    segments: dict[int, pd.DataFrame],
    n_obs: int,
    engine_id: str,
) -> WashEventMarkers:
    curr_seg = segments[ev.event_index]
    wash_row = curr_seg.iloc[0]
    anchor_dt = wash_row["flight_datetime"].to_pydatetime()
    anchor_value_raw = wash_row["float_value_smooth_custom"]
    anchor_value = float(anchor_value_raw) if pd.notna(anchor_value_raw) else None
    wash_event_point = PlotPoint(flight_datetime=anchor_dt, value=anchor_value)

    prev_seg = segments.get(ev.event_index - 1)
    before_window = prev_seg.iloc[-n_obs:] if prev_seg is not None else None
    before_segment, before_value_point = _build_marker_segment(
        before_window, ev.mean_before, anchor_dt, is_before=True
    )

    after_window = curr_seg.iloc[:n_obs]
    after_segment, after_value_point = _build_marker_segment(
        after_window, ev.mean_after, anchor_dt, is_before=False
    )

    loe_point: PlotPoint | None = None
    if ev.time_loss_of_efficiency is not None:
        loe_t = pd.Timestamp(ev.time_loss_of_efficiency)
        loe_row = curr_seg[curr_seg["flight_datetime"] == loe_t]
        loe_value: float | None = None
        if not loe_row.empty:
            v = loe_row["float_value_smooth_custom"].iloc[0]
            if pd.notna(v):
                loe_value = float(v)
        loe_point = PlotPoint(
            flight_datetime=loe_t.to_pydatetime(), value=loe_value
        )

    return WashEventMarkers(
        engine_id=engine_id,
        event_index=ev.event_index,
        wash_event_point=wash_event_point,
        before_segment=before_segment,
        after_segment=after_segment,
        before_value_point=before_value_point,
        after_value_point=after_value_point,
        loss_of_efficiency_point=loe_point,
    )


def _build_marker_segment(
    window: pd.DataFrame | None,
    mean_value: float,
    anchor_dt,
    is_before: bool,
) -> tuple[PlotSegment | None, PlotPoint | None]:
    """Build the reference segment + extremum-flight marker for one side of a wash."""
    if window is None or window.empty or pd.isna(mean_value):
        return None, None

    window_start = window["flight_datetime"].iloc[0].to_pydatetime()
    window_end = window["flight_datetime"].iloc[-1].to_pydatetime()
    if is_before:
        segment = PlotSegment(start_datetime=window_start, end_datetime=anchor_dt, value=float(mean_value))
    else:
        segment = PlotSegment(start_datetime=anchor_dt, end_datetime=window_end, value=float(mean_value))

    match = window[window["float_value_smooth_custom"] == mean_value]
    value_point = None
    if not match.empty:
        value_point = PlotPoint(
            flight_datetime=match["flight_datetime"].iloc[0].to_pydatetime(),
            value=float(mean_value),
        )
    return segment, value_point
