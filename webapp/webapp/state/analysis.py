"""State for the Wash Analysis page."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import plotly.graph_objects as go
import reflex as rx

from enginewash import WashCalculator, WashConfig, WashParameter

from ..components.analysis_fig import build_analysis_chart, build_violin_figure
from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for, maint_for, utilization_for
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


def _event_zoom_range(m) -> list[str]:
    """ISO ``[x0, x1]`` window centred on the wash date, sized to fit the
    pre/post segments and loss-of-efficiency marker for this event."""
    wash_t = m.wash_event_point.flight_datetime
    lefts = [wash_t]
    rights = [wash_t]
    if m.before_segment is not None:
        lefts.append(m.before_segment.start_datetime)
    if m.before_value_point is not None:
        lefts.append(m.before_value_point.flight_datetime)
    if m.after_segment is not None:
        rights.append(m.after_segment.end_datetime)
    if m.after_value_point is not None:
        rights.append(m.after_value_point.flight_datetime)
    if m.loss_of_efficiency_point is not None:
        rights.append(m.loss_of_efficiency_point.flight_datetime)

    half = max(wash_t - min(lefts), max(rights) - wash_t)
    if half <= timedelta(0):
        half = timedelta(days=60)
    pad = half * 0.25
    x0 = wash_t - half - pad
    x1 = wash_t + half + pad
    return [x0.isoformat(), x1.isoformat()]


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
        "loe_cycles": ev.cycles_loss_of_efficiency if ev.cycles_loss_of_efficiency is not None else "—",
        "loe_hours": ev.hours_loss_of_efficiency if ev.hours_loss_of_efficiency is not None else "—",
    }


class AnalysisState(rx.State):
    """Per-page state for the Wash Analysis view."""

    # Controls
    selected_parameter: str = "EGTHDM"
    selected_engine_ids: list[str] = []
    available_engines_labeled: list[dict] = []  # [{"id", "label"}], across selected types
    engine_search: str = ""
    smooth_window: int = 30
    pre_smooth_window: int = 15
    n_obs_mean: int = 15
    before_wash_mode: str = "worst"
    after_wash_mode: str = "best"
    loe_threshold: float = 2.0

    # UI state
    is_computing: bool = False
    has_results: bool = False
    error_message: str = ""
    active_engine_id: str = ""
    # Key ("<engine_id>:<event_index>") of the wash row currently selected in the
    # summary table — drives the row highlight and the chart zoom.
    selected_event_key: str = ""
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

    # Backend-only: zoom x-range per wash event, keyed by "<engine_id>:<event_index>".
    _event_ranges: dict = {}

    # Backend-only: engine to auto-open on the next page load (set when the user
    # clicks an event in the Wash Schedule gantt). Consumed by ``on_load``.
    _pending_engine_id: str = ""

    @rx.var
    def parameter_options(self) -> list[str]:
        return _PARAM_CHOICES

    @rx.var
    def filtered_engines(self) -> list[dict]:
        q = self.engine_search.strip().lower()
        if not q:
            return self.available_engines_labeled
        return [
            e for e in self.available_engines_labeled
            if q in e["label"].lower() or q in e["id"].lower()
        ]

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
    def set_engine_search(self, value: str):
        self.engine_search = value

    @rx.event
    def select_all_engines(self):
        ids = [e["id"] for e in self.filtered_engines]
        self.selected_engine_ids = list(dict.fromkeys([*self.selected_engine_ids, *ids]))

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
    def set_before_wash_mode(self, value: str):
        self.before_wash_mode = value

    @rx.event
    def set_after_wash_mode(self, value: str):
        self.after_wash_mode = value

    @rx.event
    def set_loe_threshold(self, value: str):
        try:
            self.loe_threshold = float(value)
        except (ValueError, TypeError):
            pass

    def _load_engines(self, gs: GlobalState):
        """Rebuild the engine list (engines with wash events across the selected
        types), pruning any selection that's no longer available."""
        labeled: list[dict] = []
        seen: set[str] = set()
        for ac_type in gs.aircraft_types:
            bundle = LOADED.get(ac_type)
            if bundle is None:
                continue
            engine_ids_wash = set(bundle.wash_maint["engine_id_str"].unique())
            for eid in bundle.available_engines:
                if eid in engine_ids_wash and eid not in seen:
                    seen.add(eid)
                    labeled.append({"id": eid, "label": bundle.engine_labels.get(eid, eid)})
        self.available_engines_labeled = labeled
        # Drop any prior selection that's no longer available under the new types.
        self.selected_engine_ids = [e for e in self.selected_engine_ids if e in seen]
        if labeled and not self.selected_engine_ids:
            self.selected_engine_ids = [labeled[0]["id"]]

    @rx.event
    async def on_load(self):
        gs = await self.get_state(GlobalState)
        self._load_engines(gs)
        # If we arrived here from a click on the Wash Schedule gantt, select that
        # engine (overriding _load_engines' default) and build its report. Done
        # here rather than chained off the redirect so it always runs *after*
        # _load_engines, which would otherwise clobber the selection.
        if self._pending_engine_id:
            eid = self._pending_engine_id
            self._pending_engine_id = ""
            if any(e["id"] == eid for e in self.available_engines_labeled):
                self.selected_engine_ids = [eid]
                yield AnalysisState.run_analysis

    @rx.event
    async def toggle_aircraft_type(self, ac_type: str, checked: bool):
        gs = await self.get_state(GlobalState)
        gs.apply_type_toggle(ac_type, checked)
        self._load_engines(gs)

    @rx.event
    def select_event(self, engine_id: str, event_index: int):
        """Show the clicked engine's chart, zoomed and centred on the clicked wash."""
        fig = self._figures_cache.get(engine_id)
        if fig is None:
            return
        self.active_engine_id = engine_id
        self.selected_event_key = f"{engine_id}:{event_index}"
        rng = self._event_ranges.get(self.selected_event_key)
        if rng is not None:
            fig.update_xaxes(range=rng, autorange=False)
        else:
            fig.update_xaxes(autorange=True)
        self.chart_figure = fig

    @rx.event
    async def run_analysis(self):
        self.is_computing = True
        self.error_message = ""
        self.has_results = False
        yield

        gs = await self.get_state(GlobalState)
        bundles = [LOADED[t] for t in gs.aircraft_types if t in LOADED]

        if not bundles:
            self.error_message = "No aircraft type selected."
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

        # Engines are disjoint across types; gather flights/maintenance from the
        # bundle each selected engine actually belongs to, and merge labels.
        selected = set(self.selected_engine_ids)
        flights = []
        maintenance = []
        utilizations = []
        labels: dict[str, str] = {}
        for bundle in bundles:
            bundle_engines = set()
            for eid in bundle.available_engines:
                if eid in selected:
                    bundle_engines.add(eid)
                    flights.extend(flights_for(bundle, eid, base_param, start=start, end=end))
                    maintenance.extend(maint_for(bundle, eid))
                    labels[eid] = bundle.engine_labels.get(eid, eid)
            utilizations.extend(utilization_for(bundle, bundle_engines))

        if not flights:
            self.error_message = (
                f"No {self.selected_parameter} data for the selected engines in the date range."
            )
            self.is_computing = False
            return

        config = WashConfig(
            smooth_window=self.smooth_window,
            pre_smooth_window=self.pre_smooth_window,
            n_obs_mean=self.n_obs_mean,
            before_wash_mode=self.before_wash_mode,
            after_wash_mode=self.after_wash_mode,
        )
        calc = WashCalculator(config=config)
        summaries = calc.process(
            flights=flights,
            maintenances=maintenance,
            parameter=calc_param,
            utilizations=utilizations,
        )
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

        figures: dict[str, go.Figure] = {}
        event_ranges: dict[str, list[str]] = {}
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
            for m in eng_markers:
                event_ranges[f"{eid}:{m.event_index}"] = _event_zoom_range(m)

        if not figures:
            self.error_message = "No wash events found for the selected engines."
            self.is_computing = False
            return

        self._figures_cache = figures
        self._event_ranges = event_ranges
        self.selected_event_key = ""

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
