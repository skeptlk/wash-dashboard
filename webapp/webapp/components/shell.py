"""Application shell: top header with brand + tab nav."""

from __future__ import annotations

import reflex as rx

from ..state.auth import AuthState


_NAV_ITEMS = [
    ("Long-Term Degradation", "/", "trending-down"),
    ("Wash Analysis", "/analysis", "droplets"),
    ("Wash Schedule", "/schedule", "calendar"),
]


def _tab(label: str, route: str, icon: str, active_route: str) -> rx.Component:
    is_active = active_route == route
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=16),
            rx.text(label, size="2", weight="medium"),
            spacing="2",
            align="center",
            padding_y="20px",
            padding_x="5px",
            color=rx.cond(is_active, "var(--accent-11)", "var(--gray-11)"),
            border_bottom=rx.cond(
                is_active,
                "2px solid var(--accent-9)",
                "2px solid transparent",
            ),
            _hover={"color": "var(--gray-12)"},
            transition="color 120ms, border-color 120ms",
        ),
        href=route,
        text_decoration="none",
    )


def _header(active_route: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon("plane", size=22, color="var(--accent-11)"),
                rx.heading("ECM", size="5"),
                spacing="2",
                align="center",
                padding_right="6px",
            ),
            rx.hstack(
                *[_tab(label, route, icon, active_route) for label, route, icon in _NAV_ITEMS],
                spacing="2",
                align="center",
                flex="1",
            ),
            rx.tooltip(
                rx.icon_button(
                    rx.icon("log-out", size=16),
                    on_click=AuthState.logout,
                    variant="ghost",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                content="Sign out",
            ),
            rx.color_mode.button(),
            spacing="4",
            align="center",
            padding_x="6px",
            height="60px",
            width="100%",
        ),
        border_bottom="1px solid var(--gray-5)",
        background_color="var(--gray-1)",
        position="sticky",
        top="0",
        z_index="100",
        width="100%",
    )


def page_shell(active_route: str, *children: rx.Component) -> rx.Component:
    """Layout wrapper: top header + padded content area."""
    return rx.vstack(
        _header(active_route),
        rx.box(
            *children,
            padding_x="8px",
            padding_y="6px",
            width="100%",
            max_width="2400px",
            margin_x="auto",
        ),
        spacing="0",
        align="stretch",
        width="100%",
        min_height="100vh",
    )
