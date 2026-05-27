"""ECM web app entry point — registers pages and creates the rx.App instance."""

from __future__ import annotations

import reflex as rx

from .pages.analysis import analysis_page
from .pages.degradation import degradation_page
from .pages.schedule import schedule_page
from .state.analysis import AnalysisState
from .state.schedule import ScheduleState


app = rx.App(
    theme=rx.theme(accent_color="blue", radius="medium"),
)
app.add_page(degradation_page, route="/", title="ECM — Degradation")
app.add_page(
    analysis_page,
    route="/analysis",
    title="ECM — Wash Analysis",
    on_load=AnalysisState.on_load,
)
app.add_page(
    schedule_page,
    route="/schedule",
    title="ECM — Wash Schedule",
    on_load=ScheduleState.on_load,
)
