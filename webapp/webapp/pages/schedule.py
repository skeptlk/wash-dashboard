"""Wash Schedule page — `/schedule`."""

from __future__ import annotations

import reflex as rx

from ..components.selectors import aircraft_type_selector, date_range_picker
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
        aircraft_type_selector(),
        date_range_picker(),
        _filter_section(
            "Aircraft",
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(
                        ScheduleState.available_aircraft_regs,
                        lambda reg: rx.checkbox(
                            reg,
                            checked=ScheduleState.selected_aircraft_regs.contains(reg),
                            on_change=ScheduleState.set_aircraft_reg_checked(reg),
                            size="1",
                        ),
                    ),
                    spacing="1",
                    align="start",
                ),
                max_height="200px",
                width="100%",
            ),
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
        width="280px",
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
                    rx.text(
                        ScheduleState.summary_text,
                        size="2",
                        color="var(--gray-11)",
                    ),
                    rx.plotly(
                        data=ScheduleState.gantt_figure,
                        width="100%",
                        height="100%",
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
            rx.heading("Wash Schedule", size="7"),
            rx.text(
                "Wash events per engine over time, coloured by ATA code.",
                color="var(--gray-11)",
            ),
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
