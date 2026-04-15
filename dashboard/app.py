"""Engine Wash Analysis Dashboard — Dash prototype."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonlib"))

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from enginewash import FlightRecord, MaintenanceRecord, WashCalculator, WashConfig
from enginewash.models import FlightPhase, TrendDirection, WashParameter
from enginewash.smoothing import smooth_series

THEME_LIGHT = dbc.themes.FLATLY
THEME_DARK = dbc.themes.DARKLY

# ---------------------------------------------------------------------------
# Data loading (once at startup)
# ---------------------------------------------------------------------------

print("Loading parquet data…")

maintenance_df = pd.read_parquet(
    "https://storage.yandexcloud.net/ecm-data/ecmapp.maintenance_20260222.parquet"
)
takeoff_df = pd.read_parquet(
    "https://storage.yandexcloud.net/ecm-data/s7.b737_takeoff_20260222-merged.parquet"
)

print("Data loaded.")

# Wash maintenance records (ATA 330-349)
wash_maint = maintenance_df[
    maintenance_df["ata_code"].astype(str).str.match(r"^3[34]\d$")
].copy()
wash_maint["engine_id_str"] = wash_maint["engine_id"].astype(str)

# Takeoff data — keep only what we need
takeoff = (
    takeoff_df[["engine_id", "flight_datetime", "egthdm"]]
    .dropna()
    .copy()
)
takeoff["engine_id"] = takeoff["engine_id"].astype(int).astype(str)

DATE_MIN = takeoff["flight_datetime"].min().date()
DATE_MAX = takeoff["flight_datetime"].max().date()
DEFAULT_START = (takeoff["flight_datetime"].max() - pd.DateOffset(years=2)).date()

# Engines that appear in both datasets
engine_ids_wash = set(wash_maint["engine_id_str"].unique())
engine_ids_takeoff = set(takeoff["engine_id"].unique())
available_engines = sorted(engine_ids_wash & engine_ids_takeoff)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

controls = dbc.Card(
    dbc.CardBody([
        dbc.Row([
            dbc.Col(html.H6("Engine Wash Analysis", className="fw-bold mb-0"),
                    width="auto"),
            dbc.Col(
                dbc.Switch(id="theme-toggle", label="Dark", value=False,
                           className="mb-0", style={"fontSize": "0.75rem"}),
                width="auto", className="ms-auto",
            ),
        ], align="center", className="mb-2"),

        dbc.Label("Engine", class_name="small fw-semibold mb-0"),
        dcc.Dropdown(
            id="engine-selector",
            options=[{"label": eid, "value": eid} for eid in available_engines],
            value=available_engines[0] if available_engines else None,
            clearable=False,
            className="mb-2",
        ),

        dbc.Label("Date Range", class_name="small fw-semibold mb-0"),
        dcc.DatePickerRange(
            id="date-range",
            min_date_allowed=DATE_MIN,
            max_date_allowed=DATE_MAX,
            start_date=DEFAULT_START,
            end_date=DATE_MAX,
            display_format="YYYY-MM-DD",
            className="mb-2 d-block",
        ),

        html.Hr(className="my-2"),
        html.P("Smoothing & Detection", className="small fw-semibold mb-1 text-muted"),

        dbc.Row([
            dbc.Col([
                dbc.Label("Smooth window", class_name="x-small text-muted mb-0",
                          style={"fontSize": "0.72rem"}),
                dbc.Input(id="smooth-window", type="number", value=30, min=5, max=100,
                          step=1, size="sm"),
            ], width=6),
            dbc.Col([
                dbc.Label("Pre-smooth", class_name="x-small text-muted mb-0",
                          style={"fontSize": "0.72rem"}),
                dbc.Input(id="pre-smooth-window", type="number", value=15, min=5, max=50,
                          step=1, size="sm"),
            ], width=6),
        ], className="mb-1 g-2"),

        dbc.Row([
            dbc.Col([
                dbc.Label("N obs (mean)", class_name="x-small text-muted mb-0",
                          style={"fontSize": "0.72rem"}),
                dbc.Input(id="n-obs-mean", type="number", value=15, min=3, max=50,
                          step=1, size="sm"),
            ], width=6),
            dbc.Col([
                dbc.Label("LoE threshold °C", class_name="x-small text-muted mb-0",
                          style={"fontSize": "0.72rem"}),
                dbc.Input(id="loe-threshold", type="number", value=2.0, min=0.5, max=20.0,
                          step=0.5, size="sm"),
            ], width=6),
        ], className="mb-2 g-2"),

        dbc.Button("Make Report", id="run-button", color="primary",
                   className="w-100", size="sm"),
    ], className="p-2"),
)

app = dash.Dash(
    __name__,
    external_stylesheets=[THEME_LIGHT],
    title="Engine Wash Dashboard",
)

app.layout = dbc.Container(
    [
        dcc.Store(id="theme-store", data=False),
        dbc.Row(
            [
                dbc.Col(
                    [
                        controls,
                        html.Div(id="table-container", className="mt-2"),
                    ],
                    width=3,
                    className="pt-3",
                    style={"overflowY": "auto", "maxHeight": "100vh"},
                ),
                dbc.Col(
                    dcc.Loading(
                        id="loading",
                        children=html.Div(
                            id="chart-container",
                            children=html.P(
                                "Select an engine and press Make Report.",
                                className="text-muted mt-5 text-center",
                            ),
                        ),
                        type="circle",
                    ),
                    width=9,
                    className="pt-3",
                ),
            ],
            style={"minHeight": "100vh"},
        )
    ],
    fluid=True,
)

# ---------------------------------------------------------------------------
# Theme switching
# ---------------------------------------------------------------------------

app.clientside_callback(
    """
    function(dark) {
        var lightUrl = "%s";
        var darkUrl = "%s";
        var sheets = document.querySelectorAll('link[rel="stylesheet"]');
        for (var i = 0; i < sheets.length; i++) {
            if (sheets[i].href.includes('flatly') || sheets[i].href.includes('darkly')) {
                sheets[i].href = dark ? darkUrl : lightUrl;
            }
        }
        return dark;
    }
    """ % (THEME_LIGHT, THEME_DARK),
    Output("theme-store", "data"),
    Input("theme-toggle", "value"),
)

# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


def _strip_tz(dt):
    """Return a tz-naive datetime from a pandas Timestamp."""
    ts = pd.Timestamp(dt)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts.replace(tzinfo=None)


@app.callback(
    Output("chart-container", "children"),
    Output("table-container", "children"),
    Input("run-button", "n_clicks"),
    State("engine-selector", "value"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("smooth-window", "value"),
    State("pre-smooth-window", "value"),
    State("n-obs-mean", "value"),
    State("loe-threshold", "value"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def make_report(n_clicks, engine_id, start_date, end_date, smooth_window,
                pre_smooth_window, n_obs_mean, loe_threshold, is_dark):

    if not engine_id:
        return dbc.Alert("Please select an engine.", color="warning"), None

    # --- Filter takeoff data ---
    pts = takeoff[takeoff["engine_id"] == engine_id].copy()
    if start_date:
        pts = pts[pts["flight_datetime"] >= pd.Timestamp(start_date)]
    if end_date:
        pts = pts[pts["flight_datetime"] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]
    pts = pts.sort_values("flight_datetime").reset_index(drop=True)

    if pts.empty:
        return dbc.Alert(
            f"No takeoff data for engine {engine_id} in the selected date range.",
            color="warning",
        ), None

    # --- Build records ---
    flights = [
        FlightRecord(
            engine_id=row.engine_id,
            flight_datetime=row.flight_datetime,
            parameter_name="EGTHDM",
            flight_phase=FlightPhase.TAKEOFF,
            float_value=row.egthdm,
        )
        for row in pts.itertuples()
    ]

    eng_maint = wash_maint[wash_maint["engine_id_str"] == engine_id]
    maintenance_records = [
        MaintenanceRecord(
            engine_id=engine_id,
            maint_datetime=_strip_tz(row.maint_datetime),
            ata_code=str(row.ata_code),
        )
        for row in eng_maint.itertuples()
    ]

    # --- Run calculator ---
    param = WashParameter(
        name="EGTHDM",
        flight_phase=FlightPhase.TAKEOFF,
        trend_direction=TrendDirection.UP,
        threshold=float(loe_threshold or 2.0),
    )
    config = WashConfig(
        smooth_window=int(smooth_window or 30),
        pre_smooth_window=int(pre_smooth_window or 15),
        n_obs_mean=int(n_obs_mean or 15),
    )
    calc = WashCalculator(config=config)
    summaries, processed_df = calc.process_with_data(
        flights=flights, maintenance=maintenance_records, parameter=param
    )
    events = [ev for s in summaries for ev in s.results]

    if not events:
        return dbc.Alert(
            f"No wash events found for engine {engine_id} in the selected date range.",
            color="info",
        ), None

    # --- Build Plotly figure ---
    sw = int(smooth_window or 30)

    fig = go.Figure()

    # Raw scatter
    fig.add_trace(go.Scatter(
        x=pts["flight_datetime"],
        y=pts["egthdm"],
        mode="markers",
        marker=dict(size=4, color="steelblue", opacity=0.35),
        name="EGTHDM (raw)",
        hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f} °C<extra></extra>",
    ))

    # Smooth line — one trace per segment so it breaks at each wash
    wash_times_sorted = sorted(
        pd.Timestamp(ev.maint_datetime)
        for ev in events
        if ev.maint_datetime is not None
    )
    seg_boundaries = (
        [pts["flight_datetime"].min()]
        + wash_times_sorted
        + [pts["flight_datetime"].max() + pd.Timedelta(days=1)]
    )
    for seg_idx in range(len(seg_boundaries) - 1):
        seg = pts[
            (pts["flight_datetime"] >= seg_boundaries[seg_idx])
            & (pts["flight_datetime"] < seg_boundaries[seg_idx + 1])
        ].copy()
        if seg.empty:
            continue
        seg_smooth = smooth_series(seg["egthdm"], window=sw, fallback=seg["egthdm"])
        fig.add_trace(go.Scatter(
            x=seg["flight_datetime"],
            y=seg_smooth,
            mode="lines",
            line=dict(color="steelblue", width=1.5),
            name="Smooth",
            legendgroup="smooth",
            showlegend=(seg_idx == 0),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f} °C<extra>smooth</extra>",
        ))

    # Double-smooth line (float_value_smooth_custom) — what the calculator actually
    # uses for before/after extremum selection; one trace per segment so it breaks at washes
    for ecum, grp in processed_df.groupby("event_cum"):
        grp = grp.sort_values("flight_datetime")
        fig.add_trace(go.Scatter(
            x=grp["flight_datetime"],
            y=grp["float_value_smooth_custom"],
            mode="lines",
            line=dict(color="darkorange", width=2),
            name="2nd smooth (used for extremums)",
            legendgroup="smooth2",
            showlegend=bool(ecum == processed_df["event_cum"].min()),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f} °C<extra>2nd smooth</extra>",
        ))

    shapes = []
    annotations = []

    # Segment boundaries for mean lines
    wash_times = [ev.maint_datetime for ev in events if ev.maint_datetime]
    seg_starts = [pts["flight_datetime"].min()] + wash_times

    for i, ev in enumerate(events):
        if ev.maint_datetime is None:
            continue

        wash_t = pd.Timestamp(ev.maint_datetime)
        seg_start = pd.Timestamp(seg_starts[i])
        after_end = (
            pd.Timestamp(ev.time_loss_of_efficiency)
            if ev.time_loss_of_efficiency
            else pts["flight_datetime"].max()
        )

        # Wash vertical line
        shapes.append(dict(
            type="line", x0=wash_t, x1=wash_t, y0=0, y1=1, yref="paper",
            line=dict(color="green", width=1.5),
        ))
        annotations.append(dict(
            x=wash_t, y=1.01, yref="paper", xref="x",
            text=f"#{ev.event_index}", showarrow=False,
            font=dict(size=9, color="green"), yanchor="bottom",
        ))

        # Mean-before horizontal line
        fig.add_trace(go.Scatter(
            x=[seg_start, wash_t],
            y=[ev.mean_before, ev.mean_before],
            mode="lines",
            line=dict(color="green", width=2, dash="dash"),
            name="Mean before",
            legendgroup="mean_before",
            showlegend=(i == 0),
            hovertemplate=f"Mean before wash #{ev.event_index}: {ev.mean_before:.1f} °C<extra></extra>",
        ))

        # Mean-after horizontal line
        fig.add_trace(go.Scatter(
            x=[wash_t, after_end],
            y=[ev.mean_after, ev.mean_after],
            mode="lines",
            line=dict(color="limegreen", width=2, dash="dash"),
            name="Mean after",
            legendgroup="mean_after",
            showlegend=(i == 0),
            hovertemplate=f"Mean after wash #{ev.event_index}: {ev.mean_after:.1f} °C<extra></extra>",
        ))

        # Loss-of-efficiency vertical line
        if ev.time_loss_of_efficiency:
            loe_t = pd.Timestamp(ev.time_loss_of_efficiency)
            shapes.append(dict(
                type="line", x0=loe_t, x1=loe_t, y0=0, y1=1, yref="paper",
                line=dict(color="crimson", width=1.5, dash="dash"),
            ))
            annotations.append(dict(
                x=loe_t, y=0.96, yref="paper", xref="x",
                text=f"LoE #{ev.event_index}",
                showarrow=False,
                font=dict(size=9, color="crimson"),
                yanchor="bottom",
            ))

    fig.update_layout(
        title=dict(text=f"Engine {engine_id} — EGTHDM (Takeoff)", font=dict(size=15)),
        xaxis=dict(
            title="Date",
            rangeslider=dict(visible=True, thickness=0.08),
            type="date",
        ),
        yaxis_title="EGTHDM (°C)",
        shapes=shapes,
        annotations=annotations,
        legend=dict(orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
        height=680,
        template="plotly_dark" if is_dark else "plotly_white",
        hovermode="x unified",
        margin=dict(t=50, r=20, b=20, l=60),
    )

    # --- Summary table ---
    rows = []
    for ev in events:
        delta_color = "text-success" if ev.delta > 0 else "text-danger"
        rows.append(html.Tr([
            html.Td(f"#{ev.event_index}"),
            html.Td(ev.maint_datetime.strftime("%Y-%m-%d") if ev.maint_datetime else "—"),
            html.Td(ev.ata_code or "—"),
            html.Td(f"{ev.mean_before:.1f}"),
            html.Td(f"{ev.mean_after:.1f}"),
            html.Td(f"{ev.delta:+.2f}", className=delta_color),
            html.Td(
                ev.time_loss_of_efficiency.strftime("%Y-%m-%d")
                if ev.time_loss_of_efficiency else "—"
            ),
            html.Td(f"{ev.days_loss_of_efficiency} d" if ev.days_loss_of_efficiency else "—"),
        ]))

    table = dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("#"), html.Th("Date"), html.Th("ATA"),
                html.Th("Before"), html.Th("After"), html.Th("Δ"),
                html.Th("LoE date"), html.Th("Days"),
            ])),
            html.Tbody(rows),
        ],
        striped=True, bordered=True, hover=True, size="sm", className="mt-0",
    )

    chart = dcc.Graph(figure=fig, config={"displayModeBar": True},
                      style={"height": "680px"})

    subtitle = html.P(
        f"{len(events)} wash event(s) — EGTHDM / Takeoff",
        className="text-muted small mb-1",
    )

    return chart, [subtitle, table]


if __name__ == "__main__":
    app.run(debug=True, port=8050)
