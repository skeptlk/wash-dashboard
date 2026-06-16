"""Wash Schedule page — `/schedule`."""

from __future__ import annotations

import reflex as rx

from ..components.selectors import (
    aircraft_type_selector,
    date_range_picker,
    filterable_checklist,
)
from ..components.shell import page_shell
from ..state.schedule import ScheduleState


def _filter_section(label: str, *children: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium"),
        *children,
        spacing="1",
        align="stretch",
        width="100%",
    )


def _control_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Controls", size="4"),
        aircraft_type_selector(on_toggle=ScheduleState.toggle_aircraft_type),
        date_range_picker(),
        filterable_checklist(
            title="Aircraft",
            search_value=ScheduleState.aircraft_search,
            on_search_change=ScheduleState.set_aircraft_search,
            filtered_items=ScheduleState.filtered_aircraft,
            selected_set=ScheduleState.selected_aircraft_regs,
            on_item_check=ScheduleState.set_aircraft_reg_checked,
            on_select_all=ScheduleState.select_all_aircraft,
            on_clear=ScheduleState.clear_aircraft,
            max_height="200px",
            search_placeholder="Search registration…",
        ),
        _filter_section(
            "ATA code",
            rx.vstack(
                rx.foreach(
                    ScheduleState.available_ata_codes,
                    lambda code: rx.checkbox(
                        code,
                        checked=ScheduleState.selected_ata_codes.contains(code),
                        on_change=ScheduleState.set_ata_code_checked(code),
                        size="1",
                    ),
                ),
                spacing="1",
                align="start",
            ),
        ),
        rx.button(
            rx.cond(
                ScheduleState.is_computing,
                rx.spinner(size="2"),
                rx.icon("play", size=16),
            ),
            "Apply",
            on_click=ScheduleState.rebuild_gantt,
            disabled=ScheduleState.is_computing,
            width="100%",
            size="3",
        ),
        spacing="4",
        align="stretch",
        max_width="350px",
        width="auto",
        padding="10px",
        border="1px solid var(--gray-5)",
        border_radius="md",
        background_color="var(--gray-2)",
    )


def _results_panel() -> rx.Component:
    return rx.vstack(
        rx.cond(
            ScheduleState.is_computing,
            rx.center(rx.spinner(size="3"), width="100%", padding_y="60px"),
            rx.cond(
                ScheduleState.has_results,
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            ScheduleState.summary_text,
                            size="2",
                            color="var(--gray-11)",
                        ),
                        rx.spacer(),
                        rx.text(
                            "Click an event to open it in Wash Analysis →",
                            size="1",
                            color="var(--gray-10)",
                        ),
                        width="100%",
                        align="center",
                    ),

                    rx.plotly(
                        data=ScheduleState.gantt_figure,
                        on_click=ScheduleState.open_in_analysis,
                        width="100%",
                    ),
                    spacing="2",
                    align="stretch",
                    width="100%",
                ),
                rx.callout(
                    rx.cond(
                        ScheduleState.summary_text != "",
                        ScheduleState.summary_text,
                        'Click "Apply" to build the wash schedule chart.',
                    ),
                    icon="info",
                    width="100%",
                ),
            ),
        ),
        spacing="4",
        align="stretch",
        width="100%",
        flex="1",
    )


def schedule_page() -> rx.Component:
    return page_shell(
        "/schedule",
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
