"""State for the EGT Indication page.

View of the EGT probe failure ML predictions
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import re
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import reflex as rx


from ..data import LOADED
from ..data import egt_params
from ..data import labels as labels_store
from ..data import versions as versions_store
from ..components.egt_fig import EgtChartRequest
from ..data.egt_indication import (
    EGT_FAILURE_ENGINES,
    EGT_PREDICTION_ENGINES,
)
from .base import GlobalState

_AIRCRAFT_TYPE = "B737"

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
    timeline_start: str = ""
    timeline_end: str = ""
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

    has_chart: bool = False
    is_computing: bool = False
    chart_error: str = ""
    chart_rows: int = 0
    _chart_revision: int = 0
    _chart_worker_running: bool = False
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
        # The default three rows fit the viewport; extra rows scroll locally.
        rows = self.chart_rows
        return "100%" if rows <= 3 else f"max(100%, {rows * 180 + 150}px)"

    @rx.event
    def set_param_search(self, value: str):
        self.param_search = value

    @rx.event
    def toggle_params_open(self):
        self.params_open = not self.params_open

    @rx.event
    async def toggle_param(self, param_id: str, checked: bool):
        selected = [p for p in self.selected_params if p != param_id]
        if checked:
            selected.append(param_id)
        self.selected_params = selected
        if self.selected_engine_id:
            async for update in self._refresh_chart():
                yield update

    @rx.event
    async def reset_params(self):
        self.selected_params = list(egt_params.DEFAULT_PARAMS)
        if self.selected_engine_id:
            async for update in self._refresh_chart():
                yield update

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
            async for update in self._refresh_chart():
                yield update

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
            async for update in self._refresh_chart():
                yield update

    @rx.event
    async def on_load(self):
        self._build_engine_list()
        self._refresh_versions()
        params = self.router.url.query_parameters
        engine = params.get("engine", "")
        if any(e["id"] == engine for e in self.available_engines_labeled):
            self.selected_engine_id = engine
        gs = await self.get_state(GlobalState)
        for key, field in (("start", "start_date"), ("end", "end_date")):
            value = params.get(key, "")
            if key in params and (not value or (
                re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and _parse_date(value)
            )):
                setattr(gs, field, value)
        self.timeline_start = self.timeline_end = ""
        lo, hi = params.get("x_start", ""), params.get("x_end", "")
        if self._valid_timeline(lo, hi):
            self.timeline_start, self.timeline_end = lo, hi
        if self.available_engines_labeled and (
            not self.selected_engine_id
            or all(e["id"] != self.selected_engine_id for e in self.available_engines_labeled)
        ):
            self.selected_engine_id = self.available_engines_labeled[0]["id"]
        if self.selected_engine_id:
            self._refresh_labels()
            async for update in self._refresh_chart():
                yield update
        yield await self._sync_url()

    @rx.event
    async def select_engine(self, engine_id: str):
        self.selected_engine_id = engine_id
        self._refresh_labels()
        async for update in self._refresh_chart():
            yield update
        yield await self._sync_url()

    async def _sync_url(self):
        gs = await self.get_state(GlobalState)
        params = json.dumps({
            "engine": self.selected_engine_id,
            "start": gs.start_date, "end": gs.end_date,
            "x_start": self.timeline_start, "x_end": self.timeline_end,
        })
        return rx.call_script(
            "(() => { const url = new URL(window.location.href);"
            "if (url.pathname.replace(/\\/$/, '') !== '/egt') return;"
            f"for (const [key, value] of Object.entries({params})) {{"
            "if (value || key === 'start' || key === 'end') url.searchParams.set(key, value);"
            "else url.searchParams.delete(key);"
            "} window.history.replaceState(window.history.state, '', url.href); })()"
        )

    @staticmethod
    def _valid_timeline(lo, hi) -> bool:
        if not isinstance(lo, str) or not isinstance(hi, str):
            return False
        start, end = _parse_date(lo), _parse_date(hi)
        try:
            return start is not None and end is not None and start < end
        except TypeError:
            return False

    async def _set_date(self, field: str, value: str):
        if value and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and _parse_date(value)):
            return
        gs = await self.get_state(GlobalState)
        setattr(gs, field, value)
        self.timeline_start = self.timeline_end = ""
        if self.selected_engine_id:
            async for update in self._refresh_chart():
                yield update
        yield await self._sync_url()

    @rx.event
    async def set_start_date(self, value: str):
        async for update in self._set_date("start_date", value):
            yield update

    @rx.event
    async def set_end_date(self, value: str):
        async for update in self._set_date("end_date", value):
            yield update

    @rx.event
    async def on_plot_relayout(self, data: dict):
        previous = (self.timeline_start, self.timeline_end)
        for key, value in data.items():
            if re.fullmatch(r"xaxis\d*\.autorange", key) and value is True:
                self.timeline_start = self.timeline_end = ""
                break
            if re.fullmatch(r"xaxis\d*\.range(?:\[0\])?", key):
                bounds = value if isinstance(value, list) else [value, data.get(key.replace("[0]", "[1]"))]
                if len(bounds) == 2 and self._valid_timeline(*bounds):
                    self.timeline_start, self.timeline_end = bounds
                    break
        else:
            return
        if previous == (self.timeline_start, self.timeline_end):
            return
        # Retain the viewport on later chart rebuilds without recomputing on pan.
        self.chart_figure.update_xaxes(
            range=[self.timeline_start, self.timeline_end] if self.timeline_start else None,
            autorange=not bool(self.timeline_start),
        )
        return await self._sync_url()

    # --- Labeling events ---

    def _refresh_labels(self) -> None:
        if self.selected_engine_id:
            self.manual_labels = labels_store.labels_for(self.selected_engine_id)
        else:
            self.manual_labels = []

    @rx.event
    def toggle_label_mode(self, value: bool):
        self.label_mode = value
        self.chart_figure.update_layout(dragmode="select" if value else "zoom")

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
        # Event markers carry maintenance dates, not flight observations.
        xs = [
            p["x"] for p in (points or [])
            if p.get("x") is not None
            and isinstance(p.get("curveNumber"), int)
            and 0 <= p["curveNumber"] < len(self.chart_figure.data)
            and self.chart_figure.data[p["curveNumber"]].meta == "reading"
        ]
        if not xs:
            return
        # Plotly versions/traces can return date strings or epoch milliseconds.
        # Pandas otherwise interprets numeric coordinates as nanoseconds.
        ts = pd.Series([
            pd.to_datetime(x, unit="ms", errors="coerce")
            if isinstance(x, (int, float)) else pd.to_datetime(x, errors="coerce")
            for x in xs
        ]).dropna()
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
        async for update in self._refresh_chart():
            yield update

    @rx.event
    async def delete_label(self, row_id: str):
        labels_store.delete_label(row_id)
        self.export_status = "Label removed."
        self._refresh_labels()
        async for update in self._refresh_chart():
            yield update

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

    async def _refresh_chart(self):
        """Finish the control event before starting any expensive chart work."""
        self._chart_revision += 1
        self.is_computing = True
        self.chart_error = ""
        if not self._chart_worker_running:
            self._chart_worker_running = True
            yield EgtState.rebuild_chart

    @rx.event(background=True)
    async def rebuild_chart(self):
        # One worker per session. Changes made during a build are coalesced into
        # the next snapshot; stale figures never overwrite the current choice.
        completed = False
        try:
            while True:
                async with self:
                    revision = self._chart_revision
                    gs = await self.get_state(GlobalState)
                    request = EgtChartRequest(
                        bundle=LOADED.get(_AIRCRAFT_TYPE),
                        selected_engine_id=self.selected_engine_id,
                        entries=tuple(dict(entry) for entry in self._selected_entries()),
                        model_params={key: getattr(self, key) for key in _DEFAULT_MODEL_PARAMS},
                        start=_parse_date(gs.start_date),
                        end=_parse_date(gs.end_date),
                        selected_version=self.selected_version,
                        label_mode=self.label_mode,
                        timeline_start=self.timeline_start,
                        timeline_end=self.timeline_end,
                    )
                error = ""
                try:
                    figure, version_error = await asyncio.to_thread(request.build)
                except Exception as exc:
                    figure, version_error = None, ""
                    error = f"Could not update chart: {exc}"
                async with self:
                    if revision != self._chart_revision:
                        continue
                    # These lightweight controls can change during the build.
                    if figure is not None:
                        figure.update_layout(dragmode="select" if self.label_mode else "zoom")
                        figure.update_xaxes(
                            range=[self.timeline_start, self.timeline_end] if self.timeline_start else None,
                            autorange=not bool(self.timeline_start),
                        )
                        self.chart_figure = figure
                        self.chart_rows = len(request.entries)
                    self.has_chart = figure is not None
                    self.version_error = version_error
                    self.chart_error = error
                    self.is_computing = False
                    self._chart_worker_running = False
                    completed = True
                    return
        finally:
            # Also release the loading state if the task is cancelled or a
            # snapshot cannot be constructed.
            if not completed:
                async with self:
                    self.is_computing = False
                    self._chart_worker_running = False
