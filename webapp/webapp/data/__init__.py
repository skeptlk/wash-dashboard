"""Data layer: registry, loader, and derived helpers for aircraft datasets."""

from .registry import AIRCRAFT_DATA_REGISTRY, AIRCRAFT_TYPES


def __getattr__(name):
    # Database tools and Constructor must not trigger the legacy startup downloads.
    if name in {"LOADED", "AircraftBundle"}:
        from . import loader
        return getattr(loader, name)
    raise AttributeError(name)

__all__ = [
    "AIRCRAFT_DATA_REGISTRY",
    "AIRCRAFT_TYPES",
    "AircraftBundle",
    "LOADED",
]
