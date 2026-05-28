"""Login page — `/login`."""

from __future__ import annotations

import reflex as rx

from ..state.auth import AuthState


def login_page() -> rx.Component:
    return rx.box(
        # color mode toggle — top right corner
        rx.box(
            rx.color_mode.button(),
            position="absolute",
            top="16px",
            right="20px",
        ),
        # centered card
        rx.center(
            rx.card(
                rx.vstack(
                    # branding
                    rx.vstack(
                        rx.hstack(
                            rx.icon("plane", size=26, color="var(--accent-11)"),
                            rx.heading("ECM", size="7", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "Engine Condition Monitoring",
                            size="2",
                            color="var(--gray-10)",
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.separator(width="100%"),
                    # login form
                    rx.form(
                        rx.vstack(
                            rx.vstack(
                                rx.text("Password", size="2", weight="medium"),
                                rx.input(
                                    type="password",
                                    name="password",
                                    placeholder="Enter password",
                                    width="100%",
                                    auto_focus=True,
                                ),
                                spacing="1",
                                align="stretch",
                                width="100%",
                            ),
                            # error — always rendered to avoid layout shift
                            rx.text(
                                AuthState.error,
                                size="2",
                                color="var(--red-11)",
                                min_height="1.25em",
                            ),
                            rx.button(
                                "Sign In",
                                rx.icon("log-in", size=16),
                                type="submit",
                                width="100%",
                                cursor="pointer",
                            ),
                            spacing="3",
                            align="stretch",
                            width="100%",
                        ),
                        on_submit=AuthState.login,
                        width="100%",
                    ),
                    spacing="5",
                    align="stretch",
                    width="100%",
                ),
                width="340px",
                padding="28px",
            ),
            min_height="100vh",
        ),
        position="relative",
        background="var(--gray-2)",
        min_height="100vh",
    )
