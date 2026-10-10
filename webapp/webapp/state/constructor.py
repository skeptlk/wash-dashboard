"""Constructor controls; no dependency on the Parquet startup loader."""

import asyncio
from datetime import date, datetime
import json
import logging
import re
from urllib.parse import parse_qsl

import pandas as pd
import plotly.graph_objects as go
import reflex as rx

from ..components.constructor_fig import add_series, empty_chart
from ..data import flight_db
from ..data.egt_params import DEFAULT_PARAMS

logger = logging.getLogger(__name__)


class ConstructorState(rx.State):
    engines: list[dict[str, str]] = []
    selected_engine: str = ""
    engine_search: str = ""
    catalog: list[dict[str, str]] = []
    selected_params: list[str] = []
    param_search: str = ""
    start_date: str = ""
    end_date: str = ""
    smoothing_window: str = "26"
    timeline_start: str = ""
    timeline_end: str = ""
    chart_rows: int = 0
    chart_figure: go.Figure = go.Figure()
    chart_generation: int = 0
    chart_offset: int = 0
    loaded_params: int = 0
    _chart_figure: go.Figure = go.Figure()
    _loading_param: bool = False
    _catalog_family: str = ""
    has_chart: bool = False
    is_computing: bool = False
    error: str = ""

    @rx.var
    def filtered_engines(self) -> list[dict[str, str]]:
        q = self.engine_search.strip().lower()
        return [e for e in self.engines if q in e["label"].lower()]

    @rx.var
    def takeoff_params(self) -> list[dict[str, str]]:
        return self._filtered_params("TAKEOFF")

    @rx.var
    def cruise_params(self) -> list[dict[str, str]]:
        return self._filtered_params("CRUISE")

    def _filtered_params(self, phase):
        q = self.param_search.strip().lower()
        return [
            e for e in self.catalog if e["phase"] == phase and q in e["name"].lower()
        ]

    @rx.var
    def chart_height(self) -> str:
        return "100%" if self.chart_rows <= 3 else f"{self.chart_rows * 180 + 150}px"

    async def _refresh(self):
        self.error = ""
        self.loaded_params = 0
        self.is_computing = False
        if not self.selected_engine or not self.selected_params:
            self.has_chart = False
            yield self._sync_url()
            return
        self.is_computing = True
        # Keep the previous figure and its dimensions beneath the loading overlay.
        yield self._sync_url()
        self.chart_generation += 1
        try:
            family, eid = self.selected_engine.split(":", 1)
            for value in (self.start_date, self.end_date):
                if value:
                    date.fromisoformat(value)
            catalog = {entry["id"]: entry for entry in self.catalog}
            self._chart_figure = await asyncio.to_thread(
                empty_chart, family, eid, [catalog[pid] for pid in self.selected_params]
            )
            self.chart_rows = len(self.selected_params)
            await self._load_parameter()
        except (ValueError, FileNotFoundError) as exc:
            self.error = str(exc)
            self.has_chart = False
        except Exception:
            logger.exception("Constructor chart failed")
            self.error = "Could not read the flight database. Check the server logs."
            self.has_chart = False
        if self.error:
            self.is_computing = False

    async def _load_parameter(self):
        """Send one row; the browser requests the next after Plotly renders it."""
        family, eid = self.selected_engine.split(":", 1)
        pid = self.selected_params[self.loaded_params]
        series, events = await asyncio.to_thread(
            flight_db.read_trends,
            family,
            eid,
            [pid],
            self.start_date,
            self.end_date,
            int(self.smoothing_window),
            catalog=list(self.catalog),
        )
        offset = len(self._chart_figure.data)
        entry, frame = series[0]
        await asyncio.to_thread(
            add_series,
            self._chart_figure,
            entry,
            frame,
            events,
            self.loaded_params + 1,
            int(self.smoothing_window),
        )
        self.loaded_params += 1
        self.is_computing = self.loaded_params < len(self.selected_params)
        # Empty rows must still mount Plotly so its acknowledgement advances loading.
        self.has_chart = True
        self._apply_timeline()
        self.chart_offset = offset
        self.chart_figure = go.Figure(
            data=self._chart_figure.data[offset:],
            layout=self._chart_figure.layout,
        )
        if not self.is_computing:
            self.has_chart = any(
                len(trace.x)
                for trace in self._chart_figure.data
                if trace.name == "Actual"
            )

    @rx.event
    async def load_next_parameter(self, generation: int, completed: int):
        if (
            generation != self.chart_generation
            or completed != self.loaded_params
            or not self.is_computing
            or self._loading_param
        ):
            return
        self._loading_param = True
        try:
            await self._load_parameter()
        except Exception:
            logger.exception("Constructor parameter load failed")
            self.error = "Could not load the remaining parameters. Change the selection to retry."
            self.is_computing = False
        finally:
            self._loading_param = False

    async def _select(self, key):
        if not any(e["key"] == key for e in self.engines):
            raise ValueError("Unknown engine")
        family, eid = key.split(":", 1)
        self.selected_engine = key
        if family != self._catalog_family:
            self.catalog = await asyncio.to_thread(flight_db.parameter_catalog, family)
            self._catalog_family = family
        available = {e["id"] for e in self.catalog}
        selected = [p for p in self.selected_params if p in available]
        self.selected_params = (
            selected
            or [p for p in DEFAULT_PARAMS if p in available]
            or [e["id"] for e in self.catalog[:1]]
        )
        if not self.start_date and not self.end_date:
            lo, hi = await asyncio.to_thread(flight_db.date_bounds, family, eid)
            if lo is not None:
                self.start_date = (
                    max(pd.Timestamp(lo), pd.Timestamp(hi) - pd.DateOffset(years=2))
                    .date()
                    .isoformat()
                )
                self.end_date = hi.date().isoformat()

    @rx.event
    async def on_load(self):
        try:
            # Reflex's query_parameters drops blank values (params=, start=).
            params = dict(parse_qsl(self.router.url.query, keep_blank_values=True))
            self.engines = await asyncio.to_thread(flight_db.engine_options)
            if self.engines:
                key = params.get("engine", self.selected_engine)
                if not any(e["key"] == key for e in self.engines):
                    key = self.engines[0]["key"]
                await self._select(key)
            else:
                self.selected_engine = ""
            self._restore_url(params)
        except FileNotFoundError as exc:
            self.error = str(exc)
            self.has_chart = False
            return
        except Exception:
            logger.exception("Constructor database initialization failed")
            self.error = "Could not open the flight database. Check the server logs."
            self.has_chart = False
            return
        async for update in self._refresh():
            yield update

    @rx.event
    async def select_engine(self, key: str):
        if not any(e["key"] == key for e in self.engines):
            return
        try:
            await self._select(key)
        except Exception:
            logger.exception("Constructor engine selection failed")
            self.error = "Could not read the flight database. Reload the page to retry."
            self.has_chart = False
            return
        async for update in self._refresh():
            yield update

    @rx.event
    async def toggle_param(self, param_id: str, checked: bool):
        if not any(e["id"] == param_id for e in self.catalog):
            return
        self.selected_params = [p for p in self.selected_params if p != param_id]
        if checked:
            self.selected_params.append(param_id)
        async for update in self._refresh():
            yield update

    @rx.event
    async def reset_params(self):
        available = {entry["id"] for entry in self.catalog}
        self.selected_params = [param for param in DEFAULT_PARAMS if param in available]
        async for update in self._refresh():
            yield update

    @rx.event
    async def set_start_date(self, value: str):
        if not self._valid_date(value):
            return
        self.start_date = value
        self.timeline_start = self.timeline_end = ""
        async for update in self._refresh():
            yield update

    @rx.event
    async def set_end_date(self, value: str):
        if not self._valid_date(value):
            return
        self.end_date = value
        self.timeline_start = self.timeline_end = ""
        async for update in self._refresh():
            yield update

    @rx.event
    async def set_smoothing_window(self, value: str):
        if not value.isdigit() or not 1 <= int(value) <= 1000:
            return
        self.smoothing_window = value
        async for update in self._refresh():
            yield update

    @rx.event
    def set_engine_search(self, value: str):
        self.engine_search = value

    @rx.event
    def set_param_search(self, value: str):
        self.param_search = value

    @staticmethod
    def _valid_date(value: str) -> bool:
        if not value:
            return True
        try:
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(
                date.fromisoformat(value)
            )
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _valid_timeline(lo, hi) -> bool:
        try:
            start, end = datetime.fromisoformat(lo), datetime.fromisoformat(hi)
            return start.tzinfo is None and end.tzinfo is None and start < end
        except (ValueError, TypeError):
            return False

    def _restore_url(self, params: dict):
        for key, field in (("start", "start_date"), ("end", "end_date")):
            if key in params and self._valid_date(params[key]):
                setattr(self, field, params[key])
        if "params" in params:
            available = {entry["id"] for entry in self.catalog}
            self.selected_params = list(
                dict.fromkeys(
                    pid for pid in params["params"].split(",") if pid in available
                )
            )
        window = params.get("smoothing", "")
        if window.isdigit() and 1 <= int(window) <= 1000:
            self.smoothing_window = window
        self.timeline_start = self.timeline_end = ""
        lo, hi = params.get("x_start", ""), params.get("x_end", "")
        if self._valid_timeline(lo, hi):
            self.timeline_start, self.timeline_end = lo, hi

    def _sync_url(self):
        params = json.dumps(
            {
                "engine": self.selected_engine,
                "start": self.start_date,
                "end": self.end_date,
                "params": ",".join(self.selected_params),
                "smoothing": self.smoothing_window,
                "x_start": self.timeline_start,
                "x_end": self.timeline_end,
            }
        )
        return rx.call_script(
            "(() => { const url = new URL(window.location.href);"
            "if (url.pathname.replace(/\\/$/, '') !== '/constructor') return;"
            f"for (const [key, value] of Object.entries({params})) {{"
            "if (value || ['start', 'end', 'params'].includes(key)) url.searchParams.set(key, value);"
            "else url.searchParams.delete(key);"
            "} window.history.replaceState(window.history.state, '', url.href); })()"
        )

    def _apply_timeline(self):
        self._chart_figure.update_xaxes(
            range=[self.timeline_start, self.timeline_end]
            if self.timeline_start
            else None,
            autorange=not bool(self.timeline_start),
        )

    @rx.event
    def on_plot_relayout(self, data: dict):
        previous = (self.timeline_start, self.timeline_end)
        for key, value in data.items():
            if re.fullmatch(r"xaxis\d*\.autorange", key) and value is True:
                self.timeline_start = self.timeline_end = ""
                break
            if re.fullmatch(r"xaxis\d*\.range(?:\[0\])?", key):
                bounds = (
                    value
                    if isinstance(value, list)
                    else [value, data.get(key.replace("[0]", "[1]"))]
                )
                if len(bounds) == 2 and self._valid_timeline(*bounds):
                    self.timeline_start, self.timeline_end = bounds
                    break
        if previous == (self.timeline_start, self.timeline_end):
            return
        self._apply_timeline()
        # A zoom update sends layout only, never the already loaded observations.
        self.chart_offset = len(self._chart_figure.data)
        self.chart_figure = go.Figure(layout=self._chart_figure.layout)
        return self._sync_url()
