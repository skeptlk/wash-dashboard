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
# Smoothing curves are split at wash boundaries — the rolling window stops at
# each segment, so connecting them visually would misrepresent the data.
_CURVE_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("raw", "float_value", False),
    ("smooth", "float_value_smooth", True),
    ("smooth_custom", "float_value_smooth_custom", True),
)


def build_wash_plot(
    df: pd.DataFrame, events: list[WashEvent], n_obs_mean: int
) -> WashPlot:
    """Assemble a WashPlot from the processed pipeline DataFrame and events.

    Three curves per engine (raw / smooth / smooth_custom) plus one
    WashEventMarkers bundle per detected wash.
    """
    events_by_engine: dict[str, list[WashEvent]] = {}
    for ev in events:
        events_by_engine.setdefault(ev.engine_id, []).append(ev)

    curves: list[PlotCurve] = []
    markers: list[WashEventMarkers] = []
    for engine_id, eng_df in df.groupby("engine_id"):
        eng_df = eng_df.sort_values("flight_datetime")
        eid = str(engine_id)
        segments = {int(idx): grp for idx, grp in eng_df.groupby("event_cum")}

        for kind, col, split in _CURVE_COLUMNS:
            curves.append(_build_curve(eng_df, col, kind, eid, split))

        for ev in events_by_engine.get(eid, []):
            markers.append(_build_wash_markers(ev, segments, n_obs_mean, eid))

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
    before_segment: PlotSegment | None = None
    before_value_point: PlotPoint | None = None
    if prev_seg is not None and len(prev_seg) and not pd.isna(ev.mean_before):
        tail = prev_seg.iloc[-n_obs:]
        before_segment = PlotSegment(
            start_datetime=tail["flight_datetime"].iloc[0].to_pydatetime(),
            end_datetime=anchor_dt,
            value=float(ev.mean_before),
        )
        match = tail[tail["float_value_smooth_custom"] == ev.mean_before]
        if not match.empty:
            before_value_point = PlotPoint(
                flight_datetime=match["flight_datetime"].iloc[0].to_pydatetime(),
                value=float(ev.mean_before),
            )

    head = curr_seg.iloc[:n_obs]
    after_segment: PlotSegment | None = None
    after_value_point: PlotPoint | None = None
    if len(head) and not pd.isna(ev.mean_after):
        after_segment = PlotSegment(
            start_datetime=anchor_dt,
            end_datetime=head["flight_datetime"].iloc[-1].to_pydatetime(),
            value=float(ev.mean_after),
        )
        match = head[head["float_value_smooth_custom"] == ev.mean_after]
        if not match.empty:
            after_value_point = PlotPoint(
                flight_datetime=match["flight_datetime"].iloc[0].to_pydatetime(),
                value=float(ev.mean_after),
            )

    loss_point: PlotPoint | None = None
    if ev.time_loss_of_efficiency is not None:
        loe_t = pd.Timestamp(ev.time_loss_of_efficiency)
        loe_row = curr_seg[curr_seg["flight_datetime"] == loe_t]
        loe_value: float | None = None
        if not loe_row.empty:
            v = loe_row["float_value_smooth_custom"].iloc[0]
            if pd.notna(v):
                loe_value = float(v)
        loss_point = PlotPoint(
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
        loss_of_efficiency_point=loss_point,
    )
