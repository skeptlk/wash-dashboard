"""State for the Long-Term Degradation page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import plotly.graph_objects as go
import reflex as rx
from enginewash.smoothing import running_mean

from ..data import LOADED
from ..data.derived import PARAMETER_BY_NAME, flights_for
from ..trends import LifetimeTrend, compute_lifetime_trend, rank_engines_by_trend
from .base import GlobalState


_PARAM_CHOICES = ["EGTHDM", "GWFM", "DEGT"]
_SMOOTH_WINDOW = 30


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


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

    # Selected engine's plotly figure, built once on the backend (Reflex requires
    # the figure to be a single go.Figure-typed Var, not a dict of Vars).
    chart_figure: go.Figure = go.Figure()

    @rx.var
    def parameter_options(self) -> list[str]:
        return _PARAM_CHOICES

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

        trend = compute_lifetime_trend(flights, parameter)
        flights.sort(key=lambda f: f.flight_datetime)
        xs = [f.flight_datetime for f in flights]
        ys = [f.float_value for f in flights]
        fig.add_trace(go.Scattergl(
            x=xs,
            y=ys,
            mode="markers",
            name=parameter.name,
            marker={"size": 4, "opacity": 0.5},
        ))
        smoothed = running_mean(ys, window=_SMOOTH_WINDOW)
        fig.add_trace(go.Scatter(
            x=xs,
            y=smoothed,
            mode="lines",
            name=f"Running mean ({_SMOOTH_WINDOW})",
            line={"color": "steelblue", "width": 2},
        ))
        if trend.fitted_endpoints:
            fig.add_trace(go.Scatter(
                x=[p.flight_datetime for p in trend.fitted_endpoints],
                y=[p.value for p in trend.fitted_endpoints],
                mode="lines",
                name="Degradation trend",
                line={"color": "darkorange", "width": 2, "dash": "dash"},
            ))

        slope_str = (
            f"{trend.slope_per_day * 365:+.2f} °C/yr"
            if trend.slope_per_day == trend.slope_per_day
            else "n/a"
        )
        r2_str = (
            f"r²={trend.r_squared:.3f}"
            if trend.r_squared == trend.r_squared
            else ""
        )
        fig.update_layout(
            title=f"{label} — {parameter.name} slope {slope_str} {r2_str}",
            margin={"l": 50, "r": 20, "t": 50, "b": 40},
            height=480,
            showlegend=True,
        )
        self.chart_figure = fig
