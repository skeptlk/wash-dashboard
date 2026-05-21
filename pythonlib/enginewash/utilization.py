"""Engine utilization lookup helpers.

Builds and queries a lookup of cumulative cycles/hours per
engine, used to compute cycle/hour deltas between a wash event and its loss-of-efficiency point.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Optional

from .models import UtilizationRecord


UtilizationLookup = dict[tuple[str, date], tuple[int, float]]


def build_utilization_lookup(records: Iterable[UtilizationRecord]) -> UtilizationLookup:
    """Aggregate utilization records by (engine_id, arrival_datetime.date()).
    """
    lookup: UtilizationLookup = {}
    for r in records:
        key = (r.engine_id, r.arrival_datetime.date())
        existing = lookup.get(key)
        if existing is None:
            lookup[key] = (r.total_cycles, r.total_hours)
        else:
            lookup[key] = (min(existing[0], r.total_cycles), min(existing[1], r.total_hours))
    return lookup


def lookup_utilization(
    lookup: UtilizationLookup,
    engine_id: str,
    flight_timestamp: Optional[datetime],
) -> tuple[Optional[int], Optional[float]]:
    """Return (cycles, hours) for (engine_id, when.date()).
    """
    if flight_timestamp is None:
        return (None, None)
    found = lookup.get((engine_id, flight_timestamp.date()))
    if found is None:
        return (None, None)
    return found
