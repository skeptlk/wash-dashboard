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
    available_aircraft_regs: list[str] = []
    available_ata_codes: list[str] = []

    # Tall per-engine chart (scrollable) + short pinned timeline navigator.
    gantt_figure: go.Figure = go.Figure()
    nav_figure: go.Figure = go.Figure()
    is_computing: bool = False
    has_results: bool = False
    summary_text: str = ""

    # Current navigator-selected time window, applied to the main chart.
    x_start: str = ""
    x_end: str = ""

    # Backend-only: gantt y-axis label → engine_id_str, for click-to-navigate.
    _label_to_engine: dict[str, str] = {}

    @rx.event
    def set_aircraft_reg_checked(self, reg: str, checked: bool):
        if checked and reg not in self.selected_aircraft_regs:
            self.selected_aircraft_regs = [*self.selected_aircraft_regs, reg]
        elif not checked:
            self.selected_aircraft_regs = [r for r in self.selected_aircraft_regs if r != reg]

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
        bundle = LOADED.get(gs.aircraft_type)
        if bundle is None:
            return
        prepared = prepare_schedule(bundle)
        self.available_aircraft_regs = prepared["aircraft_options"]
        self.available_ata_codes = prepared["ata_codes"]
        self.selected_aircraft_regs = []
        self.selected_ata_codes = []
        yield ScheduleState.rebuild_gantt

    @rx.event
    async def rebuild_gantt(self):
        self.is_computing = True
        yield

        gs = await self.get_state(GlobalState)
        bundle = LOADED.get(gs.aircraft_type)
        if bundle is None:
            self.is_computing = False
            return

        prepared = prepare_schedule(bundle)
        self.available_aircraft_regs = prepared["aircraft_options"]
        self.available_ata_codes = prepared["ata_codes"]
        sdf = prepared["df"]
        self._label_to_engine = dict(zip(sdf["engine_label"], sdf["engine_id_str"]))

        main_fig, nav_fig, n_events = build_schedule_figures(
            prepared["df"],
            prepared["ata_color"],
            aircraft_filter=self.selected_aircraft_regs or None,
            ata_filter=self.selected_ata_codes or None,
            start=_parse_date(gs.start_date),
            end=_parse_date(gs.end_date),
        )
        # Rebuilding resets the navigator window back to the full range.
        self.x_start = ""
        self.x_end = ""
        self.gantt_figure = main_fig
        self.nav_figure = nav_fig
        self.has_results = n_events > 0
        self.summary_text = (
            f"{n_events:,} events" if n_events > 0 else "No events match the filters."
        )
        self.is_computing = False

    @rx.event
    def sync_time_window(self, x_start: str, x_end: str, autorange: bool):
        """Apply the navigator rangeslider's window to the main (tall) chart.

        Fired by the navigator's ``on_relayout`` with the new x-axis bounds; we
        push them onto the main figure's x-axis so the two charts stay aligned.
        """
        if autorange or not x_start or not x_end:
            self.x_start = ""
            self.x_end = ""
            self.gantt_figure.update_layout(xaxis={"autorange": True})
        else:
            self.x_start = x_start
            self.x_end = x_end
            self.gantt_figure.update_layout(
                xaxis={"range": [x_start, x_end], "autorange": False}
            )
        # Reassign a fresh Figure so Reflex re-serialises and re-renders.
        self.gantt_figure = go.Figure(self.gantt_figure)

    @rx.event
    async def open_in_analysis(self, points: list[dict]):
        """Clicking a gantt point opens that engine on the Wash Analysis page.

        The clicked point's ``y`` is the gantt row label (one row per engine);
        we map it back to an engine id, preselect it on the Analysis page, and
        kick off the report — mirroring the old Dash navigate-on-click flow.
        """
        if not points:
            return
        label = points[0].get("y")
        engine_id = self._label_to_engine.get(label) if label is not None else None
        if not engine_id:
            return
        analysis = await self.get_state(AnalysisState)
        analysis.selected_engine_ids = [engine_id]
        return [rx.redirect("/analysis"), AnalysisState.run_analysis]
