"""Parameter catalog for the EGT chart.

Every measurement column in the Boeing takeoff/cruise parquet is a plottable
parameter. Phase is simply which frame the column lives in — some params exist
only in takeoff, some only in cruise, a few (e.g. EGTHDM) in both, so a
parameter is identified by ``NAME@PHASE`` (e.g. ``EGTHDM@TAKEOFF``).

Pure pandas; the actual values come from the loaded ``AircraftBundle`` frames.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
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

# The params consumed by the enhanced failure-prediction model.
EGTHDM_TAKEOFF_ID = "EGTHDM@TAKEOFF"
DEGT_CRUISE_ID = "DEGT@CRUISE"

_CATALOG_CACHE: dict[int, list[dict]] = {}


def line_with_gaps(xs: list, ys: list) -> tuple[list, list, list[tuple]]:
    """Break a displayed curve across gaps of at least seven days.

    Only change the plotted line; the smoothed observations and model inputs
    retain their original values.
    """
    line_x, line_y, gaps = [], [], []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if i and x - xs[i - 1] >= pd.Timedelta(days=7):
            gaps.append((xs[i - 1], x))
            line_x.append(None)
            line_y.append(None)
        line_x.append(x)
        line_y.append(y)
    return line_x, line_y, gaps


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


def smoothed_series_for(
    bundle: AircraftBundle,
    engine_id: str,
    entry: dict,
    window: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> tuple[list, list, list]:
    """Readings and the model's trailing mean, clipped only after smoothing.

    Retain history before ``start`` so changing the displayed range does not
    change the curve or separate it from the model's predicted-failure points.
    """
    xs, ys = series_for(bundle, engine_id, entry)
    smoothed = pd.Series(ys, dtype=float).rolling(window, min_periods=1).mean()
    visible = [
        i for i, t in enumerate(xs)
        if (start is None or t >= start) and (end is None or t <= end)
    ]
    return (
        [xs[i] for i in visible],
        [ys[i] for i in visible],
        smoothed.iloc[visible].tolist(),
    )
