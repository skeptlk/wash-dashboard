"""Pure figure builders for the Wash Analysis page (ported from dashboard/app.py)."""

from __future__ import annotations

from enginewash.models import PlotCurve, WashEvent, WashEventMarkers, WashParameter
import plotly.graph_objects as go


def build_analysis_chart(
    engine_id: str,
    engine_label: str,
    curves: list[PlotCurve],
    markers: list[WashEventMarkers],
    param: WashParameter,
) -> go.Figure:
    """Build a per-engine wash-effect chart. Ported from dashboard/app.py:_build_chart."""
    fig = go.Figure()
    by_kind = {c.kind: c for c in curves}

    raw = by_kind.get("raw")
    if raw and raw.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in raw.points],
            y=[p.value for p in raw.points],
            mode="markers",
            marker={"size": 4, "color": "steelblue", "opacity": 0.35},
            name=f"{param.name} (raw)",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra></extra>",
        ))

    smooth = by_kind.get("smooth")
    if smooth and smooth.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in smooth.points],
            y=[p.value for p in smooth.points],
            mode="lines",
            line={"color": "steelblue", "width": 1.5},
            name="Smooth",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra>smooth</extra>",
        ))

    smooth2 = by_kind.get("smooth_custom")
    if smooth2 and smooth2.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in smooth2.points],
            y=[p.value for p in smooth2.points],
            mode="lines",
            line={"color": "darkorange", "width": 2},
            name="2nd smooth",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra>2nd smooth</extra>",
        ))

    shapes, annotations = [], []

    for i, m in enumerate(markers):
        wash_t = m.wash_event_point.flight_datetime

        # Vertical green line at wash date
        shapes.append({
            "type": "line", "x0": wash_t, "x1": wash_t, "y0": 0, "y1": 1,
            "yref": "paper", "line": {"color": "green", "width": 1.5},
        })
        annotations.append({
            "x": wash_t, "y": 1.01, "yref": "paper", "xref": "x",
            "text": f"#{m.event_index}", "showarrow": False,
            "font": {"size": 9, "color": "green"}, "yanchor": "bottom",
        })

        if m.before_value_point is not None:
            bp = m.before_value_point
            fig.add_trace(go.Scatter(
                x=[bp.flight_datetime], y=[bp.value],
                mode="markers",
                marker={"symbol": "diamond-dot", "size": 8, "color": "green",
                        "line": {"color": "white", "width": 1}},
                hovertemplate=(
                    f"Pre-wash extremum (#{m.event_index})<br>"
                    f"mean_before = {bp.value:.2f}<br>"
                    "%{x|%Y-%m-%d}<extra></extra>"
                ),
                name="Pre-wash extremum",
                legendgroup="before_value",
                showlegend=(i == 0),
            ))

        if m.after_value_point is not None:
            ap = m.after_value_point
            fig.add_trace(go.Scatter(
                x=[ap.flight_datetime], y=[ap.value],
                mode="markers",
                marker={"symbol": "diamond-dot", "size": 8, "color": "limegreen",
                        "line": {"color": "white", "width": 1}},
                hovertemplate=(
                    f"Post-wash extremum (#{m.event_index})<br>"
                    f"mean_after = {ap.value:.2f}<br>"
                    "%{x|%Y-%m-%d}<extra></extra>"
                ),
                name="Post-wash extremum",
                legendgroup="after_value",
                showlegend=(i == 0),
            ))

        if m.before_segment is not None:
            bs = m.before_segment
            shapes.append({
                "type": "line",
                "x0": bs.start_datetime, "x1": bs.end_datetime,
                "y0": bs.value, "y1": bs.value,
                "xref": "x", "yref": "y",
                "line": {"color": "green", "width": 2},
            })

        if m.after_segment is not None:
            as_ = m.after_segment
            shapes.append({
                "type": "line",
                "x0": as_.start_datetime, "x1": as_.end_datetime,
                "y0": as_.value, "y1": as_.value,
                "xref": "x", "yref": "y",
                "line": {"color": "limegreen", "width": 2},
            })

        loe = m.loss_of_efficiency_point
        if loe is not None:
            shapes.append({
                "type": "line", "x0": loe.flight_datetime, "x1": loe.flight_datetime,
                "y0": 0, "y1": 1, "yref": "paper",
                "line": {"color": "crimson", "width": 1.5, "dash": "dash"},
                "layer": "below",
            })
            annotations.append({
                "x": loe.flight_datetime, "y": 0.02, "yref": "paper", "xref": "x",
                "text": f"LoE #{m.event_index}", "showarrow": False,
                "font": {"size": 9, "color": "crimson"}, "yanchor": "bottom",
            })

    fig.update_layout(
        title={
            "text": f"{engine_label} — {param.name} ({param.flight_phase.value.title()})",
            "font": {"size": 14}, "x": 0, "xanchor": "left",
        },
        xaxis={
            "title": "Date",
            "rangeslider": {"visible": True, "thickness": 0.06},
            "type": "date",
        },
        yaxis_title=param.name,
        shapes=shapes,
        annotations=annotations,
        legend={"orientation": "v", "x": 1.0, "y": 1.0, "xanchor": "right", "yanchor": "bottom"},
        autosize=True,
        hovermode="x unified",
        margin={"t": 80, "r": 20, "b": 40, "l": 60},
        height=520,
    )
    return fig


def build_violin_figure(events: list[WashEvent], param: WashParameter) -> go.Figure:
    """Build a violin plot of delta by ATA code."""
    ata_groups: dict[str, list[float]] = {}
    for ev in events:
        ata_groups.setdefault(ev.ata_code or "—", []).append(ev.delta)

    fig = go.Figure()
    for ata_code, deltas in sorted(ata_groups.items()):
        fig.add_trace(go.Violin(
            y=deltas,
            name=ata_code,
            box_visible=True,
            meanline_visible=True,
            points="all",
            pointpos=0,
            jitter=0.3,
            marker={"size": 4},
        ))
    fig.update_layout(
        title={"text": f"Δ {param.name} by ATA code", "font": {"size": 11}, "x": 0, "xanchor": "left"},
        yaxis_title=f"Δ {param.name}",
        showlegend=False,
        margin={"t": 36, "r": 8, "b": 36, "l": 48},
        height=260,
    )
    return fig
