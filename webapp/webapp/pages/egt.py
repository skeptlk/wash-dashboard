"""EGT Indication page — `/egt`.

Boeing-only view of the EGT-sensor failure ML predictions: pick an engine,
see EGTHDM / DEGT / GWFM over time with predicted-failure spans shaded red.
"""

from __future__ import annotations

import reflex as rx

from ..components.selectors import date_range_picker
from ..components.shell import page_shell
from ..state.egt import EgtState


def _engine_row(e: rx.Var) -> rx.Component:
    is_selected = EgtState.selected_engine_id == e["id"]
    return rx.box(
        rx.hstack(
            rx.cond(
                e["has_failure"],
                rx.icon("triangle-alert", size=12, color="var(--red-9)"),
                rx.box(width="12px"),
            ),
            rx.text(e["label"], size="1"),
            spacing="2",
            align="center",
            width="100%",
        ),
        on_click=EgtState.select_engine(e["id"]),
        cursor="pointer",
        padding="4px 6px",
        border_radius="4px",
        background_color=rx.cond(is_selected, "var(--accent-4)", "transparent"),
        _hover={"background_color": "var(--gray-3)"},
        width="100%",
    )


def _control_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Controls", size="4"),
        date_range_picker(),
        rx.vstack(
            rx.text("Engine", size="2", weight="medium"),
            rx.input(
                placeholder="Search engine / aircraft…",
                value=EgtState.engine_search,
                on_change=EgtState.set_engine_search,
                size="1",
                width="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(EgtState.filtered_engines, _engine_row),
                    spacing="1",
                    align="stretch",
                    width="100%",
                ),
                max_height="420px",
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        spacing="4",
        align="stretch",
        width="280px",
        padding="10px",
        border="1px solid var(--gray-5)",
        border_radius="md",
        background_color="var(--gray-2)",
    )


def _results_panel() -> rx.Component:
    return rx.vstack(
        rx.cond(
            EgtState.has_chart,
            rx.plotly(data=EgtState.chart_figure, width="100%", height="720px"),
            rx.callout(
                "Select an engine to see its EGT failure prediction.",
                icon="info",
                width="100%",
            ),
        ),
        spacing="4",
        align="stretch",
        width="100%",
        flex="1",
    )


def egt_page() -> rx.Component:
    return page_shell(
        "/egt",
        rx.vstack(
            rx.hstack(
                _control_panel(),
                _results_panel(),
                spacing="6",
                align="start",
                width="100%",
            ),
            spacing="4",
            align="stretch",
            width="100%",
        ),
    )
