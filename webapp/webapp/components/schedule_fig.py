"""Pure helpers for the Wash Schedule Gantt (ported from dashboard/schedule.py)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from ..data.aircraft_registry import AIRCRAFT_REG

UNINSTALLED = "— uninstalled —"

_ATA_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

_AC_FAMILY_ORDER = {"A": 0, "B": 1, "E": 2}


def _label_family_key(label: str) -> int:
    try:
        family = label.split(" — ", 1)[1].split()[0]
        return _AC_FAMILY_ORDER.get(family[:1].upper(), 3)
    except (IndexError, AttributeError):
        return 3


def prepare_schedule(bundle) -> dict:
    """Build the flat wash-event DataFrame and filter options for a bundle.

    Returns a dict with keys: df, ata_codes, aircraft_options, ata_color.
    """
    wash_maint = bundle.wash_maint
    onwing_df = bundle.onwing_df
    engine_labels = bundle.engine_labels

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
        df["aircraft_id"].map(AIRCRAFT_REG).fillna(df["aircraft_id"])
    ).fillna(UNINSTALLED)

    fallback = df.apply(
        lambda r: (
            f"{r['engine_id_str']} — {r['aircraft_family']} (uninstalled)"
            if pd.notna(r["aircraft_family"])
            else r["engine_id_str"]
        ),
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
    }


# Theme-neutral structural styling only — no template / bg / font colours, so
_GRID = "rgba(127,127,127,0.18)"
_FONT = "Inter, Arial, sans-serif"
_ROW_PX = 22


def _filter_df(
    df: pd.DataFrame,
    aircraft_filter: Optional[list[str]],
    ata_filter: Optional[list[str]],
    start: Optional[datetime],
    end: Optional[datetime],
) -> pd.DataFrame:
    if aircraft_filter:
        df = df[df["aircraft_reg"].isin(aircraft_filter)]
    if ata_filter:
        df = df[df["ata_code"].isin(ata_filter)]
    if start:
        df = df[df["maint_datetime"] >= pd.Timestamp(start)]
    if end:
        df = df[df["maint_datetime"] <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    return df


def _engine_order(df: pd.DataFrame) -> list[str]:
    return (
        df.drop_duplicates("engine_id_str")
        .assign(
            _sort_family=lambda d: d["engine_label"].map(_label_family_key),
            _sort_reg=lambda d: d["aircraft_reg"].fillna("zzz"),
            _sort_pos=lambda d: d["engine_position"].fillna(99),
        )
        .sort_values(
            ["_sort_family", "_sort_reg", "_sort_pos", "engine_id_str"],
            ascending=[False, True, True, True],
        )["engine_label"]
        .tolist()
    )


def build_main_figure(
    df: pd.DataFrame,
    ata_color: dict,
    eng_order: list[str],
    x_range: Optional[list] = None,
) -> go.Figure:
    """Tall per-engine chart (no rangeslider) — meant for a scrollable container.

    Its height grows with the engine count so every row stays readable; the time
    window is controlled externally via ``x_range`` (set from the navigator).
    """
    fig = go.Figure()

    # Thin connector lines between events per engine
    for eng_label, grp in df.groupby("engine_label"):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("maint_datetime")
        eid = grp["engine_id_str"].iloc[0]
        fig.add_trace(go.Scatter(
            x=grp["maint_datetime"],
            y=[eng_label] * len(grp),
            mode="lines",
            line={"color": "rgba(99,110,131,0.45)", "width": 1},
            showlegend=False,
            hoverinfo="skip",
            customdata=[eid] * len(grp),
        ))

    # Coloured dots per ATA code
    for ata in sorted(df["ata_code"].unique()):
        sub = df[df["ata_code"] == ata]
        fig.add_trace(go.Scatter(
            x=sub["maint_datetime"],
            y=sub["engine_label"],
            mode="markers",
            marker={
                "size": 11,
                "color": ata_color.get(ata, "#888"),
                "line": {"color": "rgba(8,48,107,0.55)", "width": 1.2},
                "opacity": 0.95,
            },
            name=f"ATA {ata}",
            customdata=sub["engine_id_str"].tolist(),
            hovertemplate="<b>%{y}</b><br>%{x|%Y-%m-%d}<br>ATA " + ata + "<extra></extra>",
        ))

    chart_height = max(360, _ROW_PX * len(eng_order) + 100)
    xaxis = {
        "title": "",
        "type": "date",
        "side": "top",
        "showgrid": True,
        "gridcolor": _GRID,
        "dtick": "M1",
        "tickformat": "%b %Y",
        "ticklabelmode": "period",
        "tickson": "boundaries",
        "ticks": "outside",
        "ticklen": 6,
        "tickcolor": _GRID,
        "tickfont": {"family": _FONT, "size": 11},
    }
    if x_range:
        xaxis["range"] = x_range
        xaxis["autorange"] = False
    fig.update_layout(
        yaxis={
            "categoryorder": "array",
            "categoryarray": eng_order,
            "title": "",
            "automargin": True,
            "showgrid": True,
            "gridcolor": _GRID,
            "ticklen": 6,
            "tickcolor": "rgba(0,0,0,0)",
            "tickfont": {"family": _FONT, "size": 10},
        },
        xaxis=xaxis,
        height=chart_height,
        margin={"t": 44, "r": 24, "b": 8, "l": 24},
        hovermode="closest",
        showlegend=False,
    )
    return fig



def build_nav_figure(df: pd.DataFrame, ata_color: dict) -> go.Figure:
    """The timeline scrubber: a compact plain rangeslider + quick-range buttons.

    Deliberately *not* a chart — a single invisible trace defines the date
    extent so the slider spans all events, and the area above it is left blank
    (no duplicate "mini chart"). The quick-range buttons and an ATA colour
    legend sit in the top margin. Dragging the slider (or a button) pans/zooms
    the tall main chart via ``on_relayout`` → ``sync_time_window``.
    """
    xs = df["maint_datetime"]
    x0, x1 = xs.min(), xs.max()

    fig = go.Figure()
    # Invisible trace: only there to give the rangeslider its full date extent.
    fig.add_trace(go.Scatter(
        x=[x0, x1], y=[0, 0], mode="markers",
        marker={"opacity": 0}, hoverinfo="skip", showlegend=False,
    ))
    # Legend-only swatches (no data) so ATA colours stay documented without
    # drawing anything in the slider.
    for ata in sorted(df["ata_code"].unique()):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker={"size": 9, "color": ata_color.get(ata, "#888")},
            name=f"ATA {ata}",
        ))

    fig.update_layout(
        yaxis={"visible": False, "fixedrange": True, "range": [-1, 1]},
        xaxis={
            "title": "",
            "type": "date",
            "showline": False,
            "zeroline": False,
            "rangeslider": {
                "visible": True,
                "thickness": 1.0,
                "borderwidth": 1,
                "autorange": True,
            },
        },
        height=110,
        margin={"t": 0, "r": 0, "b": 0, "l": 0},
        hovermode=False,
        legend={
            "orientation": "h",
            "y": 1.0,
            "x": 1,
            "xanchor": "right",
            "yanchor": "bottom",
            "title": "",
            "font": {"family": _FONT, "size": 12},
        },
    )
    return fig


def build_schedule_figures(
    df: pd.DataFrame,
    ata_color: dict,
    aircraft_filter: Optional[list[str]] = None,
    ata_filter: Optional[list[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> tuple[go.Figure, go.Figure, int]:
    """Filter and build (main_figure, nav_figure, n_events)."""
    df = _filter_df(df, aircraft_filter, ata_filter, start, end)
    if df.empty:
        empty = go.Figure()
        empty.update_layout(title="No events match the filters.", height=300)
        return empty, go.Figure(), 0

    eng_order = _engine_order(df)
    return build_main_figure(df, ata_color, eng_order), build_nav_figure(df, ata_color), len(df)
