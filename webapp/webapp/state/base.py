"""Global app state: aircraft type and date range shared across pages."""

from __future__ import annotations

import reflex as rx

from ..data import AIRCRAFT_TYPES, LOADED


def _default_aircraft() -> str:
    return AIRCRAFT_TYPES[0] if AIRCRAFT_TYPES else "B737"


def _default_dates(aircraft_type: str) -> tuple[str, str]:
    bundle = LOADED.get(aircraft_type)
    if bundle is None:
        return ("", "")
    # Default to the last 2 years of data.
    end = bundle.date_max
    start_candidate = end - __import__("pandas").DateOffset(years=2)
    start = max(bundle.date_min, start_candidate)
    return (start.date().isoformat(), end.date().isoformat())


class GlobalState(rx.State):
    """Shared selectors used by every page."""

    aircraft_type: str = _default_aircraft()
    start_date: str = _default_dates(_default_aircraft())[0]
    end_date: str = _default_dates(_default_aircraft())[1]

    @rx.var
    def aircraft_options(self) -> list[str]:
        return AIRCRAFT_TYPES

    @rx.var
    def engine_options(self) -> list[str]:
        bundle = LOADED.get(self.aircraft_type)
        if bundle is None:
            return []
        return bundle.available_engines

    @rx.var
    def engine_labels(self) -> dict[str, str]:
        bundle = LOADED.get(self.aircraft_type)
        if bundle is None:
            return {}
        return bundle.engine_labels

    @rx.event
    def set_aircraft_type(self, value: str):
        self.aircraft_type = value
        start, end = _default_dates(value)
        self.start_date = start
        self.end_date = end

    @rx.event
    def set_start_date(self, value: str):
        self.start_date = value

    @rx.event
    def set_end_date(self, value: str):
        self.end_date = value
