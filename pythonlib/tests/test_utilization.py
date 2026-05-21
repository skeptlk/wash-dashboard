"""Tests for the utilization lookup helpers."""

from datetime import date, datetime

from enginewash import UtilizationRecord
from enginewash.utilization import build_utilization_lookup, lookup_utilization


def test_build_lookup_keys_by_engine_and_date():
    records = [
        UtilizationRecord("E1", 100, 200.0, datetime(2024, 3, 1, 6, 0), datetime(2024, 3, 1, 9, 0)),
        UtilizationRecord("E2", 500, 1000.0, datetime(2024, 3, 1, 7, 0), datetime(2024, 3, 1, 10, 0)),
    ]
    lookup = build_utilization_lookup(records)

    assert lookup[("E1", date(2024, 3, 1))] == (100, 200.0)
    assert lookup[("E2", date(2024, 3, 1))] == (500, 1000.0)


def test_build_lookup_takes_min_for_same_engine_day():
    """Mirrors R's `summarise(tah = min(tah), tac = min(tac))` per engine-day."""
    records = [
        UtilizationRecord("E1", 110, 220.0, datetime(2024, 3, 1, 4, 0), datetime(2024, 3, 1, 7, 0)),
        UtilizationRecord("E1", 105, 215.0, datetime(2024, 3, 1, 12, 0), datetime(2024, 3, 1, 15, 0)),
        UtilizationRecord("E1", 100, 210.0, datetime(2024, 3, 1, 20, 0), datetime(2024, 3, 1, 23, 0)),
    ]
    lookup = build_utilization_lookup(records)

    assert lookup[("E1", date(2024, 3, 1))] == (100, 210.0)


def test_build_lookup_different_days():
    records = [
        UtilizationRecord("E1", 100, 200.0, datetime(2024, 3, 1, 9, 0), datetime(2024, 3, 1, 12, 0)),
        UtilizationRecord("E1", 110, 220.0, datetime(2024, 3, 2, 9, 0), datetime(2024, 3, 2, 12, 0)),
    ]
    lookup = build_utilization_lookup(records)

    assert lookup[("E1", date(2024, 3, 1))] == (100, 200.0)
    assert lookup[("E1", date(2024, 3, 2))] == (110, 220.0)


def test_build_lookup_empty():
    assert build_utilization_lookup([]) == {}


def test_lookup_hit():
    lookup = {("E1", date(2024, 3, 1)): (100, 200.0)}
    assert lookup_utilization(lookup, "E1", datetime(2024, 3, 1, 14, 30)) == (100, 200.0)


def test_lookup_miss_returns_none_pair():
    lookup = {("E1", date(2024, 3, 1)): (100, 200.0)}
    assert lookup_utilization(lookup, "E1", datetime(2024, 3, 2, 14, 30)) == (None, None)
    assert lookup_utilization(lookup, "E2", datetime(2024, 3, 1, 14, 30)) == (None, None)


def test_lookup_when_none():
    lookup = {("E1", date(2024, 3, 1)): (100, 200.0)}
    assert lookup_utilization(lookup, "E1", None) == (None, None)


def test_lookup_empty_dict():
    assert lookup_utilization({}, "E1", datetime(2024, 3, 1)) == (None, None)
