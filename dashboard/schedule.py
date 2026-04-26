"""Wash Schedule (Gantt) tab: data prep, layout and callbacks.

Expose a single entry point, :func:`build`, which takes the shared datasets
and the Dash ``app``, registers the tab's callbacks, and returns the layout
component to plug into the parent app.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

UNINSTALLED = "— uninstalled —"

_ATA_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _prepare(
    wash_maint: pd.DataFrame,
    onwing_df: pd.DataFrame,
    aircraft_reg: dict[str, str],
    engine_labels: dict[str, str],
) -> dict:
    """Build the flat wash-event dataframe and the filter options."""
    ts = pd.to_datetime(wash_maint["maint_datetime"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)

    current = onwing_df[onwing_df["removal_datetime"].isna()]
    engine_to_aircraft = current.set_index("engine_id")[["aircraft_id", "engine_position"]]
    engine_family = (
        onwing_df.dropna(subset=["aircraft_family"])
        .sort_values("install_datetime")
        .drop_duplicates("engine_id", keep="last")
        .set_index("engine_id")["aircraft_family"]
    )

    df = pd.DataFrame({
        "engine_id_str": wash_maint["engine_id_str"].values,
        "maint_datetime": ts.values,
        "ata_code": wash_maint["ata_code"].astype(str).values,
    })
    df["aircraft_id"] = df["engine_id_str"].map(engine_to_aircraft["aircraft_id"])
    df["engine_position"] = df["engine_id_str"].map(engine_to_aircraft["engine_position"])
    df["aircraft_family"] = df["engine_id_str"].map(engine_family)
    df["aircraft_reg"] = (
        df["aircraft_id"].map(aircraft_reg).fillna(df["aircraft_id"])
    ).fillna(UNINSTALLED)

    fallback = df.apply(
        lambda r: f"{r['engine_id_str']} — {r['aircraft_family']} (uninstalled)"
        if pd.notna(r["aircraft_family"]) else r["engine_id_str"],
        axis=1,
    )
    df["engine_label"] = df["engine_id_str"].map(engine_labels).fillna(fallback)

    ata_codes = sorted(df["ata_code"].unique())
    regs = sorted(r for r in df["aircraft_reg"].unique() if r != UNINSTALLED)
    if (df["aircraft_reg"] == UNINSTALLED).any():
        regs.append(UNINSTALLED)

    return {
        "df": df,
        "ata_codes": ata_codes,
        "aircraft_options": regs,
        "ata_color": {a: _ATA_PALETTE[i % len(_ATA_PALETTE)] for i, a in enumerate(ata_codes)},
        "date_min": df["maint_datetime"].min().date(),
        "date_max": df["maint_datetime"].max().date(),
    }


def _controls_card(state: dict) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.H6("Wash Schedule Filters", className="fw-bold mb-2"),

            dbc.Label("Aircraft", class_name="small fw-semibold mb-0"),
            dcc.Dropdown(
                id="gantt-aircraft",
                options=[{"label": a, "value": a} for a in state["aircraft_options"]],
                multi=True, placeholder="All aircraft", className="mb-2",
            ),

            dbc.Label("ATA code", class_name="small fw-semibold mb-0"),
            dcc.Dropdown(
                id="gantt-ata",
                options=[{"label": f"ATA {a}", "value": a} for a in state["ata_codes"]],
                multi=True, placeholder="All codes", className="mb-2",
            ),

            dbc.Label("Date Range", class_name="small fw-semibold mb-0"),
            dcc.DatePickerRange(
                id="gantt-date",
                min_date_allowed=state["date_min"],
                max_date_allowed=state["date_max"],
                start_date=state["date_min"],
                end_date=state["date_max"],
                display_format="YYYY-MM-DD",
                className="mb-2 d-block",
            ),

            html.Div(id="gantt-summary", className="small text-muted mt-2"),
        ], className="p-2"),
    )


def _layout(state: dict) -> dbc.Row:
    return dbc.Row(
        [
            dcc.Store(id="gantt-store"),
            dbc.Col(
                _controls_card(state), width=3, className="pt-3",
                style={"overflowY": "auto", "maxHeight": "100vh"},
            ),
            dbc.Col(
                dcc.Loading(
                    children=html.Div(id="gantt-container"),
                    type="circle",
                ),
                width=9, className="pt-3",
                style={"overflowY": "auto", "maxHeight": "100vh"},
            ),
        ],
        style={"minHeight": "100vh"},
    )


def _build_figure(df: pd.DataFrame, ata_color: dict[str, str]) -> tuple[go.Figure, list[str]]:
    eng_order = (
        df.drop_duplicates("engine_id_str")
        .assign(
            _sort_reg=lambda d: d["aircraft_reg"].fillna("zzz"),
            _sort_pos=lambda d: d["engine_position"].fillna(99),
        )
        .sort_values(["_sort_reg", "_sort_pos", "engine_id_str"])
        ["engine_label"].tolist()
    )

    fig = go.Figure()

    for eng_label, grp in df.groupby("engine_label"):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("maint_datetime")
        fig.add_trace(go.Scatter(
            x=grp["maint_datetime"], y=[eng_label] * len(grp),
            mode="lines", line=dict(color="rgba(128,128,128,0.35)", width=1),
            showlegend=False, hoverinfo="skip",
        ))

    for ata in sorted(df["ata_code"].unique()):
        sub = df[df["ata_code"] == ata]
        fig.add_trace(go.Scatter(
            x=sub["maint_datetime"], y=sub["engine_label"],
            mode="markers",
            marker=dict(size=9, color=ata_color.get(ata, "#888"),
                        line=dict(color="white", width=0.5)),
            name=f"ATA {ata}",
            hovertemplate=(
                "<b>%{y}</b><br>%{x|%Y-%m-%d}<br>ATA " + ata + "<extra></extra>"
            ),
        ))

    chart_height = max(420, 18 * len(eng_order) + 140)
    fig.update_layout(
        yaxis=dict(categoryorder="array", categoryarray=eng_order,
                   title="", automargin=True, tickfont=dict(size=10)),
        xaxis=dict(title="Date", type="date"),
        height=chart_height,
        margin=dict(t=48, r=20, b=40, l=20),
        hovermode="closest",
        legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"),
        title=dict(
            text=f"Wash schedule — {len(df)} events across {len(eng_order)} engines",
            font=dict(size=14), x=0, xanchor="left",
        ),
    )
    return fig, eng_order


def _register_callbacks(app, state: dict) -> None:
    wash_gantt = state["df"]
    ata_color = state["ata_color"]

    @app.callback(
        Output("gantt-store", "data"),
        Output("gantt-summary", "children"),
        Input("gantt-aircraft", "value"),
        Input("gantt-ata", "value"),
        Input("gantt-date", "start_date"),
        Input("gantt-date", "end_date"),
    )
    def compute_gantt(aircraft_filter, ata_filter, start_date, end_date):
        df = wash_gantt
        if aircraft_filter:
            df = df[df["aircraft_reg"].isin(aircraft_filter)]
        if ata_filter:
            df = df[df["ata_code"].isin(ata_filter)]
        if start_date:
            df = df[df["maint_datetime"] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df["maint_datetime"] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]

        if df.empty:
            return {"type": "empty"}, "No events match the filters."

        fig, eng_order = _build_figure(df, ata_color)
        return (
            {"type": "figure", "figure": fig.to_dict(), "height": fig.layout.height},
            f"{len(df):,} events across {len(eng_order)} engines.",
        )

    @app.callback(
        Output("gantt-container", "children"),
        Input("gantt-store", "data"),
        Input("theme-store", "data"),
    )
    def render_gantt(data, is_dark):
        if not data or data.get("type") != "figure":
            return dbc.Alert("No events match the filters.", color="info", className="mt-3")
        fig = go.Figure(data["figure"])
        fig.update_layout(template="plotly_dark" if is_dark else "plotly_white")
        height = data.get("height", 600)
        return dcc.Graph(
            figure=fig,
            config={"displayModeBar": True, "responsive": True},
            style={"height": f"{height}px"},
        )


def build(
    app,
    *,
    wash_maint: pd.DataFrame,
    onwing_df: pd.DataFrame,
    aircraft_reg: dict[str, str],
    engine_labels: dict[str, str],
) -> dbc.Row:
    """Register the Wash Schedule tab on ``app`` and return its layout."""
    state = _prepare(wash_maint, onwing_df, aircraft_reg, engine_labels)
    _register_callbacks(app, state)
    return _layout(state)
