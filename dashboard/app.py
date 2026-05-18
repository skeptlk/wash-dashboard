"""Engine Wash Analysis Dashboard — Dash prototype."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonlib"))

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dcc, html
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from enginewash import (
    FlightRecord,
    MaintenanceRecord,
    PlotCurve,
    WashCalculator,
    WashConfig,
    WashEventMarkers,
)
from enginewash.models import (
    DEGT, EGTHDM, GWFM, WashParameter,
)

import schedule
from aircraft_registry import AIRCRAFT_REG

FA_CDN = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"

# ---------------------------------------------------------------------------
# Data loading (once at startup)
# ---------------------------------------------------------------------------

print("Loading parquet data…")

onwing_df = pd.read_csv(
    "https://storage.yandexcloud.net/ecm-data/s7_mdb._onwing_engine_20260423.csv"
)
onwing_df["engine_id"] = onwing_df["engine_id"].astype(str)
onwing_df["aircraft_id"] = onwing_df["aircraft_id"].astype(str).str.zfill(5)

_current_eids = set(onwing_df.loc[onwing_df["removal_datetime"].isna(), "engine_id"])
# Last mounting record per engine (covers both on-wing and off-wing)
_last_install = (
    onwing_df.sort_values("install_datetime")
    .drop_duplicates("engine_id", keep="last")
)
ENGINE_LABELS: dict[str, str] = {}
for _row in _last_install.itertuples():
    _eid = _row.engine_id
    _suffix = "" if _eid in _current_eids else " (off wing)"
    ENGINE_LABELS[_eid] = (
        f"{_eid} — "
        f"{_row.aircraft_family or '?'} "
        f"{AIRCRAFT_REG.get(_row.aircraft_id, _row.aircraft_id)} "
        f"pos.{_row.engine_position}{_suffix}"
    )

_engine_family_map: dict[str, str] = (
    _last_install.set_index("engine_id")["aircraft_family"]
    .fillna("")
    .to_dict()
)

maintenance_df = pd.read_parquet(
    "https://storage.yandexcloud.net/ecm-data/ecmapp.maintenance_20260222.parquet"
)
takeoff_df = pd.read_parquet(
    "https://storage.yandexcloud.net/ecm-data/s7.b737_takeoff_20260222-merged.parquet"
)
cruise_df = pd.read_parquet(
    "https://storage.yandexcloud.net/ecm-data/s7.b737_cruise_20260222-merged.parquet"
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

# Cruise data — GWFM and DEGT
cruise_gwfm = (
    cruise_df[["engine_id", "flight_datetime", "gwfm"]]
    .dropna()
    .copy()
)
cruise_gwfm["engine_id"] = cruise_gwfm["engine_id"].astype(int).astype(str)

cruise_degt = (
    cruise_df[["engine_id", "flight_datetime", "degt"]]
    .dropna()
    .copy()
)
cruise_degt["engine_id"] = cruise_degt["engine_id"].astype(int).astype(str)

# Parameter configuration mapping
PARAM_OPTIONS = {
    "EGTHDM (Takeoff)": {"col": "egthdm", "df": takeoff, "param": EGTHDM},
    "GWFM (Cruise)": {"col": "gwfm", "df": cruise_gwfm, "param": GWFM},
    "DEGT (Cruise)": {"col": "degt", "df": cruise_degt, "param": DEGT},
}

# Date range across all datasets
all_dates = pd.concat([
    takeoff["flight_datetime"],
    cruise_gwfm["flight_datetime"],
    cruise_degt["flight_datetime"],
])
DATE_MIN = all_dates.min().date()
DATE_MAX = all_dates.max().date()
DEFAULT_START = (all_dates.max() - pd.DateOffset(years=2)).date()

# Engines that appear in both wash and flight datasets
engine_ids_wash = set(wash_maint["engine_id_str"].unique())
engine_ids_flight = (
    set(takeoff["engine_id"].unique())
    | set(cruise_gwfm["engine_id"].unique())
    | set(cruise_degt["engine_id"].unique())
)
_AC_ORDER = {"A": 0, "B": 1, "E": 2}

def _eng_sort_key(eid: str) -> tuple:
    fam = str(_engine_family_map.get(eid) or "")
    return (_AC_ORDER.get(fam[:1].upper() if fam else "", 3), eid)

available_engines = sorted(engine_ids_wash & engine_ids_flight, key=_eng_sort_key)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

controls = dbc.Card(
    dbc.CardBody([
        html.H6("Engine Wash Analysis", className="fw-bold mb-2"),

        dbc.Label("Parameter", class_name="small fw-semibold mb-0"),
        dcc.Dropdown(
            id="param-selector",
            options=[{"label": k, "value": k} for k in PARAM_OPTIONS],
            value="EGTHDM (Takeoff)",
            clearable=False,
            className="mb-2",
        ),

        dbc.Label("Engines", class_name="small fw-semibold mb-0"),
        dcc.Dropdown(
            id="engine-selector",
            options=[
                {"label": ENGINE_LABELS.get(eid, eid), "value": eid}
                for eid in available_engines
            ],
            value=[available_engines[0]] if available_engines else [],
            multi=True,
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
                dbc.Input(id="n-obs-mean", type="number", value=15, min=3,
                          step=1, size="sm"),
            ], width=6),
            dbc.Col([
                dbc.Label("LoE threshold", class_name="x-small text-muted mb-0",
                          style={"fontSize": "0.72rem"}),
                dbc.Input(id="loe-threshold", type="number", value=2.0, min=0.01, max=20.0,
                          step=0.01, size="sm"),
            ], width=6),
        ], className="mb-2 g-2"),

        dbc.Button("Make Report", id="run-button", color="primary",
                   className="w-100", size="sm"),
    ], className="p-2"),
)

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, FA_CDN],
    title="Engine Wash Dashboard",
    suppress_callback_exceptions=True,
)

analysis_page = dbc.Row(
    [
        dbc.Col(
            [
                controls,
                html.Div(id="table-container", className="mt-2"),
                html.Div(id="violin-container", className="mt-2"),
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

schedule_page = schedule.build(
    app,
    wash_maint=wash_maint,
    onwing_df=onwing_df,
    aircraft_reg=AIRCRAFT_REG,
    engine_labels=ENGINE_LABELS,
)

header = dbc.Row(
    [
        dbc.Col(
            html.H5("Engine Wash Dashboard", className="fw-bold mb-0"),
            width="auto",
        ),
        dbc.Col(
            html.Span([
                dbc.Label(className="fa fa-moon me-1", html_for="theme-toggle"),
                dbc.Switch(id="theme-toggle", value=True,
                           className="d-inline-block ms-1 mb-0", persistence=True),
                dbc.Label(className="fa fa-sun ms-1", html_for="theme-toggle"),
            ]),
            width="auto", className="ms-auto d-flex align-items-center",
        ),
    ],
    align="center", className="pt-2 pb-1",
)

app.layout = dbc.Container(
    [
        dcc.Store(id="theme-store", data=False),
        dcc.Store(id="figure-store"),
        dcc.Store(id="violin-store"),
        dcc.Store(id="active-engine"),
        header,
        dbc.Tabs(
            [
                dbc.Tab(analysis_page, label="Analysis", tab_id="tab-analysis"),
                dbc.Tab(schedule_page, label="Wash Schedule", tab_id="tab-schedule"),
            ],
            id="main-tabs",
            active_tab="tab-analysis",
        ),
    ],
    fluid=True,
)

# ---------------------------------------------------------------------------
# Theme switching
# ---------------------------------------------------------------------------

app.clientside_callback(
    """
    function(switchOn) {
        document.documentElement.setAttribute(
            "data-bs-theme", switchOn ? "light" : "dark"
        );
        return !switchOn;
    }
    """,
    Output("theme-store", "data"),
    Input("theme-toggle", "value"),
)

# ---------------------------------------------------------------------------
# Update LoE threshold default when parameter changes
# ---------------------------------------------------------------------------

@app.callback(
    Output("loe-threshold", "value"),
    Input("param-selector", "value"),
)
def update_loe_threshold(param_key):
    if param_key and param_key in PARAM_OPTIONS:
        return PARAM_OPTIONS[param_key]["param"].threshold
    return 2.0

# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


def _strip_tz(dt):
    """Return a tz-naive datetime from a pandas Timestamp."""
    ts = pd.Timestamp(dt)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts.replace(tzinfo=None)


def _build_chart(
    engine_id: str,
    curves: list[PlotCurve],
    markers: list[WashEventMarkers],
    param: WashParameter,
):
    fig = go.Figure()
    by_kind = {c.kind: c for c in curves}

    raw = by_kind.get("raw")
    if raw and raw.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in raw.points],
            y=[p.value for p in raw.points],
            mode="markers",
            marker=dict(size=4, color="steelblue", opacity=0.35),
            name=f"{param.name} (raw)",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra></extra>",
        ))

    smooth = by_kind.get("smooth")
    if smooth and smooth.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in smooth.points],
            y=[p.value for p in smooth.points],
            mode="lines", line=dict(color="steelblue", width=1.5),
            name="Smooth",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra>smooth</extra>",
        ))

    smooth2 = by_kind.get("smooth_custom")
    if smooth2 and smooth2.points:
        fig.add_trace(go.Scatter(
            x=[p.flight_datetime for p in smooth2.points],
            y=[p.value for p in smooth2.points],
            mode="lines", line=dict(color="darkorange", width=2),
            name="2nd smooth",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra>2nd smooth</extra>",
        ))

    shapes, annotations = [], []
    for i, m in enumerate(markers):
        wash_t = m.wash_event_point.flight_datetime
        shapes.append(dict(
            type="line", x0=wash_t, x1=wash_t, y0=0, y1=1, yref="paper",
            line=dict(color="green", width=1.5),
        ))
        annotations.append(dict(
            x=wash_t, y=1.01, yref="paper", xref="x",
            text=f"#{m.event_index}", showarrow=False,
            font=dict(size=9, color="green"), yanchor="bottom",
        ))

        if m.before_value_point is not None:
            bp = m.before_value_point
            fig.add_trace(go.Scatter(
                x=[bp.flight_datetime], y=[bp.value],
                mode="markers",
                marker=dict(symbol="diamond-dot", size=8, color="green",
                            line=dict(color="white", width=1)),
                hovertemplate=(
                    f"Pre-wash extremum (#{m.event_index})<br>"
                    f"mean_before = {bp.value:.2f}<br>"
                    "%{x|%Y-%m-%d}<extra></extra>"
                ),
                name="Pre-wash extremum", legendgroup="before_value",
                showlegend=(i == 0),
            ))

        if m.after_value_point is not None:
            ap = m.after_value_point
            fig.add_trace(go.Scatter(
                x=[ap.flight_datetime], y=[ap.value],
                mode="markers",
                marker=dict(symbol="diamond-dot", size=8, color="limegreen",
                            line=dict(color="white", width=1)),
                hovertemplate=(
                    f"Post-wash extremum (#{m.event_index})<br>"
                    f"mean_after = {ap.value:.2f}<br>"
                    "%{x|%Y-%m-%d}<extra></extra>"
                ),
                name="Post-wash extremum", legendgroup="after_value",
                showlegend=(i == 0),
            ))

        if m.before_segment is not None:
            bs = m.before_segment
            shapes.append(dict(
                type="line",
                x0=bs.start_datetime, x1=bs.end_datetime,
                y0=0.4, y1=0.4,
                xref="x", yref="y",
                line=dict(color="green", width=2),
            ))

        if m.after_segment is not None:
            as_ = m.after_segment
            shapes.append(dict(
                type="line",
                x0=as_.start_datetime, x1=as_.end_datetime,
                y0=0.4, y1=0.4,
                xref="x", yref="y",
                line=dict(color="limegreen", width=2),
            ))

        loe = m.loss_of_efficiency_point
        if loe is not None:
            shapes.append(dict(
                type="line", x0=loe.flight_datetime, x1=loe.flight_datetime,
                y0=0, y1=1, yref="paper",
                line=dict(color="crimson", width=1.5, dash="dash"),
                layer="below",
            ))
            annotations.append(dict(
                x=loe.flight_datetime, y=0.02, yref="paper", xref="x",
                text=f"LoE #{m.event_index}", showarrow=False,
                font=dict(size=9, color="crimson"), yanchor="bottom",
            ))

    fig.update_layout(
        title=dict(
            text=f"Engine {engine_id} — {param.name} ({param.flight_phase.value.title()})",
            font=dict(size=15), x=0, xanchor="left",
        ),
        xaxis=dict(title="Date", rangeslider=dict(visible=True, thickness=0.08), type="date"),
        yaxis_title=param.name,
        shapes=shapes, annotations=annotations,
        legend=dict(orientation="v", x=1.0, y=1.0, xanchor="right", yanchor="bottom"),
        autosize=True, hovermode="x unified",
        margin=dict(t=100, r=20, b=20, l=60),
    )
    return fig


@app.callback(
    Output("figure-store", "data"),
    Output("table-container", "children"),
    Output("violin-store", "data"),
    Output("active-engine", "data"),
    Input("run-button", "n_clicks"),
    State("param-selector", "value"),
    State("engine-selector", "value"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("smooth-window", "value"),
    State("pre-smooth-window", "value"),
    State("n-obs-mean", "value"),
    State("loe-threshold", "value"),
    prevent_initial_call=True,
)
def compute_report(n_clicks, param_key, engine_ids, start_date, end_date,
                   smooth_window, pre_smooth_window, n_obs_mean, loe_threshold):

    if isinstance(engine_ids, str):
        engine_ids = [engine_ids]
    if not engine_ids:
        return {"type": "error", "color": "warning", "message": "Please select at least one engine."}, None, None, None

    chart_engine = engine_ids[0]

    # --- Resolve parameter config ---
    pcfg = PARAM_OPTIONS.get(param_key or "EGTHDM (Takeoff)")
    param = pcfg["param"]
    col = pcfg["col"]
    source_df = pcfg["df"]

    # --- Filter flight data to all selected engines ---
    all_pts = source_df[source_df["engine_id"].isin(engine_ids)].copy()
    if start_date:
        all_pts = all_pts[all_pts["flight_datetime"] >= pd.Timestamp(start_date)]
    if end_date:
        all_pts = all_pts[all_pts["flight_datetime"] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]
    all_pts = all_pts.sort_values(["engine_id", "flight_datetime"]).reset_index(drop=True)

    if all_pts.empty:
        return {
            "type": "error", "color": "warning",
            "message": f"No {param.name} data for the selected engines in the date range.",
        }, None, None, None

    pts = all_pts[all_pts["engine_id"] == chart_engine].reset_index(drop=True)
    if pts.empty:
        return {
            "type": "error", "color": "warning",
            "message": f"No {param.name} data for engine {chart_engine} (the first selected) in the date range.",
        }, None, None, None

    # --- Build records across all selected engines ---
    flights = [
        FlightRecord(
            engine_id=row.engine_id,
            flight_datetime=row.flight_datetime,
            parameter_name=param.name,
            flight_phase=param.flight_phase,
            float_value=getattr(row, col),
        )
        for row in all_pts.itertuples()
    ]

    eng_maint = wash_maint[wash_maint["engine_id_str"].isin(engine_ids)]
    maintenance_records = [
        MaintenanceRecord(
            engine_id=row.engine_id_str,
            maint_datetime=_strip_tz(row.maint_datetime),
            ata_code=str(row.ata_code),
        )
        for row in eng_maint.itertuples()
    ]

    # --- Run calculator (single call across all engines) ---
    param = WashParameter(
        name=param.name,
        flight_phase=param.flight_phase,
        trend_direction=param.trend_direction,
        threshold=float(loe_threshold or param.threshold),
    )
    config = WashConfig(
        smooth_window=int(smooth_window or 30),
        pre_smooth_window=int(pre_smooth_window or 15),
        n_obs_mean=int(n_obs_mean or 15),
    )
    calc = WashCalculator(config=config)
    summaries = calc.process(flights=flights, maintenance=maintenance_records, parameter=param)
    plot = calc.build_plot(flights=flights, maintenance=maintenance_records, parameter=param)
    all_events = [ev for s in summaries for ev in s.results]

    if not all_events:
        return {
            "type": "error", "color": "info",
            "message": "No wash events found for the selected engines in the date range.",
        }, None, None, None

    curves_by_eng: dict[str, list[PlotCurve]] = {}
    for c in plot.curves:
        curves_by_eng.setdefault(c.engine_id, []).append(c)
    markers_by_eng: dict[str, list[WashEventMarkers]] = {}
    for m in plot.markers:
        markers_by_eng.setdefault(m.engine_id, []).append(m)

    figures = {}
    for eid in engine_ids:
        markers = sorted(markers_by_eng.get(eid, []), key=lambda m: m.event_index)
        if not markers:
            continue
        figures[eid] = _build_chart(
            eid, curves_by_eng.get(eid, []), markers, param,
        ).to_dict()

    if not figures:
        return {
            "type": "error", "color": "info",
            "message": "No wash events found for the selected engines in the date range.",
        }, None, None, None

    # --- Summary table (all selected engines) ---
    sorted_all = sorted(
        all_events,
        key=lambda e: (str(e.engine_id), e.maint_datetime or pd.Timestamp.min),
    )
    rows = []
    for ev in sorted_all:
        if str(ev.engine_id) not in figures:
            continue
        delta_color = "text-success" if ev.delta > 0 else "text-danger"
        rows.append(html.Tr(
            [
                html.Td(str(ev.engine_id)),
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
            ],
            id={"type": "row-click", "engine": str(ev.engine_id), "idx": ev.event_index},
            n_clicks=0,
            style={"cursor": "pointer"},
        ))

    table = dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Engine"), html.Th("#"), html.Th("Date"), html.Th("ATA"),
                html.Th("Before"), html.Th("After"), html.Th("Δ"),
                html.Th("LoE date"), html.Th("Days"),
            ])),
            html.Tbody(rows),
        ],
        striped=True, bordered=True, hover=True, size="sm", className="mt-0",
    )

    n_engines = len({str(ev.engine_id) for ev in all_events})
    subtitle = html.P(
        f"{len(all_events)} wash event(s) across {n_engines} engine(s) — "
        f"{param.name} / {param.flight_phase.value.title()}",
        className="text-muted small mb-1",
    )

    # --- Violin plot: delta by ATA code ---
    ata_groups: dict[str, list[float]] = {}
    for ev in all_events:
        key = ev.ata_code or "—"
        ata_groups.setdefault(key, []).append(ev.delta)

    violin_fig = go.Figure()
    for ata_code, deltas in sorted(ata_groups.items()):
        violin_fig.add_trace(go.Violin(
            y=deltas,
            name=ata_code,
            box_visible=True,
            meanline_visible=True,
            points="all",
            pointpos=0,
            jitter=0.3,
            marker=dict(size=4),
        ))
    violin_fig.update_layout(
        title=dict(text="Δ by ATA code", font=dict(size=10), x=0, xanchor="left"),
        yaxis_title=f"Δ {param.name}",
        showlegend=False,
        margin=dict(t=36, r=8, b=36, l=48),
        height=280,
    )
    return {"type": "figures", "figures": figures}, [subtitle, table], violin_fig.to_dict(), chart_engine


@app.callback(
    Output("active-engine", "data", allow_duplicate=True),
    Input({"type": "row-click", "engine": ALL, "idx": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_row_click(_):
    if not ctx.triggered_id:
        return dash.no_update
    return ctx.triggered_id["engine"]


_available_engines_set = set(available_engines)


@app.callback(
    Output("main-tabs", "active_tab"),
    Output("engine-selector", "value"),
    Output("run-button", "n_clicks"),
    Input("schedule-click", "data"),
    State("run-button", "n_clicks"),
    prevent_initial_call=True,
)
def on_schedule_click(data, current_clicks):
    if not data or not data.get("engine_id"):
        return dash.no_update, dash.no_update, dash.no_update
    engine_id = data["engine_id"]
    if engine_id not in _available_engines_set:
        return dash.no_update, dash.no_update, dash.no_update
    return "tab-analysis", [engine_id], (current_clicks or 0) + 1


@app.callback(
    Output("chart-container", "children"),
    Input("figure-store", "data"),
    Input("active-engine", "data"),
    Input("theme-store", "data"),
)
def render_chart(data, active_engine, is_dark):
    if not data:
        return html.P(
            "Select an engine and press Make Report.",
            className="text-muted mt-5 text-center",
        )
    if data.get("type") == "error":
        return dbc.Alert(data["message"], color=data["color"])
    figures = data["figures"]
    engine_id = active_engine if active_engine in figures else next(iter(figures))
    fig = go.Figure(figures[engine_id])
    fig.update_layout(template="plotly_dark" if is_dark else "plotly_white")
    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": True, "responsive": True},
        style={"height": "calc(100vh - 24px)"},
    )


@app.callback(
    Output("violin-container", "children"),
    Input("violin-store", "data"),
    Input("theme-store", "data"),
)
def render_violin(data, is_dark):
    if not data:
        return None
    fig = go.Figure(data)
    fig.update_layout(template="plotly_dark" if is_dark else "plotly_white")
    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": False, "responsive": True},
    )


if __name__ == "__main__":
    app.run(debug=True, port=8050)
