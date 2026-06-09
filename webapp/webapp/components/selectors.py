"""Shared selectors bound to GlobalState."""

from __future__ import annotations

from typing import Callable

import reflex as rx

from ..state.base import GlobalState


def aircraft_type_selector(on_toggle=None) -> rx.Component:
    """Multi-select aircraft type.

    ``on_toggle`` is an optional ``(ac_type, checked)`` event handler so a page
    can refresh its type-scoped lists when the selection changes; if omitted, the
    global setter is used (sufficient for pages whose lists rebuild on a button).
    """
    handler = on_toggle if on_toggle is not None else GlobalState.set_aircraft_type_checked
    return rx.vstack(
        rx.text("Aircraft type", size="2", weight="medium"),
        rx.hstack(
            rx.foreach(
                GlobalState.aircraft_options,
                lambda t: rx.checkbox(
                    t,
                    checked=GlobalState.aircraft_types.contains(t),
                    on_change=handler(t),
                    size="1",
                ),
            ),
            spacing="3",
            wrap="wrap",
            align="center",
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


def filterable_checklist(
    *,
    title: str,
    search_value: rx.Var,
    on_search_change: Callable,
    filtered_items: rx.Var,
    selected_set: rx.Var,
    on_item_check: Callable,
    on_select_all,
    on_clear,
    max_height: str = "200px",
    search_placeholder: str = "Search…",
) -> rx.Component:
    """A searchable, bulk-selectable checkbox list.

    ``filtered_items`` is a list[dict] of ``{"id", "label"}``; ``on_item_check`` is
    a bound event handler taking ``(id, checked)`` — mirroring the partial-bind
    pattern used elsewhere (e.g. ``set_engine_checked(eid)``).
    """
    return rx.vstack(
        rx.hstack(
            rx.text(title, size="2", weight="medium"),
            rx.spacer(),
            rx.button("All", on_click=on_select_all, size="1", variant="ghost"),
            rx.button("Clear", on_click=on_clear, size="1", variant="ghost"),
            width="100%",
            align="center",
        ),
        rx.input(
            placeholder=search_placeholder,
            value=search_value,
            on_change=on_search_change,
            size="1",
            width="100%",
        ),
        rx.scroll_area(
            rx.vstack(
                rx.foreach(
                    filtered_items,
                    lambda it: rx.checkbox(
                        it["label"],
                        checked=selected_set.contains(it["id"]),
                        on_change=on_item_check(it["id"]),
                        size="1",
                    ),
                ),
                spacing="1",
                align="start",
            ),
            max_height=max_height,
            width="100%",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )
