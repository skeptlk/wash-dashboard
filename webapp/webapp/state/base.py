"""Global app state: aircraft types and date range shared across pages."""

from __future__ import annotations

import reflex as rx

from ..data import AIRCRAFT_TYPES, LOADED


def _default_aircraft() -> str:
    return AIRCRAFT_TYPES[0] if AIRCRAFT_TYPES else "B737"


def _default_dates(aircraft_types: list[str]) -> tuple[str, str]:
    """Date range spanning the union of the selected types, last 2 years."""
    bundles = [LOADED[t] for t in aircraft_types if t in LOADED]
    if not bundles:
        return ("", "")
    end = max(b.date_max for b in bundles)
    start_candidate = end - __import__("pandas").DateOffset(years=2)
    start = max(min(b.date_min for b in bundles), start_candidate)
    return (start.date().isoformat(), end.date().isoformat())


class GlobalState(rx.State):
    """Shared selectors used by every page."""

    aircraft_types: list[str] = [_default_aircraft()]
    start_date: str = _default_dates([_default_aircraft()])[0]
    end_date: str = _default_dates([_default_aircraft()])[1]

    @rx.var
    def aircraft_options(self) -> list[str]:
        return AIRCRAFT_TYPES

    @rx.var
    def engine_options(self) -> list[str]:
        """Engines across all selected types (deduped, order-preserving)."""
        seen: dict[str, None] = {}
        for t in self.aircraft_types:
            bundle = LOADED.get(t)
            if bundle is None:
                continue
            for eid in bundle.available_engines:
                seen.setdefault(eid, None)
        return list(seen)

    @rx.var
    def engine_labels(self) -> dict[str, str]:
        """Merged engine labels across all selected types."""
        labels: dict[str, str] = {}
        for t in self.aircraft_types:
            bundle = LOADED.get(t)
            if bundle is None:
                continue
            labels.update(bundle.engine_labels)
        return labels

    def apply_type_toggle(self, ac_type: str, checked: bool):
        """Add/remove a type and recompute the date range.

        A plain method (not an event) so page states can reuse it from their own
        toggle handlers before refreshing their type-scoped lists.
        """
        if checked and ac_type not in self.aircraft_types:
            # Keep the registry order so the selection is stable.
            self.aircraft_types = [t for t in AIRCRAFT_TYPES if t in {*self.aircraft_types, ac_type}]
        elif not checked:
            self.aircraft_types = [t for t in self.aircraft_types if t != ac_type]
        start, end = _default_dates(self.aircraft_types)
        self.start_date = start
        self.end_date = end

    @rx.event
    def set_aircraft_type_checked(self, ac_type: str, checked: bool):
        self.apply_type_toggle(ac_type, checked)

    @rx.event
    def set_start_date(self, value: str):
        self.start_date = value

    @rx.event
    def set_end_date(self, value: str):
        self.end_date = value
