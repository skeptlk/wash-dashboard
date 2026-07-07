"""Helpers that bridge raw DataFrames to enginewash library inputs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from enginewash import (
    DEGT,
    EGTHDM,
    GWFM,
    FlightRecord,
    MaintenanceRecord,
    UtilizationRecord,
    WashParameter,
)

from .loader import AircraftBundle


# Maps a parameter to (column name, source dataframe attribute) on AircraftBundle.
_PARAM_SOURCES: dict[str, tuple[str, str]] = {
    "EGTHDM": ("egthdm", "takeoff_df"),
    "GWFM": ("gwfm", "cruise_df"),
    "DEGT": ("degt", "cruise_df"),
}

PARAMETER_BY_NAME: dict[str, WashParameter] = {
    "EGTHDM": EGTHDM,
    "GWFM": GWFM,
    "DEGT": DEGT,
}


def flights_for(
    bundle: AircraftBundle,
    engine_id: str,
    parameter: WashParameter,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[FlightRecord]:
    """Build a list of FlightRecord for one engine and one parameter, optionally
    constrained to a date range.
    """
    col, df_attr = _PARAM_SOURCES[parameter.name]
    df: pd.DataFrame = getattr(bundle, df_attr)
    mask = (df["engine_id"] == engine_id) & df[col].notna()
    if start is not None:
        mask &= df["flight_datetime"] >= start
    if end is not None:
        mask &= df["flight_datetime"] <= end
    sub = df.loc[mask, ["flight_datetime", col]]
    return [
        FlightRecord(
            engine_id=engine_id,
            flight_datetime=row.flight_datetime.to_pydatetime()
            if hasattr(row.flight_datetime, "to_pydatetime")
            else row.flight_datetime,
            parameter_name=parameter.name,
            flight_phase=parameter.flight_phase,
            float_value=float(getattr(row, col)),
        )
        for row in sub.itertuples(index=False)
    ]


def matched_utilization_for(
    bundle: AircraftBundle,
    engine_id: str,
    parameter: WashParameter,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    tolerance_hours: int = 12,
) -> tuple[list[datetime], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Match each parameter reading of one engine to its cumulative TAC/TAH.

    Each flight reading is paired with the latest utilization row whose departure is
    at-or-before the flight and within ``tolerance_hours`` (backward as-of join, like
    the degradation study notebook). Returns aligned sequences

        ``(datetimes, values, total_cycles, total_hours, aircraft_id_keys)``

    suitable for ``trends.compute_utilization_trend``. Readings with no utilization
    match within tolerance are dropped; empty arrays are returned when the engine has
    no flights or no utilization data.
    """
    empty = ([], np.array([]), np.array([]), np.array([]), np.array([]))
    col, df_attr = _PARAM_SOURCES[parameter.name]
    fdf: pd.DataFrame = getattr(bundle, df_attr)
    mask = (fdf["engine_id"] == engine_id) & fdf[col].notna()
    if start is not None:
        mask &= fdf["flight_datetime"] >= start
    if end is not None:
        mask &= fdf["flight_datetime"] <= end
    flights = fdf.loc[mask, ["flight_datetime", col]].sort_values("flight_datetime")

    udf = bundle.utilization_df
    if flights.empty or udf.empty or "aircraft_id_key" not in udf.columns:
        return empty
    u = (
        udf.loc[
            udf["engine_id"] == engine_id,
            ["departure_datetime", "total_cycles", "total_hours", "aircraft_id_key"],
        ]
        .sort_values("departure_datetime")
    )
    if u.empty:
        return empty

    merged = pd.merge_asof(
        flights,
        u,
        left_on="flight_datetime",
        right_on="departure_datetime",
        direction="backward",
        tolerance=pd.Timedelta(hours=tolerance_hours),
    ).dropna(subset=["total_cycles", "total_hours", "aircraft_id_key"])
    if merged.empty:
        return empty

    datetimes = [
        ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        for ts in merged["flight_datetime"]
    ]
    return (
        datetimes,
        merged[col].to_numpy(dtype=float),
        merged["total_cycles"].to_numpy(dtype=float),
        merged["total_hours"].to_numpy(dtype=float),
        merged["aircraft_id_key"].to_numpy(),
    )


def utilization_for(
    bundle: AircraftBundle, engine_ids: set[str]
) -> list[UtilizationRecord]:
    """Build UtilizationRecords for the given engines in a single pass.

    Returns an empty list when the bundle has no utilization data. Cycles/hours
    are already cumulative in the source (total_cycles / total_hours, the latter
    converted from minutes during load).
    """
    df = bundle.utilization_df
    if df.empty or not engine_ids:
        return []
    sub = df.loc[
        df["engine_id"].isin(engine_ids),
        ["engine_id", "total_cycles", "total_hours", "departure_datetime", "arrival_datetime"],
    ]
    return [
        UtilizationRecord(
            engine_id=row.engine_id,
            total_cycles=int(row.total_cycles),
            total_hours=float(row.total_hours),
            departure_datetime=row.departure_datetime.to_pydatetime()
            if hasattr(row.departure_datetime, "to_pydatetime")
            else row.departure_datetime,
            arrival_datetime=row.arrival_datetime.to_pydatetime()
            if hasattr(row.arrival_datetime, "to_pydatetime")
            else row.arrival_datetime,
        )
        for row in sub.itertuples(index=False)
    ]


def maint_events_for_ata(
    bundle: AircraftBundle,
    engine_id: str,
    ata_codes: list[str],
) -> list[tuple[datetime, str]]:
    """Return (maint_datetime, ata_code) pairs for the given ATA codes.

    Strips timezone info from timestamps to match the tz-naive flight datetimes.
    """
    df = bundle.maintenance_df
    mask = (df["engine_id"] == engine_id) & (~df["deleted"]) & df["ata_code"].isin(ata_codes)
    sub = df.loc[mask, ["maint_datetime", "ata_code"]].dropna(subset=["maint_datetime"])
    result = []
    for row in sub.itertuples(index=False):
        dt = pd.to_datetime(row.maint_datetime)
        if dt.tzinfo is not None:
            dt = dt.tz_localize(None)
        result.append((dt.to_pydatetime(), row.ata_code))
    return result


def maint_for(bundle: AircraftBundle, engine_id: str) -> list[MaintenanceRecord]:
    """Build a list of MaintenanceRecord for one engine from wash_maint.
    """
    df = bundle.wash_maint
    sub = df.loc[df["engine_id"] == engine_id, ["maint_datetime", "ata_code"]]
    return [
        MaintenanceRecord(
            engine_id=engine_id,
            maint_datetime=row.maint_datetime.to_pydatetime()
            if hasattr(row.maint_datetime, "to_pydatetime")
            else row.maint_datetime,
            ata_code=str(row.ata_code) if pd.notna(row.ata_code) else None,
        )
        for row in sub.itertuples(index=False)
        if pd.notna(row.maint_datetime)
    ]
