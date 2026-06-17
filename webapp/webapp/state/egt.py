"""State for the EGT Indication page.

View of the EGT probe failure ML predictions
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import reflex as rx
from plotly.subplots import make_subplots

from enginewash import predict_egt_failure

from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for, maint_events_for_ata
from ..data.egt_indication import (
    EGT_FAILURE_ENGINES,
    EGT_PREDICTION_ENGINES,
    failure_spans_for,
)
from .base import GlobalState

_AIRCRAFT_TYPE = "B737"

_PARAMS = ["EGTHDM", "DEGT", "GWFM"]
_PARAM_COLORS = {"EGTHDM": "#1f77b4", "DEGT": "#1f77b4", "GWFM": "#1f77b4"}

_SMOOTH_WINDOW = 30

# Show ATA markers up to this many days before the first flight (context).
_ATA_GRACE_DAYS = 60

# Defaults for the simple heuristic EGT-failure model.
_DEFAULT_EGTHDM_THRESHOLD = 10.0
_DEFAULT_LOOKBACK_CYCLES = 30


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

    # Simple heuristic-model parameters.
    egthdm_threshold: float = _DEFAULT_EGTHDM_THRESHOLD
    lookback_cycles: int = _DEFAULT_LOOKBACK_CYCLES

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
    async def set_egthdm_threshold(self, value: str):
        try:
            self.egthdm_threshold = float(value)
        except (TypeError, ValueError):
            return
        if self.selected_engine_id:
            await self._build_chart()

    @rx.event
    async def set_lookback_cycles(self, value: str):
        try:
            self.lookback_cycles = max(1, int(float(value)))
        except (TypeError, ValueError):
            return
        if self.selected_engine_id:
            await self._build_chart()

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

        # Track the span actually covered by flight data, so out-of-range
        # markers (e.g. an ATA event predating the data) don't stretch the axis.
        data_min: Optional[datetime] = None
        data_max: Optional[datetime] = None

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

            xs = [f.flight_datetime for f in flights]
            ys = [f.float_value for f in flights]

            if xs:
                data_min = xs[0] if data_min is None else min(data_min, xs[0])
                data_max = xs[-1] if data_max is None else max(data_max, xs[-1])

            fig.add_trace(
                go.Scattergl(
                    x=xs,
                    y=ys,
                    mode="markers",
                    name=pname,
                    marker={"size": 3, "color": "#888", "opacity": 0.25},
                ),
                row=i,
                col=1,
            )

            smoothed = pd.Series(ys).rolling(_SMOOTH_WINDOW, center=True, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=smoothed.tolist(),
                    mode="lines",
                    name=f"{pname} smooth",
                    line={"color": color, "width": 1.5},
                    opacity=0.9,
                ),
                row=i,
                col=1,
            )

            # Overlay the simple heuristic model's predicted failures on EGTHDM.
            if pname == "EGTHDM":
                predictions = predict_egt_failure(
                    eid,
                    flights,
                    egthdm_threshold=self.egthdm_threshold,
                    lookback_cycles=self.lookback_cycles,
                    smooth_window=_SMOOTH_WINDOW,
                )
                if predictions:
                    px, py = zip(*predictions)
                    fig.add_trace(
                        go.Scatter(
                            x=list(px),
                            y=list(py),
                            mode="markers",
                            name="Model prediction",
                            marker={"symbol": "x", "size": 7, "color": "red"},
                        ),
                        row=i,
                        col=1,
                    )

            fig.update_yaxes(title_text=pname, row=i, col=1)

        # Maintenance events (ATA 223/224) as dotted vertical lines. Skip events
        # outside the flight-data span (with a small grace window before the
        # first flight) — they'd otherwise stretch the x-axis.
        ata_lo = data_min - pd.Timedelta(days=_ATA_GRACE_DAYS) if data_min is not None else None
        for dt, ata in sorted(maint_events_for_ata(bundle, eid, ["223", "224"]), key=lambda x: x[0]):
            if ata_lo is not None and (dt < ata_lo or dt > data_max):
                continue
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
            title=f"{label} — EGT probe failure prediction",
            margin={"l": 60, "r": 20, "t": 60, "b": 40},
            height=720,
            showlegend=False,
        )
        self.chart_figure = fig
        self.has_chart = True
