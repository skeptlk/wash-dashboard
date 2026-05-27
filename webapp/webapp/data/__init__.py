"""Data layer: registry, loader, and derived helpers for aircraft datasets."""

from .loader import LOADED, AircraftBundle
from .registry import AIRCRAFT_DATA_REGISTRY, AIRCRAFT_TYPES

__all__ = [
    "AIRCRAFT_DATA_REGISTRY",
    "AIRCRAFT_TYPES",
    "AircraftBundle",
    "LOADED",
]
