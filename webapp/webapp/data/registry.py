"""Per-aircraft-type data source registry.

Maps each aircraft type to the URLs for its onwing/maintenance/takeoff/cruise
datasets. Add new types here when they become available.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

_SHARED_ONWING = "https://storage.yandexcloud.net/ecm-data/s7_mdb._onwing_engine_20260423.csv"
_SHARED_MAINTENANCE = "https://storage.yandexcloud.net/ecm-data/ecmapp.maintenance_20260222.parquet"


class AircraftDataSources(TypedDict):
    onwing: str
    maintenance: str
    takeoff: str
    cruise: NotRequired[str]  # optional; GWFM/DEGT unavailable when absent


AIRCRAFT_DATA_REGISTRY: dict[str, AircraftDataSources] = {
    "B737": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.b737_takeoff_20260222-merged.parquet",
        "cruise": "https://storage.yandexcloud.net/ecm-data/s7.b737_cruise_20260222-merged.parquet",
    },
    "A320": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.a320_takeoff_merged_20260522.parquet",
    },
    "E170": {
        "onwing": _SHARED_ONWING,
        "maintenance": _SHARED_MAINTENANCE,
        "takeoff": "https://storage.yandexcloud.net/ecm-data/s7.erj170_takeoff_20260522.parquet",
    },
}

AIRCRAFT_TYPES: list[str] = list(AIRCRAFT_DATA_REGISTRY.keys())
