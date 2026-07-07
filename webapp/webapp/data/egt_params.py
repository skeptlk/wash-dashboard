"""Parameter catalog for the EGT chart.

Every measurement column in the Boeing takeoff/cruise parquet is a plottable
parameter. Phase is simply which frame the column lives in — some params exist
only in takeoff, some only in cruise, a few (e.g. EGTHDM) in both, so a
parameter is identified by ``NAME@PHASE`` (e.g. ``EGTHDM@TAKEOFF``).

Pure pandas; the actual values come from the loaded ``AircraftBundle`` frames.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .loader import AircraftBundle

# Columns that are keys/metadata, not measurements.
_META_COLS = {
    "engine_id", "aircraft_id", "engine_position",
    "flight_datetime", "flight_phase", "n1_modifier",
}

# (phase label, AircraftBundle attribute holding that phase's frame).
_PHASES = [("TAKEOFF", "takeoff_df"), ("CRUISE", "cruise_df")]

# The three params shown by default (matches the original hardcoded view).
DEFAULT_PARAMS = ["EGTHDM@TAKEOFF", "DEGT@CRUISE", "GWFM@CRUISE"]

# The one param that carries the heuristic failure-prediction overlay.
EGTHDM_TAKEOFF_ID = "EGTHDM@TAKEOFF"

_CATALOG_CACHE: dict[int, list[dict]] = {}


def catalog(bundle: AircraftBundle) -> list[dict]:
    """All plottable params, takeoff group first then cruise, each alphabetical.

    Entry: ``{"id", "name", "phase", "column", "df_attr"}``.
    """
    cached = _CATALOG_CACHE.get(id(bundle))
    if cached is not None:
        return cached
    out: list[dict] = []
    for phase, df_attr in _PHASES:
        df = getattr(bundle, df_attr)
        for col in sorted(c for c in df.columns if c not in _META_COLS):
            out.append({
                "id": f"{col.upper()}@{phase}",
                "name": col.upper(),
                "phase": phase,
                "column": col,
                "df_attr": df_attr,
            })
    _CATALOG_CACHE[id(bundle)] = out
    return out


def series_for(
    bundle: AircraftBundle,
    engine_id: str,
    entry: dict,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> tuple[list, list]:
    """Time-sorted ``(datetimes, values)`` for one engine + one catalog entry."""
    df = getattr(bundle, entry["df_attr"])
    col = entry["column"]
    mask = (df["engine_id"] == engine_id) & df[col].notna()
    if start is not None:
        mask &= df["flight_datetime"] >= start
    if end is not None:
        mask &= df["flight_datetime"] <= end
    sub = df.loc[mask, ["flight_datetime", col]].sort_values("flight_datetime")
    return sub["flight_datetime"].tolist(), sub[col].tolist()
