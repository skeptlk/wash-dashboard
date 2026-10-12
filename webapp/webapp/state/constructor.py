"""Constructor controls; no dependency on the Parquet startup loader."""

import asyncio
from datetime import date, datetime
import json
import logging
import math
import re
from urllib.parse import parse_qsl

import plotly.graph_objects as go
import reflex as rx

from ..components.constructor_fig import (
    add_predictions,
    add_series,
    copy_series,
    empty_chart,
    update_time_ticks,
    trace_x_values,
)
from ..data import flight_db
from ..data.egt_params import DEFAULT_PARAMS

logger = logging.getLogger(__name__)


class ConstructorState(rx.State):
    engines: list[dict[str, str]] = []
    selected_engine: str = ""
    catalog: list[dict[str, str]] = []
    selected_params: list[str] = []
    start_date: str = ""
    end_date: str = ""
    smoothing_window: str = "26"
    egt_indication_store: str = rx.LocalStorage(
        "false", name="ew_constructor_egt_indication"
    )
    _predictions: list[tuple[datetime, float]] = []
    _predictions_key: str = ""
    timeline_start: str = ""
    timeline_end: str = ""
    chart_rows: int = 0
    chart_figure: go.Figure = go.Figure()
    chart_generation: int = 0
    chart_data_generation: int = 0
    chart_offset: int = 0
    loaded_params: int = 0
    _chart_figure: go.Figure = go.Figure()
    _series_cache: dict[str, go.Figure] = {}
    _figure_params: list[str] = []
    _sent_params: list[str] = []
    _data_key: str = ""
    _loading_param: bool = False
    _prepared_generation: int = -1
    _catalog_family: str = ""
    _catalogs: dict[str, list[dict[str, str]]] = {}
    has_chart: bool = False
    is_computing: bool = False
    error: str = ""

    @rx.var
    def egt_indication_enabled(self) -> bool:
        return self.egt_indication_store == "true"

    @rx.var
    def chart_height(self) -> str:
        return "100%" if self.chart_rows <= 3 else f"{self.chart_rows * 180 + 150}px"

    async def _refresh(self):
        self.error = ""
        data_key = json.dumps(
            [
                self.selected_engine,
                self.start_date,
                self.end_date,
                self.smoothing_window,
                self.egt_indication_enabled,
            ]
        )
        if data_key != self._data_key:
            self._data_key = data_key
            self.chart_data_generation += 1
            self._series_cache = {}
            self._sent_params = []
            self.loaded_params = 0
        else:
            for row, pid in enumerate(self._figure_params):
                if pid in self._series_cache:
                    axis = self._chart_figure.layout[
                        f"yaxis{2 * row + 1 if row else ''}"
                    ]
                    self._series_cache[pid].update_yaxes(
                        range=axis.range, autorange=axis.autorange, secondary_y=False
                    )
        if not self.has_chart:
            self._sent_params = []
        self.chart_generation += 1
        self._loading_param = False
        self.loaded_params = 0
        self.is_computing = bool(self.selected_engine and self.selected_params)
        if not self.is_computing:
            self.has_chart = False
            self._sent_params = []
        yield self._sync_url()
        if self.is_computing:
            yield ConstructorState.prepare_chart(self.chart_generation)

    @rx.event(background=True)
    async def prepare_chart(self, generation: int):
        async with self:
            if generation != self.chart_generation or not self.is_computing:
                return
            engine = self.selected_engine
            family, eid = engine.split(":", 1)
            start, end = self.start_date, self.end_date
            catalog = list(self.catalog)
            selected = list(self.selected_params)
            option = dict(next(e for e in self.engines if e["key"] == engine))
            enabled = self.egt_indication_enabled
            prediction_key = json.dumps([engine, start, end])
            predictions = list(self._predictions)
            needs_predictions = enabled and prediction_key != self._predictions_key
            data_generation = self.chart_data_generation
        try:
            for value in (start, end):
                if value:
                    date.fromisoformat(value)
            if needs_predictions:
                predictions = await asyncio.to_thread(
                    flight_db.read_egt_predictions,
                    family,
                    eid,
                    start,
                    end,
                    catalog=catalog,
                )
            # Stop the old pipeline before doing further work or publishing it.
            async with self:
                if generation != self.chart_generation:
                    return
            entries = {entry["id"]: entry for entry in catalog}
            figure = await asyncio.to_thread(
                empty_chart,
                family,
                eid,
                [entries[pid] for pid in selected],
                option,
            )
            figure.update_layout(uirevision=data_generation)
            async with self:
                if generation != self.chart_generation:
                    return
                if needs_predictions:
                    self._predictions = predictions
                    self._predictions_key = prediction_key
                self._chart_figure = figure
                self._prepared_generation = generation
                self._figure_params = selected
                self.chart_rows = len(selected)
            yield ConstructorState.load_next_parameter(generation, 0)
        except Exception as exc:
            async with self:
                if generation != self.chart_generation:
                    return
                logger.exception("Constructor chart failed")
                self.error = (
                    str(exc)
                    if isinstance(exc, (ValueError, FileNotFoundError))
                    else ("Could not read the flight database. Check the server logs.")
                )
                self.has_chart = False
                self.is_computing = False

    @rx.event(background=True)
    async def load_next_parameter(self, generation: int, completed: int):
        async with self:
            if (
                generation != self.chart_generation
                or generation != self._prepared_generation
                or completed != self.loaded_params
                or not self.is_computing
                or self._loading_param
            ):
                return
            self._loading_param = True
            family, eid = self.selected_engine.split(":", 1)
            selected = list(self.selected_params)
            catalog = list(self.catalog)
            start, end = self.start_date, self.end_date
            window = int(self.smoothing_window)
            enabled = self.egt_indication_enabled
            predictions = list(self._predictions)
            cache = dict(self._series_cache)
            figure = self._chart_figure
            viewport = {
                name: (figure.layout[name].range, figure.layout[name].autorange)
                for name in figure.layout
                if re.fullmatch(r"yaxis\d*", name)
            }
            data_generation = self.chart_data_generation
            sent = list(self._sent_params)
        try:
            # Only the local figure is mutated while the state lock is released.
            figure = await asyncio.to_thread(go.Figure, figure)
            offset = len(figure.data)
            loaded = completed
            while loaded < len(selected):
                pid = selected[loaded]
                cached = pid in cache
                if not cached:
                    series, events = await asyncio.to_thread(
                        flight_db.read_trends,
                        family,
                        eid,
                        [pid],
                        start,
                        end,
                        window,
                        catalog=catalog,
                    )
                    async with self:
                        if generation != self.chart_generation:
                            return
                    entry, frame = series[0]

                    def build_source():
                        source = empty_chart(family, eid, [entry])
                        add_series(source, entry, frame, events, 1, window)
                        if enabled:
                            add_predictions(source, entry, predictions)
                        for index, trace in enumerate(source.data):
                            trace.meta = f"{pid}:{index}"
                        return source

                    cache[pid] = await asyncio.to_thread(build_source)
                row = loaded + 1
                await asyncio.to_thread(copy_series, figure, cache[pid], row)
                figure.update_yaxes(
                    uirevision=f"{data_generation}:{pid}",
                    row=row,
                    col=1,
                    secondary_y=False,
                )
                loaded += 1
                if not cached:
                    break
            async with self:
                if generation != self.chart_generation:
                    return
                for axis_name in self._chart_figure.layout:
                    if re.fullmatch(r"yaxis\d*", axis_name):
                        axis = self._chart_figure.layout[axis_name]
                        if (axis.range, axis.autorange) != viewport.get(axis_name):
                            figure.layout[axis_name].update(
                                range=axis.range, autorange=axis.autorange
                            )
                self._chart_figure = figure
                self._series_cache = cache
                self.loaded_params = loaded
                self.is_computing = loaded < len(selected)
                self.has_chart = True
                self._apply_timeline()
                self.chart_offset = offset
                traces = []
                for trace in figure.data[offset:]:
                    payload = trace.to_plotly_json()
                    pid = trace.meta.rsplit(":", 1)[0]
                    if pid in sent:
                        for field in ("x", "y", "customdata"):
                            payload.pop(field, None)
                    traces.append(payload)
                self._sent_params = list(dict.fromkeys([*sent, *selected[:loaded]]))
                self.chart_figure = go.Figure(data=traces, layout=figure.layout)
                if not self.is_computing:
                    self.has_chart = any(
                        len(trace_x_values(trace))
                        for trace in figure.data
                        if trace.name == "Raw"
                    )
        except Exception as exc:
            async with self:
                if generation != self.chart_generation:
                    return
                logger.exception("Constructor parameter load failed")
                self.error = (
                    str(exc)
                    if completed == 0
                    and isinstance(exc, (ValueError, FileNotFoundError))
                    else (
                        "Could not load the remaining parameters. Change the selection to retry."
                    )
                )
                self.is_computing = False
                if completed == 0:
                    self.has_chart = False
        finally:
            async with self:
                if generation == self.chart_generation:
                    self._loading_param = False

    async def _select(self, key):
        if not any(e["key"] == key for e in self.engines):
            raise ValueError("Unknown engine")
        family, _ = key.split(":", 1)
        if key != self.selected_engine:
            self.timeline_start = self.timeline_end = ""
        self.selected_engine = key
        # Re-publish the catalog even when revisiting the same family: a new
        # browser mount starts with empty controls while server state can survive.
        self.catalog = [dict(entry) for entry in self._catalogs[family]]
        self._catalog_family = family
        available = {e["id"] for e in self.catalog}
        selected = [p for p in self.selected_params if p in available]
        self.selected_params = (
            selected
            or [p for p in DEFAULT_PARAMS if p in available]
            or [e["id"] for e in self.catalog[:1]]
        )

    @rx.event
    async def on_load(self):
        # Browser refs disappear on reload/navigation; the server cache survives.
        # Reuse computed rows, but resend their arrays to this new chart mount.
        self._sent_params = []
        self.has_chart = False
        try:
            # Reflex's query_parameters drops blank values (params=, start=).
            params = dict(parse_qsl(self.router.url.query, keep_blank_values=True))
            self.engines = await asyncio.to_thread(flight_db.engine_options)
            families = {e["key"].split(":", 1)[0] for e in self.engines}
            self._catalogs = {
                family: await asyncio.to_thread(flight_db.parameter_catalog, family)
                for family in families
            }
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
        if (param_id in self.selected_params) == checked:
            return
        self.selected_params = [p for p in self.selected_params if p != param_id]
        if checked:
            self.selected_params.append(param_id)
        async for update in self._refresh():
            yield update

    @rx.event
    async def set_egt_indication(self, enabled: bool):
        self.egt_indication_store = "true" if enabled else "false"
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
        update_time_ticks(self._chart_figure, self.timeline_start, self.timeline_end)

    @rx.event
    def on_plot_relayout(self, data: dict):
        previous = (self.timeline_start, self.timeline_end)
        y_changed = False
        # Plotly reports only the axes touched by the gesture. Preserve each
        # primary Y axis independently, including Y-only zoom and reset.
        for axis_name in self._chart_figure.layout:
            if not re.fullmatch(r"yaxis\d*", axis_name):
                continue
            axis = self._chart_figure.layout[axis_name]
            if axis.fixedrange:
                continue
            if data.get(f"{axis_name}.autorange") is True:
                y_changed |= axis.range is not None or axis.autorange is not True
                axis.update(range=None, autorange=True)
                continue
            bounds = data.get(
                f"{axis_name}.range",
                [
                    data.get(f"{axis_name}.range[0]"),
                    data.get(f"{axis_name}.range[1]"),
                ],
            )
            if (
                isinstance(bounds, list)
                and len(bounds) == 2
                and all(
                    isinstance(v, (int, float)) and math.isfinite(v) for v in bounds
                )
                and bounds[0] != bounds[1]
            ):
                y_changed |= tuple(bounds) != axis.range or axis.autorange is not False
                axis.update(range=bounds, autorange=False)
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
        if previous == (self.timeline_start, self.timeline_end) and not y_changed:
            return
        self._apply_timeline()
        # A zoom update sends layout only, never the already loaded observations.
        self.chart_offset = len(self._chart_figure.data)
        self.chart_figure = go.Figure(layout=self._chart_figure.layout)
        return self._sync_url()
