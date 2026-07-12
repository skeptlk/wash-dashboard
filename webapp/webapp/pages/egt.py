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


def _model_params() -> rx.Component:
    return rx.vstack(
        rx.text("Model parameters", size="2", weight="medium"),
        rx.vstack(
            rx.hstack(
                rx.text("EGTHDM threshold", size="1"),
                rx.spacer(),
                rx.input(
                    type="number",
                    value=EgtState.egthdm_threshold,
                    on_change=EgtState.set_egthdm_threshold.debounce(400),
                    size="1",
                    width="70px",
                ),
                align="center",
                width="100%",
            ),
            rx.slider(
                value=[EgtState.egthdm_threshold],
                on_change=EgtState.set_egthdm_threshold.debounce(300),
                min=0,
                max=50,
                step=0.5,
                size="1",
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        rx.vstack(
            rx.hstack(
                rx.text("Lookback cycles", size="1"),
                rx.spacer(),
                rx.input(
                    type="number",
                    value=EgtState.lookback_cycles,
                    on_change=EgtState.set_lookback_cycles.debounce(400),
                    min=1,
                    size="1",
                    width="70px",
                ),
                align="center",
                width="100%",
            ),
            rx.slider(
                value=[EgtState.lookback_cycles],
                on_change=EgtState.set_lookback_cycles.debounce(300),
                min=1,
                max=100,
                step=1,
                size="1",
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        spacing="3",
        align="stretch",
        width="100%",
    )


def _label_row(e: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.cond(
            e["failure_value"] == 1,
            rx.icon("triangle-alert", size=12, color="var(--red-9)"),
            rx.icon("check", size=12, color="var(--green-9)"),
        ),
        rx.text(e["start"].to(str) + " → " + e["end"].to(str), size="1"),
        rx.spacer(),
        rx.icon(
            "trash-2",
            size=12,
            color="var(--gray-9)",
            cursor="pointer",
            on_click=EgtState.delete_label(e["row_id"]),
        ),
        spacing="2",
        align="center",
        width="100%",
    )


def _param_group(title: str, options: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.text(title, size="1", weight="medium", color="var(--gray-10)"),
        rx.foreach(
            options,
            lambda it: rx.checkbox(
                it["label"],
                checked=EgtState.selected_params.contains(it["id"]),
                on_change=EgtState.toggle_param(it["id"]),
                size="1",
            ),
        ),
        spacing="1",
        align="start",
        width="100%",
    )


def _iqr_toggle() -> rx.Component:
    return rx.hstack(
        rx.text("Show IQR noise bars", size="2", weight="medium"),
        rx.spacer(),
        rx.switch(
            checked=EgtState.show_iqr,
            on_change=EgtState.toggle_show_iqr,
        ),
        align="center",
        width="100%",
    )


def _param_selector() -> rx.Component:
    """Collapsible: pick which parameters get a chart row, grouped by phase."""
    return rx.vstack(
        rx.hstack(
            rx.icon(
                rx.cond(EgtState.params_open, "chevron-down", "chevron-right"),
                size=14,
            ),
            rx.text("Chart parameters", size="2", weight="medium"),
            rx.spacer(),
            rx.badge(EgtState.selected_params.length().to_string()),
            on_click=EgtState.toggle_params_open,
            cursor="pointer",
            align="center",
            width="100%",
        ),
        rx.cond(
            EgtState.params_open,
            rx.vstack(
                rx.hstack(
                    rx.input(
                        placeholder="Search parameters…",
                        value=EgtState.param_search,
                        on_change=EgtState.set_param_search,
                        size="1",
                        width="100%",
                    ),
                    rx.button(
                        "Reset",
                        on_click=EgtState.reset_params,
                        size="1",
                        variant="ghost",
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                rx.scroll_area(
                    rx.vstack(
                        _param_group("Takeoff", EgtState.takeoff_param_options),
                        _param_group("Cruise", EgtState.cruise_param_options),
                        spacing="3",
                        align="stretch",
                        width="100%",
                    ),
                    max_height="260px",
                    width="100%",
                ),
                spacing="2",
                align="stretch",
                width="100%",
            ),
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def _version_selector() -> rx.Component:
    return rx.vstack(
        rx.text("Dataset version", size="2", weight="medium"),
        rx.select.root(
            rx.select.trigger(width="100%"),
            rx.select.content(
                rx.foreach(
                    EgtState.version_options,
                    lambda o: rx.select.item(o["label"], value=o["value"]),
                ),
            ),
            value=EgtState.selected_version,
            on_change=EgtState.set_version,
            size="1",
            width="100%",
        ),
        rx.cond(
            EgtState.selected_version != "working",
            rx.text(
                "Read-only snapshot — switch to Working (live) to edit labels.",
                size="1",
                color="var(--gray-10)",
            ),
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _labeling_panel() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Label mode", size="2", weight="medium"),
            rx.spacer(),
            rx.switch(
                checked=EgtState.label_mode,
                on_change=EgtState.toggle_label_mode,
            ),
            align="center",
            width="100%",
        ),
        rx.cond(
            EgtState.label_mode,
            rx.vstack(
                rx.text(
                    "Drag-select on the chart to fill the range, or type it below.",
                    size="1",
                    color="var(--gray-10)",
                ),
                rx.vstack(
                    rx.input(
                        type="datetime-local",
                        step=1,
                        value=EgtState.label_start,
                        on_change=EgtState.set_label_start,
                        size="1",
                    ),
                    rx.input(
                        type="datetime-local",
                        step=1,
                        value=EgtState.label_end,
                        on_change=EgtState.set_label_end,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.segmented_control.root(
                    rx.segmented_control.item("No failure", value="0"),
                    rx.segmented_control.item("Failure", value="1"),
                    value=EgtState.label_value.to_string(),
                    on_change=EgtState.set_label_value,
                    size="1",
                    width="100%",
                ),
                rx.button(
                    "Apply label",
                    on_click=EgtState.apply_label,
                    size="1",
                    width="100%",
                ),
                rx.cond(
                    EgtState.manual_labels.length() > 0,
                    rx.vstack(
                        rx.text("Labels for this engine", size="1", weight="medium"),
                        rx.scroll_area(
                            rx.vstack(
                                rx.foreach(EgtState.manual_labels, _label_row),
                                spacing="1",
                                align="stretch",
                                width="100%",
                            ),
                            max_height="140px",
                            width="100%",
                        ),
                        spacing="1",
                        align="stretch",
                        width="100%",
                    ),
                ),
                rx.divider(),
                rx.button(
                    "Export & version",
                    on_click=EgtState.export_dataset,
                    size="1",
                    variant="soft",
                    width="100%",
                ),
                rx.cond(
                    EgtState.export_status != "",
                    rx.text(EgtState.export_status, size="1", color="var(--gray-10)"),
                ),
                spacing="2",
                align="stretch",
                width="100%",
            ),
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def _control_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Controls", size="4"),
        date_range_picker(),
        _model_params(),
        _iqr_toggle(),
        _param_selector(),
        _version_selector(),
        rx.cond(
            EgtState.selected_version == "working",
            _labeling_panel(),
        ),
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
            EgtState.version_error != "",
            rx.callout(
                EgtState.version_error,
                icon="triangle_alert",
                color_scheme="red",
                width="100%",
            ),
        ),
        rx.cond(
            EgtState.has_chart,
            rx.plotly(
                data=EgtState.chart_figure,
                on_selected=EgtState.on_plot_selected,
                width="100%",
                height=EgtState.chart_height,
            ),
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
