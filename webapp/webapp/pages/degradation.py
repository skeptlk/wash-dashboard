"""Long-Term Degradation page — `/`."""

from __future__ import annotations

import reflex as rx

from ..components.shell import page_shell
from ..components.selectors import aircraft_type_selector, date_range_picker
from ..state.degradation import DegradationState


def _control_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Controls", size="4"),
        aircraft_type_selector(),
        date_range_picker(),
        rx.vstack(
            rx.text("Parameter", size="2", weight="medium"),
            rx.select(
                DegradationState.parameter_options,
                value=DegradationState.selected_parameter,
                on_change=DegradationState.set_selected_parameter,
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        rx.vstack(
            rx.text("Normal rate (°C/yr)", size="2", weight="medium"),
            rx.input(
                value=DegradationState.normal_rate.to_string(),
                on_change=DegradationState.set_normal_rate,
                type="number",
                step="0.01",
                width="100%",
            ),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        rx.button(
            rx.cond(DegradationState.is_computing, rx.spinner(size="2"), rx.icon("play", size=16)),
            "Recompute",
            on_click=DegradationState.recompute,
            disabled=DegradationState.is_computing,
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


def _slope_bg(row: rx.Var) -> rx.Var:
    """Background colour that encodes degradation intensity vs normal_rate.

    diff > 0  → better than normal (green, intensity ∝ diff)
    diff < 0  → worse than normal  (red,   intensity ∝ |diff|)
    """
    diff = row["slope_per_year"].to(float) - DegradationState.normal_rate
    return rx.cond(
        ~row["is_valid_slope"],
        "transparent",
        rx.cond(
            diff > 5,  "var(--green-8)",
            rx.cond(
                diff > 2,  "var(--green-5)",
                rx.cond(
                    diff > 0,  "var(--green-3)",
                    rx.cond(
                        diff > -2, "var(--red-3)",
                        rx.cond(
                            diff > -5, "var(--red-5)",
                            "var(--red-8)",
                        ),
                    ),
                ),
            ),
        ),
    )


def _ranked_table_row(row: rx.Var) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["label"]),
        rx.table.cell(row["slope_per_year"], background_color=_slope_bg(row)),
        rx.table.cell(row["r_squared"]),
        rx.table.cell(row["n_points"]),
        rx.table.cell(row["start"]),
        rx.table.cell(row["end"]),
        on_click=DegradationState.select_engine(row["engine_id"]),
        cursor="pointer",
        _hover={"background_color": "var(--gray-3)"},
    )


def _sortable_header(label: str, column: str) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            rx.cond(
                DegradationState.sort_column == column,
                rx.cond(
                    DegradationState.sort_ascending,
                    rx.icon("chevron-up", size=14),
                    rx.icon("chevron-down", size=14),
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="center",
        ),
        on_click=DegradationState.sort_by(column),
        cursor="pointer",
        _hover={"background_color": "var(--gray-3)"},
    )


def _ranked_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    _sortable_header("Engine", "label"),
                    _sortable_header("°C / yr", "slope_per_year"),
                    _sortable_header("r²", "r_squared"),
                    _sortable_header("n", "n_points"),
                    _sortable_header("Start", "start"),
                    _sortable_header("End", "end"),
                ),
            ),
            rx.table.body(
                rx.foreach(DegradationState.sorted_ranked_rows, _ranked_table_row),
            ),
            variant="surface",
            size="2",
        ),
        max_height="600px",
        overflow_y="auto",
        width="100%",
    )


def _chart() -> rx.Component:
    return rx.plotly(data=DegradationState.chart_figure, width="100%", height="500px")


def _results_panel() -> rx.Component:
    return rx.vstack(
        rx.cond(
            DegradationState.has_results,
            rx.vstack(
                rx.heading("Engine lifetime degradation", size="4"),
                _ranked_table(),
                rx.divider(),
                rx.heading("Selected engine", size="4"),
                _chart(),
                spacing="4",
                align="stretch",
                width="100%",
            ),
            rx.callout(
                'Click "Recompute" to fit linear trends across all engines.',
                icon="info",
                width="100%",
            ),
        ),
        spacing="4",
        align="stretch",
        width="100%",
        flex="1",
    )


def degradation_page() -> rx.Component:
    return page_shell(
        "/",
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
