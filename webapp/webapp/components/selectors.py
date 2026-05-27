"""Shared selectors bound to GlobalState."""

from __future__ import annotations

import reflex as rx

from ..state.base import GlobalState


def aircraft_type_selector() -> rx.Component:
    return rx.vstack(
        rx.text("Aircraft type", size="2", weight="medium"),
        rx.select(
            GlobalState.aircraft_options,
            value=GlobalState.aircraft_type,
            on_change=GlobalState.set_aircraft_type,
            width="100%",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def date_range_picker() -> rx.Component:
    return rx.vstack(
        rx.text("Date range", size="2", weight="medium"),
        rx.hstack(
            rx.input(
                type="date",
                value=GlobalState.start_date,
                on_change=GlobalState.set_start_date,
                width="100%",
            ),
            rx.input(
                type="date",
                value=GlobalState.end_date,
                on_change=GlobalState.set_end_date,
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )
