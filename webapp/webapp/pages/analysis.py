"""Wash Analysis page — `/analysis`."""

from __future__ import annotations

import reflex as rx

from ..components.selectors import (
    aircraft_type_selector,
    date_range_picker,
    filterable_checklist,
)
from ..components.shell import page_shell
from ..state.analysis import AnalysisState


def _num_input(label: str, value: rx.Var, on_change, min_val: int = 1) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color="var(--gray-11)"),
        rx.input(
            value=value.to_string(),
            on_change=on_change,
            type="number",
            min=str(min_val),
            step="1",
            size="1",
            width="100%",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _mode_select(label: str, options: list[str], value: rx.Var, on_change) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color="var(--gray-11)"),
        rx.select(
            options,
            value=value,
            on_change=on_change,
            size="1",
            width="100%",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _control_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Controls", size="4"),
        aircraft_type_selector(on_toggle=AnalysisState.toggle_aircraft_type),
        date_range_picker(),
        # Parameter
        rx.vstack(
            rx.text("Parameter", size="2", weight="medium"),
            rx.select(
                AnalysisState.parameter_options,
                value=AnalysisState.selected_parameter,
                on_change=AnalysisState.set_selected_parameter,
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        # Engine multi-select
        filterable_checklist(
            title="Engines",
            search_value=AnalysisState.engine_search,
            on_search_change=AnalysisState.set_engine_search,
            filtered_items=AnalysisState.filtered_engines,
            selected_set=AnalysisState.selected_engine_ids,
            on_item_check=AnalysisState.set_engine_checked,
            on_select_all=AnalysisState.select_all_engines,
            on_clear=AnalysisState.clear_engines,
            max_height="160px",
            search_placeholder="Search engine / aircraft…",
        ),
        # Smoothing & detection
        rx.divider(),
        rx.text("Smoothing & Detection", size="2", weight="medium", color="var(--gray-11)"),
        rx.grid(
            _num_input("Smooth window", AnalysisState.smooth_window, AnalysisState.set_smooth_window, min_val=5),
            _num_input("Pre-smooth", AnalysisState.pre_smooth_window, AnalysisState.set_pre_smooth_window, min_val=1),
            _num_input("N obs mean", AnalysisState.n_obs_mean, AnalysisState.set_n_obs_mean, min_val=1),
            rx.vstack(
                rx.text("LoE threshold", size="1", color="var(--gray-11)"),
                rx.input(
                    value=AnalysisState.loe_threshold.to_string(),
                    on_change=AnalysisState.set_loe_threshold,
                    type="number",
                    min="0.01",
                    step="0.01",
                    size="1",
                    width="100%",
                ),
                spacing="1",
                align="stretch",
                width="100%",
            ),
            columns="2",
            spacing="2",
            width="100%",
        ),
        rx.grid(
            _mode_select(
                "Before wash",
                ["worst", "last"],
                AnalysisState.before_wash_mode,
                AnalysisState.set_before_wash_mode,
            ),
            _mode_select(
                "After wash",
                ["best", "first"],
                AnalysisState.after_wash_mode,
                AnalysisState.set_after_wash_mode,
            ),
            columns="2",
            spacing="2",
            width="100%",
        ),
        # Run button
        rx.button(
            rx.cond(
                AnalysisState.is_computing,
                rx.spinner(size="2"),
                rx.icon("play", size=16),
            ),
            "Make Report",
            on_click=AnalysisState.run_analysis,
            disabled=AnalysisState.is_computing,
            width="100%",
            size="3",
        ),
        spacing="3",
        align="stretch",
        max_width="350px",
        width="auto",
        padding="10px",
        border="1px solid var(--gray-5)",
        border_radius="md",
        background_color="var(--gray-2)",
    )


def _delta_color(row: rx.Var) -> rx.Var:
    return rx.cond(row["delta_positive"], "var(--green-9)", "var(--red-9)")


def _summary_row(row: rx.Var) -> rx.Component:
    is_selected = AnalysisState.selected_event_key == row["row_key"]
    return rx.table.row(
        rx.table.cell(row["engine_label"], max_width="200px", overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
        rx.table.cell(row["event_index"]),
        rx.table.cell(row["maint_date"]),
        rx.table.cell(row["ata_code"]),
        rx.table.cell(row["mean_before"]),
        rx.table.cell(row["mean_after"]),
        rx.table.cell(row["delta"], color=_delta_color(row)),
        rx.table.cell(row["loe_date"]),
        rx.table.cell(row["loe_days"]),
        rx.table.cell(row["loe_cycles"]),
        rx.table.cell(row["loe_hours"]),
        on_click=AnalysisState.select_event(row["engine_id"], row["event_index"]),
        cursor="pointer",
        background_color=rx.cond(is_selected, "var(--blue-4)", "transparent"),
        _hover={"background_color": rx.cond(is_selected, "var(--blue-5)", "var(--gray-3)")},
    )


def _sortable_header(label: str, column: str) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            rx.cond(
                AnalysisState.sort_column == column,
                rx.cond(
                    AnalysisState.sort_ascending,
                    rx.icon("chevron-up", size=14),
                    rx.icon("chevron-down", size=14),
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="center",
        ),
        on_click=AnalysisState.sort_by(column),
        cursor="pointer",
        _hover={"background_color": "var(--gray-3)"},
    )


def _summary_table() -> rx.Component:
    return rx.vstack(
        rx.text(
            AnalysisState.n_events.to_string() + " wash events",
            size="2",
            color="var(--gray-11)",
        ),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _sortable_header("Engine", "engine_label"),
                        _sortable_header("#", "event_index"),
                        _sortable_header("Date", "maint_date"),
                        _sortable_header("ATA", "ata_code"),
                        _sortable_header("Before", "mean_before"),
                        _sortable_header("After", "mean_after"),
                        _sortable_header("Δ", "delta"),
                        _sortable_header("LoE date", "loe_date"),
                        _sortable_header("LoE Days", "loe_days"),
                        _sortable_header("LoE Cycles", "loe_cycles"),
                        _sortable_header("LoE Hours", "loe_hours"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(AnalysisState.sorted_summary_rows, _summary_row),
                ),
                variant="surface",
                size="1",
            ),
            overflow_x="auto",
            width="100%",
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def _results_panel() -> rx.Component:
    return rx.vstack(
        rx.cond(
            AnalysisState.is_computing,
            rx.center(rx.spinner(size="3"), width="100%", padding_y="60px"),
            rx.cond(
                AnalysisState.error_message != "",
                rx.callout(AnalysisState.error_message, icon="triangle-alert", color_scheme="orange", width="100%"),
                rx.cond(
                    AnalysisState.has_results,
                    rx.vstack(
                        rx.plotly(data=AnalysisState.chart_figure, width="100%", height="540px"),
                        rx.divider(),
                        _summary_table(),
                        rx.divider(),
                        rx.plotly(data=AnalysisState.violin_figure, width="100%", height="420px"),
                        spacing="4",
                        align="stretch",
                        width="100%",
                    ),
                    rx.callout(
                        'Select engines and click "Make Report".',
                        icon="info",
                        width="100%",
                    ),
                ),
            ),
        ),
        spacing="4",
        align="stretch",
        width="100%",
        flex="1",
    )


def analysis_page() -> rx.Component:
    return page_shell(
        "/analysis",
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
