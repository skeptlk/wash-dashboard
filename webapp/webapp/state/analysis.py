"""State for the Wash Analysis page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx

from enginewash import WashCalculator, WashConfig, WashParameter

from ..components.analysis_fig import build_analysis_chart, build_violin_figure
from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for, maint_for
from .base import GlobalState


_PARAM_CHOICES = ["EGTHDM", "GWFM", "DEGT"]

_DEFAULT_THRESHOLDS = {p: PARAMETER_BY_NAME[p].threshold for p in _PARAM_CHOICES}


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _sort_key(value):
    """Sort key that tolerates mixed/missing values within a column.

    None and placeholder strings sort to the end (in ascending order).
    """
    if value is None or value == "" or value == "—":
        return (1, 0)
    if isinstance(value, bool):
        return (0, value)
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value).lower())


def _event_to_row(ev, label: str) -> dict:
    return {
        "engine_id": ev.engine_id,
        "engine_label": label,
        "event_index": ev.event_index,
        "maint_date": ev.maint_datetime.strftime("%Y-%m-%d") if ev.maint_datetime else "—",
        "ata_code": ev.ata_code or "—",
        "mean_before": round(ev.mean_before, 2),
        "mean_after": round(ev.mean_after, 2),
        "delta": round(ev.delta, 2),
        "delta_positive": ev.delta > 0,
        "loe_date": (
            ev.time_loss_of_efficiency.strftime("%Y-%m-%d")
            if ev.time_loss_of_efficiency else "—"
        ),
        "loe_days": ev.days_loss_of_efficiency if ev.days_loss_of_efficiency is not None else "—",
    }


class AnalysisState(rx.State):
    """Per-page state for the Wash Analysis view."""

    # Controls
    selected_parameter: str = "EGTHDM"
    selected_engine_ids: list[str] = []
    available_engines_list: list[str] = []
    smooth_window: int = 30
    pre_smooth_window: int = 15
    n_obs_mean: int = 15
    loe_threshold: float = 2.0

    # UI state
    is_computing: bool = False
    has_results: bool = False
    error_message: str = ""
    active_engine_id: str = ""
    n_events: int = 0

    # Click-to-sort: dict key of the active column, and direction.
    sort_column: str = ""
    sort_ascending: bool = True

    # Results for the frontend
    summary_rows: list[dict] = []
    chart_figure: go.Figure = go.Figure()
    violin_figure: go.Figure = go.Figure()

    # Backend-only: cache of per-engine figures (not serialised to client)
    _figures_cache: dict = {}

    @rx.var
    def parameter_options(self) -> list[str]:
        return _PARAM_CHOICES

    @rx.var
    def sorted_summary_rows(self) -> list[dict]:
        if not self.sort_column:
            return self.summary_rows
        return sorted(
            self.summary_rows,
            key=lambda r: _sort_key(r.get(self.sort_column)),
            reverse=not self.sort_ascending,
        )

    @rx.event
    def sort_by(self, column: str):
        if self.sort_column == column:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_column = column
            self.sort_ascending = True

    @rx.event
    def set_selected_parameter(self, value: str):
        self.selected_parameter = value
        self.loe_threshold = _DEFAULT_THRESHOLDS.get(value, 2.0)

    @rx.event
    def set_engine_checked(self, eid: str, checked: bool):
        if checked and eid not in self.selected_engine_ids:
            self.selected_engine_ids = [*self.selected_engine_ids, eid]
        elif not checked:
            self.selected_engine_ids = [e for e in self.selected_engine_ids if e != eid]

    @rx.event
    def clear_engines(self):
        self.selected_engine_ids = []

    @rx.event
    def set_smooth_window(self, value: str):
        try:
            self.smooth_window = max(5, int(value))
        except (ValueError, TypeError):
            pass

    @rx.event
    def set_pre_smooth_window(self, value: str):
        try:
            self.pre_smooth_window = max(1, int(value))
        except (ValueError, TypeError):
            pass

    @rx.event
    def set_n_obs_mean(self, value: str):
        try:
            self.n_obs_mean = max(1, int(value))
        except (ValueError, TypeError):
            pass

    @rx.event
    def set_loe_threshold(self, value: str):
        try:
            self.loe_threshold = float(value)
        except (ValueError, TypeError):
            pass

    @rx.event
    async def on_load(self):
        gs = await self.get_state(GlobalState)
        bundle = LOADED.get(gs.aircraft_type)
        if bundle is None:
            return
        engine_ids_wash = set(bundle.wash_maint["engine_id_str"].unique())
        available = [e for e in bundle.available_engines if e in engine_ids_wash]
        self.available_engines_list = available
        if available and not self.selected_engine_ids:
            self.selected_engine_ids = [available[0]]

    @rx.event
    def select_engine_chart(self, engine_id: str):
        fig = self._figures_cache.get(engine_id)
        if fig is not None:
            self.active_engine_id = engine_id
            self.chart_figure = fig

    @rx.event
    async def run_analysis(self):
        self.is_computing = True
        self.error_message = ""
        self.has_results = False
        yield

        gs = await self.get_state(GlobalState)
        bundle = LOADED.get(gs.aircraft_type)

        if bundle is None:
            self.error_message = "No data loaded for this aircraft type."
            self.is_computing = False
            return

        if not self.selected_engine_ids:
            self.error_message = "Please select at least one engine."
            self.is_computing = False
            return

        base_param = PARAMETER_BY_NAME[self.selected_parameter]
        calc_param = WashParameter(
            name=base_param.name,
            flight_phase=base_param.flight_phase,
            trend_direction=base_param.trend_direction,
            threshold=self.loe_threshold,
        )

        start = _parse_date(gs.start_date)
        end = _parse_date(gs.end_date)

        flights = []
        for eid in self.selected_engine_ids:
            flights.extend(flights_for(bundle, eid, base_param, start=start, end=end))

        if not flights:
            self.error_message = (
                f"No {self.selected_parameter} data for the selected engines in the date range."
            )
            self.is_computing = False
            return

        maintenance = []
        for eid in self.selected_engine_ids:
            maintenance.extend(maint_for(bundle, eid))

        config = WashConfig(
            smooth_window=self.smooth_window,
            pre_smooth_window=self.pre_smooth_window,
            n_obs_mean=self.n_obs_mean,
        )
        calc = WashCalculator(config=config)
        summaries = calc.process(flights=flights, maintenances=maintenance, parameter=calc_param)
        plot = calc.build_plot(flights=flights, maintenances=maintenance, parameter=calc_param)

        all_events = [ev for s in summaries for ev in s.results]
        if not all_events:
            self.error_message = "No wash events found for the selected engines in the date range."
            self.is_computing = False
            return

        # Group curves and markers per engine
        curves_by_eng: dict[str, list] = {}
        for c in plot.curves:
            curves_by_eng.setdefault(c.engine_id, []).append(c)
        markers_by_eng: dict[str, list] = {}
        for m in plot.markers:
            markers_by_eng.setdefault(m.engine_id, []).append(m)

        labels = bundle.engine_labels
        figures: dict[str, go.Figure] = {}
        for eid in self.selected_engine_ids:
            eng_markers = sorted(markers_by_eng.get(eid, []), key=lambda m: m.event_index)
            if not eng_markers:
                continue
            figures[eid] = build_analysis_chart(
                eid,
                labels.get(eid, eid),
                curves_by_eng.get(eid, []),
                eng_markers,
                calc_param,
            )

        if not figures:
            self.error_message = "No wash events found for the selected engines."
            self.is_computing = False
            return

        self._figures_cache = figures

        # Summary table rows (sorted by engine, then event index)
        engine_ids_with_events = {str(ev.engine_id) for ev in all_events}
        sorted_events = sorted(
            [ev for ev in all_events if str(ev.engine_id) in figures],
            key=lambda e: (str(e.engine_id), e.event_index),
        )
        self.summary_rows = [_event_to_row(ev, labels.get(ev.engine_id, ev.engine_id)) for ev in sorted_events]
        self.n_events = len(sorted_events)

        # Violin plot
        self.violin_figure = build_violin_figure(
            [ev for ev in all_events if str(ev.engine_id) in figures],
            calc_param,
        )

        # Display chart for first engine with events
        first_eid = next(
            (e for e in self.selected_engine_ids if e in figures),
            next(iter(figures)),
        )
        self.active_engine_id = first_eid
        self.chart_figure = figures[first_eid]

        self.has_results = True
        self.is_computing = False
