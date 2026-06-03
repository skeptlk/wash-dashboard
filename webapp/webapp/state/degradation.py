"""State for the Long-Term Degradation page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx

from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for
from ..trends import (
    LifetimeTrend,
    compute_group_trends,
    compute_lifetime_trend,
    detect_fast_spans,
    rank_engines_by_trend,
)
from .base import GlobalState


_PARAM_CHOICES = ["EGTHDM", "GWFM", "DEGT"]
_SMOOTH_WINDOW = 30
_GROUP_GAP_DAYS = 30.0
_FAST_WINDOW_DAYS = 30.0
_FAST_MIN_SPAN_DAYS = 7.0
_FAST_MULTIPLIER = 10.0
_GROUP_COLORS = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
)


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _sort_key(value):
    """Sort key that tolerates mixed/missing values within a column.

    None and placeholder strings sort to the end (in ascending order).
    """
    if value is None or value == "" or value == "—":
        return (1, 0)
    if isinstance(value, bool):
        return (0, value)
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value).lower())


def _trend_to_row(t: LifetimeTrend, label: str) -> dict:
    valid = t.slope_per_day == t.slope_per_day  # False when NaN
    return {
        "engine_id": t.engine_id,
        "label": label,
        "is_valid_slope": valid,
        "slope_per_year": round(t.slope_per_day * 365, 2) if valid else 0.0,
        "r_squared": None if t.r_squared != t.r_squared else round(t.r_squared, 3),
        "n_points": t.n_points,
        "start": t.start_datetime.date().isoformat() if t.start_datetime else "",
        "end": t.end_datetime.date().isoformat() if t.end_datetime else "",
    }


class DegradationState(rx.State):
    """Per-page state for the Long-Term Degradation view."""

    selected_parameter: str = "EGTHDM"
    selected_engine_id: str = ""
    normal_rate: float = -3.86
    is_computing: bool = False
    has_results: bool = False

    # Serialized list[LifetimeTrend] → row dicts for rx.data_table.
    ranked_rows: list[dict] = []

    # Click-to-sort: dict key of the active column, and direction.
    sort_column: str = ""
    sort_ascending: bool = True

    # Selected engine's plotly figure, built once on the backend (Reflex requires
    # the figure to be a single go.Figure-typed Var, not a dict of Vars).
    chart_figure: go.Figure = go.Figure()

    @rx.var
    def parameter_options(self) -> list[str]:
        return _PARAM_CHOICES

    @rx.var
    def sorted_ranked_rows(self) -> list[dict]:
        if not self.sort_column:
            return self.ranked_rows
        return sorted(
            self.ranked_rows,
            key=lambda r: _sort_key(r.get(self.sort_column)),
            reverse=not self.sort_ascending,
        )

    @rx.event
    def sort_by(self, column: str):
        if self.sort_column == column:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_column = column
            self.sort_ascending = True

    @rx.event
    def set_selected_parameter(self, value: str):
        self.selected_parameter = value

    @rx.event
    def set_normal_rate(self, value: str):
        try:
            self.normal_rate = float(value)
        except (ValueError, TypeError):
            pass

    @rx.event
    async def recompute(self):
        self.is_computing = True
        yield

        gs = await self.get_state(GlobalState)
        bundle = LOADED.get(gs.aircraft_type)
        if bundle is None:
            self.is_computing = False
            self.has_results = False
            self.ranked_rows = []
            return

        parameter = PARAMETER_BY_NAME[self.selected_parameter]
        start = _parse_date(gs.start_date)
        end = _parse_date(gs.end_date)

        trends: list[LifetimeTrend] = []
        for engine_id in bundle.available_engines:
            flights = flights_for(bundle, engine_id, parameter, start=start, end=end)
            if len(flights) < 2:
                continue
            trends.append(compute_lifetime_trend(flights, parameter))

        ranked = rank_engines_by_trend(trends, parameter.trend_direction)
        labels = bundle.engine_labels
        self.ranked_rows = [
            _trend_to_row(t, labels.get(t.engine_id, t.engine_id)) for t in ranked
        ]
        self.has_results = True
        self.is_computing = False

        # Auto-select the worst degrader so the user sees something immediately.
        if ranked:
            self.selected_engine_id = ranked[0].engine_id
            self._update_chart(bundle, parameter, start, end)

    @rx.event
    async def select_engine(self, engine_id: str):
        self.selected_engine_id = engine_id
        gs = await self.get_state(GlobalState)
        bundle = LOADED.get(gs.aircraft_type)
        if bundle is None:
            return
        parameter = PARAMETER_BY_NAME[self.selected_parameter]
        self._update_chart(bundle, parameter, _parse_date(gs.start_date), _parse_date(gs.end_date))

    def _update_chart(self, bundle, parameter, start, end):
        label = bundle.engine_labels.get(self.selected_engine_id, self.selected_engine_id)
        flights = flights_for(bundle, self.selected_engine_id, parameter, start=start, end=end)
        fig = go.Figure()
        if len(flights) < 2:
            fig.update_layout(title=f"{label} — insufficient data", height=480)
            self.chart_figure = fig
            return

        overall = compute_lifetime_trend(flights, parameter)
        groups = compute_group_trends(
            flights,
            parameter,
            gap_days=_GROUP_GAP_DAYS,
            smooth_window=_SMOOTH_WINDOW,
        )

        # Raw points (faint) so the underlying data stays visible behind the segments.
        flights.sort(key=lambda f: f.flight_datetime)
        fig.add_trace(go.Scattergl(
            x=[f.flight_datetime for f in flights],
            y=[f.float_value for f in flights],
            mode="markers",
            name=parameter.name,
            marker={"size": 3, "opacity": 0.25, "color": "#888"},
            showlegend=True,
        ))

        # Signed daily rate threshold; sign matches the parameter's direction so the
        # comparison in detect_fast_spans works for both UP and DOWN parameters.
        normal_per_day = self.normal_rate / 365.0
        threshold_per_day = normal_per_day * _FAST_MULTIPLIER

        for g in groups:
            color = _GROUP_COLORS[g.group_id % len(_GROUP_COLORS)]
            fig.add_trace(go.Scatter(
                x=list(g.xs),
                y=list(g.smoothed),
                mode="lines",
                name=f"g{g.group_id} smooth ({g.n_points})",
                line={"color": color, "width": 1.5},
                opacity=0.8,
            ))
            if g.fitted_endpoints:
                rate_yr = g.slope_per_day * 365.0
                fig.add_trace(go.Scatter(
                    x=[p.flight_datetime for p in g.fitted_endpoints],
                    y=[p.value for p in g.fitted_endpoints],
                    mode="lines",
                    name=f"g{g.group_id}: {rate_yr:+.1f}/yr",
                    line={"color": color, "width": 2, "dash": "dash"},
                ))

            for span in detect_fast_spans(
                g,
                rate_threshold_per_day=threshold_per_day,
                direction=parameter.trend_direction,
                window_days=_FAST_WINDOW_DAYS,
                min_span_days=_FAST_MIN_SPAN_DAYS,
            ):
                fig.add_vrect(
                    x0=span.start_datetime,
                    x1=span.end_datetime,
                    fillcolor="red",
                    opacity=0.12,
                    layer="below",
                    line_width=0,
                )

        slope_str = (
            f"{overall.slope_per_day * 365:+.2f} °C/yr"
            if overall.slope_per_day == overall.slope_per_day
            else "n/a"
        )
        r2_str = (
            f"r²={overall.r_squared:.3f}"
            if overall.r_squared == overall.r_squared
            else ""
        )
        fig.update_layout(
            title=f"{label} — {parameter.name} slope {slope_str} {r2_str}",
            margin={"l": 50, "r": 20, "t": 50, "b": 40},
            height=480,
            showlegend=True,
        )
        self.chart_figure = fig
