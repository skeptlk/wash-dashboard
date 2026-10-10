"""Constructor — parameter trends across all aircraft types from DuckDB."""

import reflex as rx
from plotly.io import templates

from ..components.shell import page_shell
from ..components.trend_plotly import TrendPlotly
from ..state.constructor import ConstructorState as State


def _engine_row(engine):
    return rx.box(
        rx.text(engine["label"], size="1"),
        on_click=State.select_engine(engine["key"]),
        cursor="pointer",
        padding="4px 6px",
        border_radius="4px",
        width="100%",
        background_color=rx.cond(
            State.selected_engine == engine["key"], "var(--accent-4)", "transparent"
        ),
        _hover={"background_color": "var(--gray-3)"},
    )


def _parameter_group(title, options):
    return rx.vstack(
        rx.text(title, size="1", weight="medium", color="var(--gray-10)"),
        rx.foreach(
            options,
            lambda entry: rx.checkbox(
                entry["name"],
                checked=State.selected_params.contains(entry["id"]),
                on_change=State.toggle_param(entry["id"]),
                size="1",
            ),
        ),
        spacing="1",
        align="start",
        width="100%",
    )


def _controls():
    return rx.vstack(
        rx.heading("Constructor", size="4"),
        rx.vstack(
            rx.text("Date range", size="2", weight="medium"),
            rx.hstack(
                rx.input(
                    type="date",
                    value=State.start_date,
                    on_change=State.set_start_date,
                    size="1",
                    width="100%",
                    aria_label="Start date",
                ),
                rx.input(
                    type="date",
                    value=State.end_date,
                    on_change=State.set_end_date,
                    size="1",
                    width="100%",
                    aria_label="End date",
                ),
                width="100%",
                spacing="2",
            ),
            width="100%",
            spacing="1",
        ),
        rx.hstack(
            rx.text("Smoothing window", size="1"),
            rx.spacer(),
            rx.input(
                type="number",
                min=1,
                max=1000,
                value=State.smoothing_window,
                on_change=State.set_smoothing_window.debounce(400),
                size="1",
                width="70px",
            ),
            width="100%",
            align="center",
        ),
        rx.vstack(
            rx.hstack(
                rx.text("Parameters", size="2", weight="medium"),
                rx.badge(State.selected_params.length().to_string()),
                rx.spacer(),
                rx.button(
                    "Reset",
                    on_click=State.reset_params,
                    size="1",
                    variant="ghost",
                ),
                align="center",
                width="100%",
            ),
            rx.input(
                placeholder="Search parameters…",
                value=State.param_search,
                on_change=State.set_param_search,
                size="1",
                width="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    _parameter_group("Takeoff", State.takeoff_params),
                    _parameter_group("Cruise", State.cruise_params),
                    spacing="3",
                    align="stretch",
                    width="100%",
                ),
                max_height="260px",
                width="100%",
            ),
            width="100%",
            spacing="2",
        ),
        rx.vstack(
            rx.text("Engine", size="2", weight="medium"),
            rx.input(
                placeholder="Search engine / aircraft…",
                value=State.engine_search,
                on_change=State.set_engine_search,
                size="1",
                width="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(State.filtered_engines, _engine_row),
                    spacing="1",
                    align="stretch",
                    width="100%",
                ),
                max_height="420px",
                width="100%",
            ),
            spacing="1",
            width="100%",
        ),
        spacing="4",
        align="stretch",
        width=rx.breakpoints(initial="100%", md="300px"),
        max_height="100%",
        flex_shrink="0",
        overflow_y="auto",
        padding="10px",
        border="1px solid var(--gray-5)",
        border_radius="md",
        background_color="var(--gray-2)",
        style={
            "& .rt-TextFieldRoot": {"min_width": "0"},
            "& input[type='date']": {"font_size": "12px"},
        },
    )


def constructor_page():
    return page_shell(
        "/constructor",
        rx.flex(
            _controls(),
            rx.vstack(
                rx.cond(
                    State.error != "",
                    rx.callout(
                        State.error,
                        icon="triangle-alert",
                        color_scheme="red",
                        width="100%",
                    ),
                ),
                rx.cond(
                    State.is_computing,
                    rx.center(
                        rx.hstack(
                            rx.spinner(size="3"),
                            rx.text("Updating chart…", size="2"),
                            align="center",
                            role="status",
                        ),
                        position="absolute",
                        inset="0",
                        background_color="var(--color-overlay)",
                        z_index="1",
                    ),
                ),
                rx.cond(
                    State.has_chart,
                    rx.box(
                        TrendPlotly.create(
                            data=State.chart_figure,
                            on_relayout=State.on_plot_relayout,
                            template=rx.color_mode_cond(
                                light=templates["plotly_white"],
                                dark=templates["plotly_dark"],
                            ),
                            config={"displaylogo": False, "responsive": True},
                            width="100%",
                            height=State.chart_height,
                        ),
                        width="100%",
                        min_height="0",
                        flex="1",
                        overflow_y="auto",
                        overflow_x="hidden",
                    ),
                    rx.cond(
                        State.error == "",
                        rx.callout(
                            "Select an engine and parameters. No readings are available for the current selection.",
                            icon="info",
                            width="100%",
                        ),
                    ),
                ),
                spacing="3",
                align="stretch",
                position="relative",
                width="100%",
                min_width="0",
                flex="1",
                height=rx.breakpoints(initial="75dvh", md="100%"),
            ),
            direction=rx.breakpoints(initial="column", md="row"),
            gap="12px",
            align="start",
            width="100%",
            height=rx.breakpoints(initial="auto", md="calc(100dvh - 73px)"),
        ),
    )
