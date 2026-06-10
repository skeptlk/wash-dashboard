"""Per-aircraft-type data source registry.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

_SHARED_ONWING = "https://storage.yandexcloud.net/ecm-data/s7_mdb.onwing_engine_inc_20260610.csv"
_SHARED_MAINTENANCE = "https://storage.yandexcloud.net/ecm-data/ecmapp.maintenance_20260610.parquet"
_SHARED_UTILIZATION = "https://storage.yandexcloud.net/ecm-data/utilization_prepared_2026-06-10.parquet"

class AircraftDataSources(TypedDict):
    onwing: str
    maintenance: str
    takeoff: str
    cruise: NotRequired[str]
    utilization: NotRequired[str]

AIRCRAFT_DATA_REGISTRY: dict[str, AircraftDataSources] = {
    "B737": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.b737_takeoff_20260610-merged.parquet",
        "cruise": "https://storage.yandexcloud.net/ecm-data/s7.b737_cruise_20260610-merged.parquet",
        "utilization": _SHARED_UTILIZATION,
    },
    "A320": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.a320_takeoff_20260610-merged.parquet",
        "cruise": "https://storage.yandexcloud.net/ecm-data/s7.a320_cruise_20260610-merged.parquet",
        "utilization": _SHARED_UTILIZATION,
    },
    "E170": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.erj170_takeoff_20260522.parquet",
        "utilization": _SHARED_UTILIZATION,
    },
}

AIRCRAFT_TYPES: list[str] = list(AIRCRAFT_DATA_REGISTRY.keys())
