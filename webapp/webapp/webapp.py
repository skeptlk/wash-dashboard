"""ECM web app entry point — registers pages and creates the rx.App instance."""

from __future__ import annotations

import reflex as rx

from .pages.analysis import analysis_page
from .pages.degradation import degradation_page
from .pages.login import login_page
from .pages.schedule import schedule_page
from .pages.egt import egt_page
from .state.analysis import AnalysisState
from .state.auth import AuthState
from .state.egt import EgtState
from .state.schedule import ScheduleState

app = rx.App()
app.add_page(
    login_page,
    route="/login",
    title="ECM — Sign In",
    on_load=AuthState.redirect_if_authenticated,
)
app.add_page(
    degradation_page,
    route="/",
    title="ECM — Degradation",
    on_load=AuthState.require_auth,
)
app.add_page(
    analysis_page,
    route="/analysis",
    title="ECM — Wash Analysis",
    on_load=[AuthState.require_auth, AnalysisState.on_load],
)
app.add_page(
    schedule_page,
    route="/schedule",
    title="ECM — Wash Schedule",
    on_load=[AuthState.require_auth, ScheduleState.on_load],
)
app.add_page(
    egt_page,
    route="/egt",
    title="ECM — EGT Indication",
    on_load=[AuthState.require_auth, EgtState.on_load],
)