"""State for the Wash Schedule page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx

from ..components.schedule_fig import build_gantt_figure, prepare_schedule
from ..data import LOADED
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

    gantt_figure: go.Figure = go.Figure()
    is_computing: bool = False
    has_results: bool = False
    summary_text: str = ""

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

        fig, n_events = build_gantt_figure(
            prepared["df"],
            prepared["ata_color"],
            aircraft_filter=self.selected_aircraft_regs or None,
            ata_filter=self.selected_ata_codes or None,
            start=_parse_date(gs.start_date),
            end=_parse_date(gs.end_date),
        )
        self.gantt_figure = fig
        self.has_results = n_events > 0
        self.summary_text = (
            f"{n_events:,} events" if n_events > 0 else "No events match the filters."
        )
        self.is_computing = False
