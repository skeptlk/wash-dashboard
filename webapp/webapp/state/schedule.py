"""State for the Wash Schedule page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx

from ..components.schedule_fig import build_schedule_figures, prepare_schedule
from ..data import LOADED
from .analysis import AnalysisState
from .base import GlobalState


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class ScheduleState(rx.State):
    """Per-page state for the Wash Schedule view."""

    selected_aircraft_regs: list[str] = []
    selected_ata_codes: list[str] = []
    available_aircraft: list[dict] = []  # [{"id", "label"}], scoped to selected types
    aircraft_search: str = ""
    available_ata_codes: list[str] = []

    # Per-engine Gantt chart with the built-in rangeslider.
    gantt_figure: go.Figure = go.Figure()
    is_computing: bool = False
    has_results: bool = False
    summary_text: str = ""

    # Backend-only: gantt y-axis label → engine_id, for click-to-navigate.
    _label_to_engine: dict[str, str] = {}

    @rx.var
    def filtered_aircraft(self) -> list[dict]:
        q = self.aircraft_search.strip().lower()
        if not q:
            return self.available_aircraft
        return [a for a in self.available_aircraft if q in a["label"].lower()]

    @rx.event
    def set_aircraft_reg_checked(self, reg: str, checked: bool):
        if checked and reg not in self.selected_aircraft_regs:
            self.selected_aircraft_regs = [*self.selected_aircraft_regs, reg]
        elif not checked:
            self.selected_aircraft_regs = [r for r in self.selected_aircraft_regs if r != reg]

    @rx.event
    def set_aircraft_search(self, value: str):
        self.aircraft_search = value

    @rx.event
    def select_all_aircraft(self):
        ids = [a["id"] for a in self.filtered_aircraft]
        self.selected_aircraft_regs = list(dict.fromkeys([*self.selected_aircraft_regs, *ids]))

    @rx.event
    def clear_aircraft(self):
        self.selected_aircraft_regs = []

    @rx.event
    def set_ata_code_checked(self, code: str, checked: bool):
        if checked and code not in self.selected_ata_codes:
            self.selected_ata_codes = [*self.selected_ata_codes, code]
        elif not checked:
            self.selected_ata_codes = [c for c in self.selected_ata_codes if c != code]

    @rx.event
    async def on_load(self):
        """Populate filter option lists and build the initial figure."""
        gs = await self.get_state(GlobalState)
        bundles = [LOADED[t] for t in gs.aircraft_types if t in LOADED]
        if not bundles:
            return
        prepared = prepare_schedule(bundles)
        self.available_aircraft = [{"id": r, "label": r} for r in prepared["aircraft_options"]]
        self.available_ata_codes = prepared["ata_codes"]
        self.selected_aircraft_regs = []
        self.selected_ata_codes = []
        yield ScheduleState.rebuild_gantt

    @rx.event
    async def toggle_aircraft_type(self, ac_type: str, checked: bool):
        gs = await self.get_state(GlobalState)
        gs.apply_type_toggle(ac_type, checked)
        yield ScheduleState.rebuild_gantt

    @rx.event
    async def rebuild_gantt(self):
        self.is_computing = True
        yield

        gs = await self.get_state(GlobalState)
        bundles = [LOADED[t] for t in gs.aircraft_types if t in LOADED]
        if not bundles:
            self.has_results = False
            self.summary_text = "No aircraft type selected."
            self.is_computing = False
            return

        prepared = prepare_schedule(bundles)
        regs = prepared["aircraft_options"]
        self.available_aircraft = [{"id": r, "label": r} for r in regs]
        self.available_ata_codes = prepared["ata_codes"]
        # Drop selections that no longer exist under the current type scope.
        reg_set = set(regs)
        self.selected_aircraft_regs = [r for r in self.selected_aircraft_regs if r in reg_set]
        ata_set = set(prepared["ata_codes"])
        self.selected_ata_codes = [c for c in self.selected_ata_codes if c in ata_set]
        sdf = prepared["df"]
        self._label_to_engine = dict(zip(sdf["engine_label"], sdf["engine_id"]))

        main_fig, n_events = build_schedule_figures(
            prepared["df"],
            prepared["ata_color"],
            aircraft_filter=self.selected_aircraft_regs or None,
            ata_filter=self.selected_ata_codes or None,
            start=_parse_date(gs.start_date),
            end=_parse_date(gs.end_date),
        )
        self.gantt_figure = main_fig
        self.has_results = n_events > 0
        self.summary_text = (
            f"{n_events:,} events" if n_events > 0 else "No events match the filters."
        )
        self.is_computing = False

    @rx.event
    async def open_in_analysis(self, points: list[dict]):
        """Clicking a gantt point opens that engine on the Wash Analysis page.

        The clicked point's ``y`` is the gantt row label (one row per engine);
        we map it back to an engine id, stash it as the Analysis page's pending
        engine, and navigate. The Analysis page's ``on_load`` then selects that
        engine and builds the report — mirroring the old Dash navigate-on-click
        flow. Running the report from ``on_load`` (rather than chaining it onto
        the redirect here) guarantees it happens after the page's own
        ``_load_engines``, which would otherwise reset the selection.
        """
        if not points:
            return
        label = points[0].get("y")
        engine_id = self._label_to_engine.get(label) if label is not None else None
        if not engine_id:
            return
        analysis = await self.get_state(AnalysisState)
        analysis._pending_engine_id = engine_id
        analysis.selected_engine_ids = [engine_id]
        return rx.redirect("/analysis")
