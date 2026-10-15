"""Constructor trend chart, built exclusively from DuckDB query results."""

import base64

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..data.egt_params import EGTHDM_TAKEOFF_ID, line_with_gaps, plotly_timestamps
from ..data.flight_db import engine_options, read_trends


def build_chart(aircraft_type, engine_id, params, start, end, window=26, path=None):
    if not params:
        return None
    series, events = read_trends(
        aircraft_type, engine_id, params, start, end, window, path
    )
    if not any(not frame.empty for _, frame in series):
        return None
    engine = next(
        (e for e in engine_options(path) if e["key"] == f"{aircraft_type}:{engine_id}"),
        {},
    )
    fig = empty_chart(aircraft_type, engine_id, [entry for entry, _ in series], engine)
    for row, (entry, frame) in enumerate(series, 1):
        add_series(fig, entry, frame, events, row, window)
    update_time_ticks(fig)
    return fig


def empty_chart(aircraft_type, engine_id, entries, engine=None):
    """Reserve all rows before the first parameter arrives."""
    rows = len(entries)
    engine = engine or {}
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        specs=[[{"secondary_y": True}] for _ in entries],
        # Reserve enough room for X labels and the next row's title.
        vertical_spacing=min(0.06, 0.35 / max(1, rows - 1)),
        subplot_titles=[
            f"{e['name']} ({e['phase'].title()}), ESN = {engine_id}, "
            f"Pos = {engine.get('position', '?')}, "
            f"{engine.get('registration', '?')}, {engine.get('aircraft_model', aircraft_type)}"
            for e in entries
        ],
    )
    fig.update_annotations(x=0, xanchor="left", font_size=12, yshift=-2)
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 33, "r": 33, "t": 48, "b": 64},
        font={"family": "Inter, system-ui, sans-serif", "size": 11},
        legend={
            "orientation": "h",
            "x": 1,
            "xanchor": "right",
            "y": 1,
            "yref": "container",
            "yanchor": "top",
        },
        autosize=True,
        dragmode="zoom",
    )
    fig.update_xaxes(
        # The hidden secondary Y axes need no reserved space on the right.
        domain=[0, 1],
        type="date",
        tickformat="%d.%m.%y",
        nticks=14,
        showticklabels=True,
        gridcolor="rgba(128,128,128,0.12)",
        zeroline=False,
    )
    fig.update_yaxes(
        gridcolor="rgba(128,128,128,0.15)", zeroline=False, nticks=5, automargin=True
    )
    fig.update_yaxes(range=[0, 1], fixedrange=True, visible=False, secondary_y=True)
    return fig


def _trace_values(values):
    """Plotly restores persisted NumPy arrays as its binary transport dicts."""
    if isinstance(values, dict) and "bdata" in values:
        return np.frombuffer(base64.b64decode(values["bdata"]), dtype=values["dtype"])
    return values if values is not None else ()


def trace_x_values(trace):
    return _trace_values(trace.x)


def scale_to_smoothed(fig, start="", end=""):
    """Fit each primary Y axis to finite, visible trend values with 30% padding."""
    values_by_axis = {}
    for trace in fig.data:
        if trace.legendgroup != "smooth":
            continue
        xs = np.asarray(trace_x_values(trace), dtype=float)
        ys = np.asarray(_trace_values(trace.y), dtype=float)
        visible = np.isfinite(xs) & np.isfinite(ys)
        if start:
            visible &= xs >= pd.Timestamp(start).value / 1e6
        if end:
            visible &= xs <= pd.Timestamp(end).value / 1e6
        if visible.any():
            axis = "yaxis" + (trace.yaxis or "y")[1:]
            values_by_axis.setdefault(axis, []).append(ys[visible])
    for axis, parts in values_by_axis.items():
        values = np.concatenate(parts)
        lo, hi = float(values.min()), float(values.max())
        padding = (hi - lo) * 0.3 if hi > lo else max(abs(lo) * 0.05, 0.1)
        fig.layout[axis].update(range=[lo - padding, hi + padding], autorange=False)


def update_time_ticks(fig, start="", end=""):
    """Show twelve dates across the visible readings, including the last point."""
    series = [(trace.name, trace_x_values(trace)) for trace in fig.data]
    bounds = [
        (np.min(xs), np.max(xs)) for name, xs in series if name == "Raw" and len(xs)
    ]
    if not bounds:
        return
    # Keep autorange/reset behavior, with only 1% breathing room at each end.
    # Include event markers as well as readings so neither gets clipped.
    data_lo = pd.to_datetime(min(np.nanmin(xs) for _, xs in series if len(xs)), unit="ms")
    data_hi = pd.to_datetime(max(np.nanmax(xs) for _, xs in series if len(xs)), unit="ms")
    padding = max((data_hi - data_lo) * 0.01, pd.Timedelta(minutes=1))
    fig.update_xaxes(
        autorangeoptions={
            "clipmin": (data_lo - padding).isoformat(),
            "clipmax": (data_hi + padding).isoformat(),
        },
    )
    # Include any visible event before the readings, ending at the last reading.
    lo = data_lo
    hi = pd.to_datetime(max(b[1] for b in bounds), unit="ms")
    if start:
        lo = max(lo, pd.Timestamp(start))
        hi = min(hi, pd.Timestamp(end))
    if lo > hi:
        fig.update_xaxes(tickmode="auto", tickvals=None)
        return
    # Avoid repeating day labels on short ranges; zoomed views include the time.
    span = hi - lo
    frequency = "%d.%m.%y" if span >= pd.Timedelta(days=11) else "%d.%m %H:%M"
    if span < pd.Timedelta(minutes=11):
        frequency = "%H:%M:%S"
    ticks = pd.date_range(lo, hi, periods=12) if lo < hi else [lo]
    fig.update_xaxes(
        tickmode="array",
        tickvals=[dt.isoformat() for dt in ticks],
        tickformat=frequency,
    )


