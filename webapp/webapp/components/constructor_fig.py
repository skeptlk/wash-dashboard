"""Constructor trend chart, built exclusively from DuckDB query results."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..data.egt_params import line_with_gaps, plotly_timestamps
from ..data.flight_db import read_trends


def build_chart(aircraft_type, engine_id, params, start, end, window=26, path=None):
    if not params:
        return None
    series, events = read_trends(
        aircraft_type, engine_id, params, start, end, window, path
    )
    if not any(not frame.empty for _, frame in series):
        return None
    fig = empty_chart(aircraft_type, engine_id, [entry for entry, _ in series])
    for row, (entry, frame) in enumerate(series, 1):
        add_series(fig, entry, frame, events, row, window)
    return fig


def empty_chart(aircraft_type, engine_id, entries):
    """Reserve all rows before the first parameter arrives."""
    rows = len(entries)
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        specs=[[{"secondary_y": True}] for _ in entries],
        vertical_spacing=min(0.085, 0.7 / max(1, rows - 1)),
        subplot_titles=[f"{e['name']} ({e['phase'].title()})" for e in entries],
    )
    fig.update_annotations(x=0, xanchor="left", font_size=12, yshift=3)
    fig.update_layout(
        template="plotly_white",
        title={"text": f"{engine_id} · {aircraft_type}", "font": {"size": 15}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 66, "r": 16, "t": 70, "b": 38},
        font={"family": "Inter, system-ui, sans-serif", "size": 11},
        legend={
            "orientation": "h",
            "x": 1,
            "xanchor": "right",
            "y": 1,
            "yanchor": "bottom",
        },
        autosize=True,
        dragmode="zoom",
    )
    fig.update_xaxes(
        type="date",
        tickformat="%d.%m.%y",
        showticklabels=True,
        gridcolor="rgba(128,128,128,0.12)",
        zeroline=False,
    )
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False, nticks=5)
    fig.update_yaxes(range=[0, 1], fixedrange=True, visible=False, secondary_y=True)
    return fig


def add_series(fig, entry, frame, events, row, window):
    """Append one parameter to its reserved row without rebuilding previous rows."""
    xs = frame.flight_datetime.tolist()
    hover = f"%{{x|%d.%m.%y, %H:%M:%S}}<br>{entry['name']}: %{{y:.2f}}<extra></extra>"
    fig.add_trace(
        go.Scattergl(
            x=plotly_timestamps(xs),
            y=frame.value.to_numpy(dtype=float),
            mode="markers",
            name="Actual",
            legendgroup="actual",
            showlegend=row == 1,
            marker={"size": 3, "color": "#3b82f6", "opacity": 0.4},
            hovertemplate=hover,
        ),
        row=row,
        col=1,
    )
    line_x, line_y, gaps = line_with_gaps(xs, frame.smoothed.tolist())
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
    for lo, hi in gaps:
        fig.add_vrect(
            x0=lo,
            x1=hi,
            fillcolor="rgba(128,128,128,0.05)",
            line_width=0,
            layer="below",
            row=row,
            col=1,
            annotation_text="No data",
            annotation_position="inside",
            annotation_font={"size": 9, "color": "#888"},
            annotation_textangle=-90,
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
            fig.add_shape(
                type="line",
                x0=dt,
                x1=dt,
                y0=0,
                y1=1,
                yref="y domain",
                line={"color": color, "width": 1, "dash": "dot"},
                opacity=0.4,
                layer="below",
                row=row,
                col=1,
            )
