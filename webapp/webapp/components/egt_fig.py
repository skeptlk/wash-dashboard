"""Build EGT figures from a snapshot of controls, without accessing Reflex state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from enginewash import FlightPhase, FlightRecord, predict_egt_failure_enhanced

from ..data import egt_params
from ..data import labels as labels_store
from ..data import versions as versions_store
from ..data.derived import install_removal_events_for, maint_events_for_ata
from ..data.egt_indication import failure_spans_for

if TYPE_CHECKING:
    from ..data.loader import AircraftBundle

_PARAM_COLOR = "#3b82f6"
_ATA_GRACE_DAYS = 60


@dataclass(frozen=True)
class EgtChartRequest:
    bundle: AircraftBundle | None  # Shared read-only frames; never copy the dataset.
    selected_engine_id: str
    entries: tuple[dict, ...]
    model_params: dict[str, int | float]
    start: Optional[datetime]
    end: Optional[datetime]
    selected_version: str
    label_mode: bool
    timeline_start: str
    timeline_end: str

    def _model_predictions(self, bundle, eid: str) -> list[tuple[datetime, float]]:
        """Enhanced-model predictions over the engine's full history.

        Needs the full EGTHDM/DEGT series (not the user's date-range filter)
        so the lookback/decline windows have enough history to compare against.
        """
        catalog = egt_params.catalog(bundle)
        egthdm_entry = next((e for e in catalog if e["id"] == egt_params.EGTHDM_TAKEOFF_ID), None)
        degt_entry = next((e for e in catalog if e["id"] == egt_params.DEGT_CRUISE_ID), None)
        if egthdm_entry is None:
            return []
        ex, ey = egt_params.series_for(bundle, eid, egthdm_entry)
        dx, dy = egt_params.series_for(bundle, eid, degt_entry) if degt_entry else ([], [])
        egthdm_records = [
            FlightRecord(
                engine_id=eid, flight_datetime=x,
                parameter_name="EGTHDM", flight_phase=FlightPhase.TAKEOFF,
                float_value=float(y),
            )
            for x, y in zip(ex, ey)
        ]
        degt_records = [
            FlightRecord(
                engine_id=eid, flight_datetime=x,
                parameter_name="DEGT", flight_phase=FlightPhase.CRUISE,
                float_value=float(y),
            )
            for x, y in zip(dx, dy)
        ]
        return predict_egt_failure_enhanced(
            eid,
            egthdm_records,
            degt_records,
            **self.model_params,
        )

    def build(self) -> tuple[go.Figure | None, str]:
        bundle = self.bundle
        if bundle is None:
            return None, ""

        start, end = self.start, self.end
        version_error = ""
        smoothing_window = self.model_params["smoothing_window"]

        eid = self.selected_engine_id
        label = bundle.engine_labels.get(eid, eid)

        entries = self.entries
        if not entries:
            return None, ""
        nrows = len(entries)

        # Track the span actually covered by flight data, so out-of-range
        # markers (e.g. an ATA event predating the data) don't stretch the axis.
        data_min: Optional[datetime] = None
        data_max: Optional[datetime] = None

        model_predictions = (
            self._model_predictions(bundle, eid)
            if any(e["id"] == egt_params.EGTHDM_TAKEOFF_ID for e in entries)
            else []
        )

        titles = [f"{e['name']} ({e['phase'].title()})" for e in entries]
        fig = make_subplots(
            rows=nrows,
            cols=1,
            shared_xaxes=True,
            # Invisible secondary axes anchor events inside each chart without
            # changing its measurement scale, including when the user zooms.
            specs=[[{"secondary_y": True}] for _ in entries],
            vertical_spacing=min(0.085, 0.7 / max(1, nrows - 1)),
            subplot_titles=titles,
        )
        fig.update_annotations(x=0, xanchor="left", font_size=12, yshift=3)

        for i, entry in enumerate(entries, start=1):
            pname = entry["name"]
            xs, ys, smoothed = egt_params.smoothed_series_for(
                bundle, eid, entry, smoothing_window, start=start, end=end,
            )

            if xs:
                data_min = xs[0] if data_min is None else min(data_min, xs[0])
                data_max = xs[-1] if data_max is None else max(data_max, xs[-1])

            fig.add_trace(
                go.Scattergl(
                    x=egt_params.plotly_timestamps(xs),
                    y=np.asarray(ys, dtype=np.float64),
                    mode="markers",
                    name="Actual",
                    legendgroup="readings",
                    showlegend=i == 1,
                    meta="reading",
                    hovertemplate=f"%{{x|%d.%m.%y, %H:%M:%S}}<br>{pname}: %{{y:.2f}}<extra></extra>",
                    marker={"size": 3, "color": _PARAM_COLOR, "opacity": 0.4},
                    selected={"marker": {"size": 5, "opacity": 0.9}},
                    unselected={"marker": {"opacity": 0.2}},
                ),
                row=i,
                col=1,
            )

            line_x, line_y, gaps = egt_params.line_with_gaps(xs, smoothed)
            fig.add_trace(
                go.Scatter(
                    x=egt_params.plotly_timestamps(line_x),
                    y=np.asarray(line_y, dtype=np.float64),
                    connectgaps=False,
                    mode="lines",
                    name=f"Smoothed (window={smoothing_window})",
                    legendgroup="smooth",
                    showlegend=i == 1,
                    hovertemplate=f"%{{x|%d.%m.%y, %H:%M:%S}}<br>{pname} average: %{{y:.2f}}<extra></extra>",
                    line={"color": _PARAM_COLOR, "width": 1.5},
                    opacity=0.9,
                ),
                row=i,
                col=1,
            )

            for gap_start, gap_end in gaps:
                fig.add_vrect(
                    x0=gap_start, x1=gap_end,
                    fillcolor="rgba(128,128,128,0.05)",
                    line_width=0, layer="below", row=i, col=1,
                    annotation_text="No data",
                    annotation_position="inside",
                    annotation_font={"size": 9, "color": "#888"},
                    annotation_textangle=-90,
                )

            # Overlay the enhanced model's predicted failures on takeoff EGTHDM.
            if entry["id"] == egt_params.EGTHDM_TAKEOFF_ID and model_predictions:
                visible = [
                    (t, v) for t, v in model_predictions
                    if (start is None or t >= start) and (end is None or t <= end)
                ]
                if visible:
                    px, py = zip(*visible)
                    fig.add_trace(
                        go.Scatter(
                            x=egt_params.plotly_timestamps(px),
                            y=np.asarray(py, dtype=np.float64),
                            mode="markers",
                            name="Prediction",
                            hovertemplate="%{x|%d.%m.%y, %H:%M:%S}<br>Predicted failure: %{y:.2f}<extra></extra>",
                            marker={"symbol": "x", "size": 7, "color": "red"},
                        ),
                        row=i,
                        col=1,
                    )

        # Maintenance events (ATA 223/224) as dotted vertical lines. Skip events
        # outside the flight-data span (with a small grace window before the
        # first flight) — they'd otherwise stretch the x-axis.
        ata_lo = data_min - pd.Timedelta(days=_ATA_GRACE_DAYS) if data_min is not None else None
        events: dict[str, list[tuple]] = {"ATA 223": [], "ATA 224": [], "Install": [], "Removal": []}
        for dt, ata in sorted(maint_events_for_ata(bundle, eid, ["223", "224"]), key=lambda x: x[0]):
            if ata_lo is not None and (dt < ata_lo or dt > data_max):
                continue
            events[f"ATA {ata}"].append((dt, f"ATA {ata}"))

        # Install/removal points from the onwing history, same grace/clip rule as ATA.
        for dt, kind, reason in sorted(
            install_removal_events_for(bundle, eid), key=lambda x: x[0]
        ):
            if ata_lo is not None and (dt < ata_lo or dt > data_max):
                continue
            event_label = f"{kind}" + (f" ({reason})" if reason else "")
            events[kind].append((dt, event_label))

        for kind, color, symbol, position in [
            ("ATA 223", "#a855f7", "diamond", 0.96),
            ("ATA 224", "#a855f7", "diamond-open", 0.96),
            ("Install", "#2ca02c", "triangle-up", 0.96),
            ("Removal", "#d62728", "triangle-down", 0.83),
        ]:
            points = events[kind]
            for i in range(1, nrows + 1):
                fig.add_trace(
                    go.Scatter(
                        x=egt_params.plotly_timestamps([dt for dt, _ in points]),
                        y=[position] * len(points),
                        customdata=[text for _, text in points],
                        mode="markers",
                        name=kind,
                        showlegend=False,
                        marker={"color": color, "symbol": symbol, "size": 7},
                        hovertemplate="%{customdata}<br>%{x|%d.%m.%y, %H:%M}<extra></extra>",
                    ),
                    row=i, col=1, secondary_y=True,
                )
                for dt, _ in points:
                    fig.add_shape(
                        type="line", x0=dt, x1=dt, y0=0, y1=1,
                        yref="y domain",
                        line={"color": color, "width": 1, "dash": "dot"},
                        opacity=0.4, layer="below", row=i, col=1,
                    )

        if self.selected_version == "working":
            # Live view: migrated baseline (light red) + editable manual overlay.
            for s, e in failure_spans_for(eid, start=start, end=end):
                for i in range(1, nrows + 1):
                    fig.add_vrect(
                        x0=s, x1=e, fillcolor="red", opacity=0.15,
                        layer="below", line_width=0, row=i, col=1,
                    )
            # Manual labels, distinct from baseline spans:
            # green = cleared (failure 0), solid red outline = failure 1.
            for s, e, val in labels_store.manual_spans_for(eid, start=start, end=end):
                color = "#d62728" if val == 1 else "#2ca02c"
                for i in range(1, nrows + 1):
                    fig.add_vrect(
                        x0=s, x1=e, fillcolor=color, opacity=0.22,
                        layer="below", line_width=1, line_color=color, row=i, col=1,
                    )
        else:
            # Read-only past version: shade from the snapshot's failure_value.
            try:
                spans = versions_store.failure_spans_for_version(
                    self.selected_version, eid, start=start, end=end
                )
            except RuntimeError as exc:
                version_error = str(exc)
                spans = []
            for s, e in spans:
                for i in range(1, nrows + 1):
                    fig.add_vrect(
                        x0=s, x1=e, fillcolor="red", opacity=0.15,
                        layer="below", line_width=1, line_color="#d62728",
                        row=i, col=1,
                    )

        title = f"{label} — EGT probe failure prediction"
        if self.selected_version != "working":
            title += f"  ·  version {self.selected_version[:7]}"
        fig.update_layout(
            template="plotly_white",
            title={
                "text": title, "font": {"size": 15}, "x": 0.01,
                "y": 1, "yanchor": "top", "pad": {"t": 8},
            },
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 66, "r": 16, "t": 70, "b": 38},
            font={"family": "Inter, system-ui, sans-serif", "size": 11},
            legend={
                "orientation": "h", "x": 1, "xanchor": "right",
                "y": 1, "yanchor": "bottom",
            },
            autosize=True,
            showlegend=True,
            dragmode="select" if self.label_mode else "zoom",
        )
        fig.update_xaxes(
            type="date",
            tickformat="%d.%m.%y", showticklabels=True, domain=[0, 1],
            range=[self.timeline_start, self.timeline_end] if self.timeline_start else None,
            autorange=not bool(self.timeline_start),
            ticks="outside", ticklen=3,
            gridcolor="rgba(128,128,128,0.12)", zeroline=False,
        )
        fig.update_yaxes(
            gridcolor="rgba(128,128,128,0.15)", zeroline=False, nticks=5,
        )
        fig.update_yaxes(
            range=[0, 1], fixedrange=True, visible=False, secondary_y=True,
        )
        return fig, version_error
