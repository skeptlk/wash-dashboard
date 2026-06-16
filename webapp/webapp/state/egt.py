"""State for the EGT Indication page.

Boeing-only view of the EGT-sensor failure ML predictions. For a selected
engine it charts EGTHDM, DEGT and GWFM (values from the Boeing parquet files —
the source of truth) and shades the time spans the model predicts as failing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx
from plotly.subplots import make_subplots

from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for, maint_events_for_ata
from ..data.egt_indication import (
    EGT_FAILURE_ENGINES,
    EGT_PREDICTION_ENGINES,
    failure_spans_for,
)
from ..trends import compute_group_trends
from .base import GlobalState

# Predictions are Boeing-only, so this page is pinned to the B737 bundle.
_AIRCRAFT_TYPE = "B737"

# Charted top-to-bottom; each parameter pulls from its source-of-truth frame
# via flights_for (EGTHDM ← takeoff, DEGT/GWFM ← cruise).
_PARAMS = ["EGTHDM", "DEGT", "GWFM"]
_PARAM_COLORS = {"EGTHDM": "#1f77b4", "DEGT": "#d62728", "GWFM": "#2ca02c"}

# Match the degradation page's segmentation/smoothing.
_SMOOTH_WINDOW = 30
_GROUP_GAP_DAYS = 30.0


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class EgtState(rx.State):
    """Per-page state for the EGT Indication view."""

    selected_engine_id: str = ""
    engine_search: str = ""
    available_engines_labeled: list[dict] = []  # [{"id", "label"}]

    has_chart: bool = False
    chart_figure: go.Figure = go.Figure()

    @rx.var
    def filtered_engines(self) -> list[dict]:
        q = self.engine_search.strip().lower()
        if not q:
            return self.available_engines_labeled
        return [
            e for e in self.available_engines_labeled
            if q in e["label"].lower() or q in e["id"].lower()
        ]

    def _build_engine_list(self) -> None:
        """Engines that have predictions AND exist in the Boeing bundle.

        Engines with at least one predicted failure are listed first.
        """
        bundle = LOADED.get(_AIRCRAFT_TYPE)
        labeled: list[dict] = []
        if bundle is not None:
            avail = set(bundle.available_engines)
            candidates = [eid for eid in EGT_PREDICTION_ENGINES if eid in avail]
            # Failing engines first; preserve id order within each group.
            candidates.sort(key=lambda eid: (eid not in EGT_FAILURE_ENGINES, eid))
            for eid in candidates:
                labeled.append({
                    "id": eid,
                    "label": bundle.engine_labels.get(eid, eid),
                    "has_failure": eid in EGT_FAILURE_ENGINES,
                })
        self.available_engines_labeled = labeled

    @rx.event
    def set_engine_search(self, value: str):
        self.engine_search = value

    @rx.event
    async def on_load(self):
        self._build_engine_list()
        if self.available_engines_labeled and (
            not self.selected_engine_id
            or all(e["id"] != self.selected_engine_id for e in self.available_engines_labeled)
        ):
            self.selected_engine_id = self.available_engines_labeled[0]["id"]
        if self.selected_engine_id:
            await self._build_chart()

    @rx.event
    async def select_engine(self, engine_id: str):
        self.selected_engine_id = engine_id
        await self._build_chart()

    async def _build_chart(self):
        bundle = LOADED.get(_AIRCRAFT_TYPE)
        if bundle is None:
            self.has_chart = False
            return

        gs = await self.get_state(GlobalState)
        start = _parse_date(gs.start_date)
        end = _parse_date(gs.end_date)

        eid = self.selected_engine_id
        label = bundle.engine_labels.get(eid, eid)

        fig = make_subplots(
            rows=len(_PARAMS),
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=_PARAMS,
        )

        for i, pname in enumerate(_PARAMS, start=1):
            param = PARAMETER_BY_NAME[pname]
            color = _PARAM_COLORS[pname]
            flights = flights_for(bundle, eid, param, start=start, end=end)
            flights.sort(key=lambda f: f.flight_datetime)

            # Raw points (faint) so the underlying data stays visible behind the
            # smoothed curve.
            fig.add_trace(
                go.Scattergl(
                    x=[f.flight_datetime for f in flights],
                    y=[f.float_value for f in flights],
                    mode="markers",
                    name=pname,
                    marker={"size": 3, "color": "#888", "opacity": 0.25},
                ),
                row=i,
                col=1,
            )

            # Centered moving-average curve per gap-split segment (as on the
            # degradation page).
            for g in compute_group_trends(
                flights, param, gap_days=_GROUP_GAP_DAYS, smooth_window=_SMOOTH_WINDOW
            ):
                fig.add_trace(
                    go.Scatter(
                        x=list(g.xs),
                        y=list(g.smoothed),
                        mode="lines",
                        name=f"{pname} smooth",
                        line={"color": color, "width": 1.5},
                        opacity=0.9,
                    ),
                    row=i,
                    col=1,
                )

            fig.update_yaxes(title_text=pname, row=i, col=1)

        # Maintenance events (ATA 223/224) as dotted vertical lines.
        for dt, ata in sorted(maint_events_for_ata(bundle, eid, ["223", "224"]), key=lambda x: x[0]):
            fig.add_shape(
                type="line", x0=dt, x1=dt, y0=0, y1=1,
                xref="x", yref="paper",
                line={"color": "darkorchid", "width": 1.2, "dash": "dot"},
                layer="above",
            )
            fig.add_annotation(
                x=dt, y=0.99, xref="x", yref="paper",
                text=f"ATA {ata}", showarrow=False,
                font={"size": 8, "color": "darkorchid"}, yanchor="top",
                textangle=-90,
            )

        # Shade predicted-failure spans across every parameter row.
        for s, e in failure_spans_for(eid, start=start, end=end):
            for i in range(1, len(_PARAMS) + 1):
                fig.add_vrect(
                    x0=s,
                    x1=e,
                    fillcolor="red",
                    opacity=0.15,
                    layer="below",
                    line_width=0,
                    row=i,
                    col=1,
                )

        fig.update_layout(
            title=f"{label} — EGT sensor failure prediction",
            margin={"l": 60, "r": 20, "t": 60, "b": 40},
            height=720,
            showlegend=False,
        )
        self.chart_figure = fig
        self.has_chart = True