def add_series(fig, entry, frame, events, row, window):
    """Append one parameter to its reserved row without rebuilding previous rows."""
    xs = frame.flight_datetime.tolist()
    hover = f"%{{x|%d.%m.%y, %H:%M:%S}}<br>{entry['name']}: %{{y:.2f}}<extra></extra>"
    fig.add_trace(
        go.Scattergl(
            x=plotly_timestamps(xs),
            y=frame.value.to_numpy(dtype=float),
            mode="markers",
            name="Raw",
            legendgroup="raw",
            showlegend=row == 1,
            marker={"size": 4, "color": "#3b82f6", "opacity": 0.4},
            hovertemplate=hover,
        ),
        row=row,
        col=1,
    )
    line_x, line_y, gaps = line_with_gaps(
        xs, frame.smoothed.tolist(), gap_days=30, include_threshold=False
    )
    fig.add_trace(
        go.Scatter(
            x=plotly_timestamps(line_x),
            y=np.asarray(line_y, dtype=float),
            mode="lines",
            name=f"Smoothed (window={window})",
            legendgroup="smooth",
            showlegend=row == 1,
            connectgaps=False,
            line={"color": "#3b82f6", "width": 1.5},
            hovertemplate=hover,
        ),
        row=row,
        col=1,
    )
    axes = fig.get_subplot(row, 1)
    xref = axes.xaxis.plotly_name.replace("axis", "")
    yref = axes.yaxis.plotly_name.replace("axis", "") + " domain"
    shapes, annotations = [], []
    for lo, hi in gaps:
        shapes.append(
            dict(
                type="rect",
                x0=lo,
                x1=hi,
                xref=xref,
                y0=0,
                y1=1,
                yref=yref,
                fillcolor="rgba(128,128,128,0.05)",
                line={"width": 0},
                layer="below",
            )
        )
        annotations.append(
            dict(
                text="No data",
                x=(lo + (hi - lo) / 2).isoformat(),
                xref=xref,
                y=0.5,
                yref=yref,
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                font={"size": 9, "color": "#888"},
                textangle=-90,
            )
        )
    for kind, color, symbol, y in [
        ("Install", "#2ca02c", "triangle-up", 0.96),
        ("Removal", "#d62728", "triangle-down", 0.83),
    ]:
        points = [
            (dt, reason) for dt, event_kind, reason in events if event_kind == kind
        ]
        fig.add_trace(
            go.Scatter(
                x=plotly_timestamps([dt for dt, _ in points]),
                y=[y] * len(points),
                customdata=[
                    f"{kind} ({reason})" if reason else kind for _, reason in points
                ],
                name=kind,
                legendgroup=kind,
                showlegend=row == 1,
                mode="markers",
                marker={"color": color, "symbol": symbol, "size": 7},
                hovertemplate="%{customdata}<br>%{x|%d.%m.%y, %H:%M}<extra></extra>",
            ),
            row=row,
            col=1,
            secondary_y=True,
        )
        for dt, _ in points:
            shapes.append(
                dict(
                    type="line",
                    x0=dt,
                    x1=dt,
                    y0=0,
                    y1=1,
                    xref=xref,
                    yref=yref,
                    line={"color": color, "width": 1, "dash": "dot"},
                    opacity=0.4,
                    layer="below",
                )
            )
    # Assign once: add_vrect/add_shape revalidate the growing layout each time.
    fig.layout.shapes = (*fig.layout.shapes, *shapes)
    fig.layout.annotations = (*fig.layout.annotations, *annotations)


def copy_series(fig, source, row):
    """Place a cached parameter row into a new subplot layout."""
    for trace in source.data:
        copied = trace.to_plotly_json()
        copied["showlegend"] = row == 1 or trace.legendgroup == "egt_prediction"
        fig.add_trace(copied, row=row, col=1, secondary_y=trace.yaxis == "y2")
    axes = fig.get_subplot(row, 1)
    xref = axes.xaxis.plotly_name.replace("axis", "")
    yref = axes.yaxis.plotly_name.replace("axis", "") + " domain"
    fig.layout.shapes = (
        *fig.layout.shapes,
        *(
            dict(shape.to_plotly_json(), xref=xref, yref=yref)
            for shape in source.layout.shapes
        ),
    )
    annotations = []
    for annotation in source.layout.annotations:
        if annotation.xref != "paper":
            annotations.append(dict(annotation.to_plotly_json(), xref=xref, yref=yref))
    fig.layout.annotations = (*fig.layout.annotations, *annotations)
    fig.update_yaxes(
        range=source.layout.yaxis.range,
        autorange=source.layout.yaxis.autorange,
        row=row,
        col=1,
        secondary_y=False,
    )


def add_predictions(fig, entry, predictions):
    """Show predictions only on the takeoff EGTHDM parameter row."""
    if entry["id"] != EGTHDM_TAKEOFF_ID or not predictions:
        return
    xs, values = zip(*predictions)
    fig.add_trace(
        go.Scatter(
            x=plotly_timestamps(xs),
            y=np.asarray(values, dtype=float),
            customdata=np.asarray(values, dtype=float),
            mode="markers",
            name="EGT Indication",
            legendgroup="egt_prediction",
            marker={"symbol": "x", "size": 7, "color": "red"},
            hovertemplate="%{x|%d.%m.%y, %H:%M:%S}<br>Predicted failure (EGTHDM): %{customdata:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
