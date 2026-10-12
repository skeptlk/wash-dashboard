"""Constructor — parameter trends across all aircraft types from DuckDB."""

import reflex as rx
from plotly.io import templates

from ..components.shell import page_shell
from ..components.constructor_plotly import ConstructorPlotly
from ..components.constructor_picker import ConstructorPicker
from ..state.constructor import ConstructorState as State


def _controls():
    return rx.vstack(
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
            rx.text("Smooth window", size="1"),
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
            rx.text("Predictions", size="2", weight="medium"),
            rx.hstack(
                rx.text("EGT Indication", size="1"),
                rx.spacer(),
                rx.switch(
                    checked=State.egt_indication_enabled,
                    on_change=State.set_egt_indication,
                    aria_label="EGT Indication",
                    size="1",
                ),
                width="100%",
                align="center",
            ),
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            rx.hstack(
                rx.text("Parameters", size="2", weight="medium"),
                rx.flex(
                    rx.foreach(
                        State.selected_params,
                        lambda pid: rx.badge(
                            pid.split("@")[0], title=pid, color_scheme="blue"
                        ),
                    ),
                    wrap="wrap",
                    gap="4px",
                    flex="1",
                    min_width="0",
                ),
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
            ConstructorPicker.create(
                options=State.catalog,
                selected=State.selected_params,
                multiple=True,
                on_pick=State.toggle_param,
            ),
            width="100%",
            spacing="2",
        ),
        rx.vstack(
            rx.text("Engine", size="2", weight="medium"),
            ConstructorPicker.create(
                options=State.engines,
                selected=rx.Var.create([State.selected_engine]),
                multiple=False,
                on_pick=lambda key, checked: State.select_engine(key),
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
                    State.is_computing & (State.loaded_params == 0),
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
                    State.is_computing & (State.loaded_params > 0),
                    rx.hstack(
                        rx.spinner(size="1"),
                        rx.text(
                            "Loading parameters: ",
                            State.loaded_params,
                            " / ",
                            State.selected_params.length(),
                            size="1",
                        ),
                        align="center",
                        role="status",
                        position="absolute",
                        top="8px",
                        right="16px",
                        z_index="1",
                        pointer_events="none",
                    ),
                ),
                rx.cond(
                    State.has_chart,
                    rx.box(
                        ConstructorPlotly.create(
                            data=State.chart_figure,
                            generation=State.chart_generation,
                            offset=State.chart_offset,
                            data_generation=State.chart_data_generation,
                            on_initialized=State.load_next_parameter(
                                State.chart_generation,
                                State.loaded_params,
                            ),
                            on_update=State.load_next_parameter(
                                State.chart_generation,
                                State.loaded_params,
                            ),
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
                        style={
                            "& .modebar-container": {
                                "top": "auto !important",
                                "bottom": "0",
                            },
                            "& .js-plotly-plot .plotly .modebar": {
                                "top": "auto",
                                "bottom": "2px",
                            },
                            "& .js-plotly-plot .plotly .modebar [data-title]::before, & .js-plotly-plot .plotly .modebar [data-title]::after": {
                                "top": "auto",
                                "bottom": "110%",
                            },
                            "& .js-plotly-plot .plotly .modebar [data-title]::before": {
                                "margin_top": "0",
                                "margin_bottom": "-12px",
                                "border_bottom_color": "transparent",
                                "border_top_color": "#69738a",
                            },
                        },
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
