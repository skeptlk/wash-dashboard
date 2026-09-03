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

from enginewash import FlightPhase, FlightRecord, predict_egt_failure_enhanced

from ..data import LOADED
from ..data import egt_params
from ..data import labels as labels_store
from ..data import versions as versions_store
from ..data.derived import install_removal_events_for, maint_events_for_ata
from ..data.egt_indication import (
    EGT_FAILURE_ENGINES,
    EGT_PREDICTION_ENGINES,
    failure_spans_for,
)
from .base import GlobalState

_AIRCRAFT_TYPE = "B737"

_PARAM_COLOR = "#1f77b4"

_SMOOTH_WINDOW = 30

# Rolling robust-dispersion ("noise") companion bar. IQR is robust to outliers,
# unlike std. Hypothesis: data gets noisier around a failure.
_SCATTER_WINDOW = 15


def _rolling_scatter(ys: list[float], window: int = _SCATTER_WINDOW) -> list[float]:
    r = pd.Series(ys, dtype="float64").rolling(
        window, center=True, min_periods=max(2, window // 3)
    )
    return (r.quantile(0.75) - r.quantile(0.25)).tolist()

# Show ATA markers up to this many days before the first flight (context).
_ATA_GRACE_DAYS = 60

# Defaults for the enhanced (EGTHDM + DEGT + decline) failure model, matching
# the tuned run in enhanced_baseline.ipynb.
_DEFAULT_MODEL_PARAMS = {
    "lookback_cycles": 10,
    "egthdm_threshold": 4.85,
    "degt_threshold": 2.70,
    "smoothing_window": 26,
    "decline_window_days": 5.0,
    "decline_min_span_days": 2.0,
    "decline_min_points": 5,
    "decline_threshold": 4.0,
    "decline_min_downward_fraction": 0.75,
    "decline_min_r2": 0.50,
}
_INT_MODEL_PARAMS = {"lookback_cycles", "smoothing_window", "decline_min_points"}


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

    # Enhanced model parameters (collapsed "Model parameters" panel).
    model_params_open: bool = False
    lookback_cycles: int = _DEFAULT_MODEL_PARAMS["lookback_cycles"]
    egthdm_threshold: float = _DEFAULT_MODEL_PARAMS["egthdm_threshold"]
    degt_threshold: float = _DEFAULT_MODEL_PARAMS["degt_threshold"]
    smoothing_window: int = _DEFAULT_MODEL_PARAMS["smoothing_window"]
    decline_window_days: float = _DEFAULT_MODEL_PARAMS["decline_window_days"]
    decline_min_span_days: float = _DEFAULT_MODEL_PARAMS["decline_min_span_days"]
    decline_min_points: int = _DEFAULT_MODEL_PARAMS["decline_min_points"]
    decline_threshold: float = _DEFAULT_MODEL_PARAMS["decline_threshold"]
    decline_min_downward_fraction: float = _DEFAULT_MODEL_PARAMS["decline_min_downward_fraction"]
    decline_min_r2: float = _DEFAULT_MODEL_PARAMS["decline_min_r2"]

    # Which parameters to plot (catalog ids, one subplot each).
    selected_params: list[str] = egt_params.DEFAULT_PARAMS
    param_search: str = ""
    params_open: bool = False
    show_iqr: bool = False

    has_chart: bool = False
    chart_figure: go.Figure = go.Figure()

    # --- Data-labeling state ---
    label_mode: bool = False
    label_start: str = ""
    label_end: str = ""
    label_value: int = 1  # 0 = no failure, 1 = failure
    manual_labels: list[dict] = []  # overlay rows for the selected engine
    export_status: str = ""

    # --- Dataset version selection ---
    # "working" = migrated baseline + editable overlay; otherwise a git sha of a
    # committed dataset snapshot, shown read-only.
    selected_version: str = "working"
    version_options: list[dict] = []  # [{"value", "label"}], incl. "Working (live)"
    version_error: str = ""

    @rx.var
    def filtered_engines(self) -> list[dict]:
        q = self.engine_search.strip().lower()
        if not q:
            return self.available_engines_labeled
        return [
            e for e in self.available_engines_labeled
            if q in e["label"].lower() or q in e["id"].lower()
        ]

    def _param_catalog(self) -> list[dict]:
        bundle = LOADED.get(_AIRCRAFT_TYPE)
        return egt_params.catalog(bundle) if bundle is not None else []

    def _filter_params(self, phase: str) -> list[dict]:
        q = self.param_search.strip().lower()
        return [
            {"id": e["id"], "label": e["name"]}
            for e in self._param_catalog()
            if e["phase"] == phase and (not q or q in e["name"].lower())
        ]

    @rx.var
    def takeoff_param_options(self) -> list[dict]:
        return self._filter_params("TAKEOFF")

    @rx.var
    def cruise_param_options(self) -> list[dict]:
        return self._filter_params("CRUISE")

    def _selected_entries(self) -> list[dict]:
        sel = set(self.selected_params)
        return [e for e in self._param_catalog() if e["id"] in sel]

    @rx.var
    def chart_height(self) -> str:
        return "100vh"

    @rx.event
    def set_param_search(self, value: str):
        self.param_search = value

    @rx.event
    def toggle_params_open(self):
        self.params_open = not self.params_open

    @rx.event
    async def toggle_show_iqr(self, value: bool):
        self.show_iqr = value
        await self._build_chart()

    @rx.event
    async def toggle_param(self, param_id: str, checked: bool):
        selected = [p for p in self.selected_params if p != param_id]
        if checked:
            selected.append(param_id)
        self.selected_params = selected
        if self.selected_engine_id:
            await self._build_chart()

    @rx.event
    async def reset_params(self):
        self.selected_params = list(egt_params.DEFAULT_PARAMS)
        if self.selected_engine_id:
            await self._build_chart()

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
    def toggle_model_params_open(self):
        self.model_params_open = not self.model_params_open

    @rx.event
    async def set_model_param(self, field: str, value: str | list):
        # Number input hands back a string; slider hands back a [value] list.
        if isinstance(value, list):
            value = value[0] if value else None
        try:
            new_value = float(value)
        except (TypeError, ValueError):
            return
        if field in _INT_MODEL_PARAMS:
            new_value = max(1, int(new_value))
        if new_value == getattr(self, field):
            return
        setattr(self, field, new_value)
        if self.selected_engine_id:
            await self._build_chart()

    def _refresh_versions(self) -> None:
        """Rebuild the version dropdown: Working (live) + committed snapshots."""
        opts = [{"value": "working", "label": "Working (live)"}]
        for v in versions_store.list_versions():
            opts.append({"value": v["sha"], "label": v["label"]})
        self.version_options = opts
        # If the selected version vanished (e.g. history rewritten), fall back.
        if all(o["value"] != self.selected_version for o in opts):
            self.selected_version = "working"

    @rx.event
    async def set_version(self, value: str):
        self.selected_version = value or "working"
        self.version_error = ""
        if self.selected_version != "working":
            # Past versions are read-only; leave label mode off.
            self.label_mode = False
        if self.selected_engine_id:
            await self._build_chart()

    @rx.event
    async def on_load(self):
        self._build_engine_list()
        self._refresh_versions()
        if self.available_engines_labeled and (
            not self.selected_engine_id
            or all(e["id"] != self.selected_engine_id for e in self.available_engines_labeled)
        ):
            self.selected_engine_id = self.available_engines_labeled[0]["id"]
        if self.selected_engine_id:
            self._refresh_labels()
            await self._build_chart()

    @rx.event
    async def select_engine(self, engine_id: str):
        self.selected_engine_id = engine_id
        self._refresh_labels()
        await self._build_chart()

    # --- Labeling events ---

    def _refresh_labels(self) -> None:
        if self.selected_engine_id:
            self.manual_labels = labels_store.labels_for(self.selected_engine_id)
        else:
            self.manual_labels = []

    @rx.event
    async def toggle_label_mode(self, value: bool):
        self.label_mode = value
        if self.selected_engine_id:
            await self._build_chart()

    @rx.event
    def set_label_start(self, value: str):
        self.label_start = value

    @rx.event
    def set_label_end(self, value: str):
        self.label_end = value

    @rx.event
    def set_label_value(self, value: str | list[str]):
        # rx.segmented_control's on_change is typed str | list[str]; single-select
        # hands back a plain string.
        v = value[0] if isinstance(value, list) else value
        try:
            self.label_value = 1 if int(v) else 0
        except (TypeError, ValueError):
            self.label_value = 1 if str(v).strip().lower() in ("1", "failure", "true") else 0

    @rx.event
    def on_plot_selected(self, points: list[dict]):
        """Box-select on the chart → set the label range from the points' x-span."""
        xs = [p.get("x") for p in (points or []) if p.get("x") is not None]
        if not xs:
            return
        ts = pd.to_datetime(pd.Series(xs), errors="coerce").dropna()
        if ts.empty:
            return
        # Keep full precision so the exact drag boundaries are stored (the inputs
        # are datetime-local). Format matches the <input type="datetime-local"> value.
        self.label_start = ts.min().strftime("%Y-%m-%dT%H:%M:%S")
        self.label_end = ts.max().strftime("%Y-%m-%dT%H:%M:%S")
        if not self.label_mode:
            self.label_mode = True

    @rx.event
    async def apply_label(self):
        if not self.selected_engine_id:
            self.export_status = "Select an engine first."
            return
        if not self.label_start or not self.label_end:
            self.export_status = "Pick a start and end date (drag-select or type)."
            return
        try:
            changed = labels_store.add_label(
                self.selected_engine_id,
                self.label_start,
                self.label_end,
                self.label_value,
            )
        except ValueError as exc:
            self.export_status = f"Could not apply label: {exc}"
            return
        if changed == 0:
            self.export_status = "No change — those flights are already labeled that way."
        else:
            self.export_status = (
                f"Labeled {changed} observation(s) {self.label_start} → {self.label_end} "
                f"as failure={self.label_value}."
            )
        self._refresh_labels()
        await self._build_chart()

    @rx.event
    async def delete_label(self, row_id: str):
        labels_store.delete_label(row_id)
        self.export_status = "Label removed."
        self._refresh_labels()
        await self._build_chart()

    @rx.event
    def export_dataset(self):
        try:
            summary = labels_store.export_curated()
        except RuntimeError as exc:
            self.export_status = f"Export failed: {exc}"
            return
        ok, out = labels_store.dvc_add()
        base = (
            f"Exported {summary['rows']} rows ({summary['overridden']} overridden) "
            f"to {summary['path']}."
        )
        if ok:
            self.export_status = (
                base
                + " DVC pointers updated — commit `egt-failure-dataset/data/*.dvc`, "
                "then run `cd egt-failure-dataset && dvc push` to publish."
            )
        else:
            self.export_status = base + f" (dvc add skipped: {out})"

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
            lookback_cycles=self.lookback_cycles,
            egthdm_threshold=self.egthdm_threshold,
            degt_threshold=self.degt_threshold,
            smoothing_window=self.smoothing_window,
            decline_window_days=self.decline_window_days,
            decline_min_span_days=self.decline_min_span_days,
            decline_min_points=self.decline_min_points,
            decline_threshold=self.decline_threshold,
            decline_min_downward_fraction=self.decline_min_downward_fraction,
            decline_min_r2=self.decline_min_r2,
        )

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

        entries = self._selected_entries()
        if not entries:
            self.has_chart = False
            return
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
            # Keep spacing valid (plotly caps it at 1/(rows-1)) as row count grows.
            vertical_spacing=min(0.05, 0.8 / max(1, nrows - 1)),
            subplot_titles=titles,
        )

        for i, entry in enumerate(entries, start=1):
            pname = entry["name"]
            xs, ys = egt_params.series_for(bundle, eid, entry, start=start, end=end)

            if xs:
                data_min = xs[0] if data_min is None else min(data_min, xs[0])
                data_max = xs[-1] if data_max is None else max(data_max, xs[-1])

            fig.add_trace(
                go.Scattergl(
                    x=xs,
                    y=ys,
                    mode="markers",
                    name=pname,
                    marker={"size": 5, "color": "#888", "opacity": 0.45},
                    selected={"marker": {"size": 9, "opacity": 0.9}},
                    unselected={"marker": {"opacity": 0.2}},
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
                    line={"color": _PARAM_COLOR, "width": 1.5},
                    opacity=0.9,
                ),
                row=i,
                col=1,
            )

            # Rolling robust dispersion (noise proxy) as bars on the same axis,
            # baseline-shifted to sit just under the data so it's readable.
            if self.show_iqr:
                scatter = _rolling_scatter(ys)
                base = min((v for v in ys if v == v), default=0.0)
                bar_kwargs = {
                    "x": xs,
                    "y": scatter,
                    "base": base,
                    "name": f"{pname} noise (IQR {_SCATTER_WINDOW})",
                    "marker": {"color": "#ff7f0e", "opacity": 0.35, "line": {"width": 0}},
                }
                if len(xs) > 1:
                    gap_ms = pd.Series(xs).diff().dt.total_seconds().median() * 1000
                    if gap_ms == gap_ms:  # not NaN
                        bar_kwargs["width"] = gap_ms * 0.5
                fig.add_trace(go.Bar(**bar_kwargs), row=i, col=1)

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

        # Install/removal points from the onwing history, same grace/clip rule as ATA.
        _EVENT_COLOR = {"Install": "#2ca02c", "Removal": "#d62728"}
        for dt, kind, reason in sorted(
            install_removal_events_for(bundle, eid), key=lambda x: x[0]
        ):
            if ata_lo is not None and (dt < ata_lo or dt > data_max):
                continue
            color = _EVENT_COLOR[kind]
            fig.add_shape(
                type="line", x0=dt, x1=dt, y0=0, y1=1,
                xref="x", yref="paper",
                line={"color": color, "width": 1.2, "dash": "dashdot"},
                layer="above",
            )
            event_label = f"{kind}" + (f" ({reason})" if reason else "")
            fig.add_annotation(
                x=dt, y=0.01, xref="x", yref="paper",
                text=event_label, showarrow=False,
                font={"size": 8, "color": color}, yanchor="bottom",
                textangle=-90,
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
                self.version_error = str(exc)
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
            title=title,
            margin={"l": 50, "r": 10, "t": 50, "b": 30},
            autosize=True,
            showlegend=True,
            dragmode="select" if self.label_mode else "zoom",
        )
        fig.update_xaxes(tickformat="%Y-%m-%d", ticks="outside")
        self.chart_figure = fig
        self.has_chart = True
