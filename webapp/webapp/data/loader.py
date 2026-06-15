"""Load all aircraft datasets once at import.

Mirrors the startup-load pattern of `dashboard/app.py:36-100`. Data is held in
module-level singletons because it's small (a few hundred MB), loaded once,
and read-only after load.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .aircraft_registry import AIRCRAFT_REG
from .registry import AIRCRAFT_DATA_REGISTRY, AircraftDataSources


@dataclass
class AircraftBundle:
    """Loaded data for one aircraft type."""

    aircraft_type: str
    onwing_df: pd.DataFrame
    maintenance_df: pd.DataFrame
    takeoff_df: pd.DataFrame
    cruise_df: pd.DataFrame
    utilization_df: pd.DataFrame
    wash_maint: pd.DataFrame
    engine_labels: dict[str, str]
    engine_family_map: dict[str, str]
    available_engines: list[str]
    date_min: pd.Timestamp
    date_max: pd.Timestamp


_AC_FAMILY_ORDER = {"A": 0, "B": 1, "E": 2}

# Short display names for verbose aircraft-family strings (saves space in labels).
_FAMILY_DISPLAY = {"EMBRAER RJ": "E170"}


def _family_display(family: object) -> str:
    fam = str(family) if family else "?"
    return _FAMILY_DISPLAY.get(fam, fam)


def _eng_sort_key(eid: str, family_map: dict[str, str]) -> tuple[int, str]:
    fam = str(family_map.get(eid) or "")
    return (_AC_FAMILY_ORDER.get(fam[:1].upper() if fam else "", 3), eid)


# The utilization file is shared across aircraft types; load it once and hand the
# same frame to every bundle rather than re-downloading ~1.3M rows per type.
_UTILIZATION_CACHE: dict[str, pd.DataFrame] = {}


def _load_utilization(url: str) -> pd.DataFrame:
    cached = _UTILIZATION_CACHE.get(url)
    if cached is not None:
        return cached
    df = pd.read_parquet(url)
    df = df.dropna(subset=["engine_id", "arrival_datetime", "departure_datetime"]).copy()
    df["engine_id"] = df["engine_id"].astype(int).astype(str)
    # tah is cumulative minutes in the source; the enginewash library expects hours.
    df["total_hours"] = df["tah"] / 60.0
    df["total_cycles"] = df["tac"].astype(int)
    _UTILIZATION_CACHE[url] = df
    return df


def _load_one(aircraft_type: str, sources: AircraftDataSources) -> AircraftBundle:
    onwing_df = pd.read_csv(sources["onwing"])
    onwing_df["engine_id"] = onwing_df["engine_id"].astype(str)
    onwing_df["aircraft_id"] = onwing_df["aircraft_id"].astype(str).str.zfill(5)

    current_eids = set(onwing_df.loc[onwing_df["removal_datetime"].isna(), "engine_id"])
    last_install = (
        onwing_df.sort_values("install_datetime")
        .drop_duplicates("engine_id", keep="last")
    )
    engine_labels: dict[str, str] = {}
    for row in last_install.itertuples():
        suffix = "" if row.engine_id in current_eids else " (off wing)"
        engine_labels[row.engine_id] = (
            f"{row.engine_id} — "
            f"{_family_display(row.aircraft_family)} "
            f"{AIRCRAFT_REG.get(row.aircraft_id, row.aircraft_id)} "
            f"pos.{row.engine_position}{suffix}"
        )

    engine_family_map: dict[str, str] = (
        last_install.set_index("engine_id")["aircraft_family"].fillna("").to_dict()
    )

    maintenance_df = pd.read_parquet(sources["maintenance"])
    _ata = pd.to_numeric(maintenance_df["ata_code"], errors="coerce")
    wash_mask = (
        (
            ((_ata >= 330) & (_ata <= 349)) |
            ((_ata >= 206) & (_ata <= 210))
        ) & (~maintenance_df["deleted"])
    )
    wash_maint = maintenance_df[wash_mask].copy()

    # maint_datetime arrives as tz-aware strings (e.g. '2024-02-10 03:00:00.000 +0300');
    # normalize once to tz-naive local wall-clock to match the tz-naive flight timestamps.
    md = pd.to_datetime(wash_maint["maint_datetime"], errors="coerce")
    if md.dt.tz is not None:
        md = md.dt.tz_localize(None)
    wash_maint["maint_datetime"] = md

    takeoff_df = pd.read_parquet(sources["takeoff"])
    takeoff_df = takeoff_df.dropna(subset=["engine_id", "flight_datetime"]).copy()
    takeoff_df["engine_id"] = takeoff_df["engine_id"].astype(int).astype(str)

    cruise_url = sources.get("cruise")
    if cruise_url:
        cruise_df = pd.read_parquet(cruise_url)
        cruise_df = cruise_df.dropna(subset=["engine_id", "flight_datetime"]).copy()
        cruise_df["engine_id"] = cruise_df["engine_id"].astype(int).astype(str)
    else:
        cruise_df = pd.DataFrame(columns=["engine_id", "flight_datetime", "gwfm", "degt"])

    util_url = sources.get("utilization")
    if util_url:
        utilization_df = _load_utilization(util_url)
    else:
        utilization_df = pd.DataFrame(
            columns=["engine_id", "arrival_datetime", "departure_datetime", "total_cycles", "total_hours"]
        )

    date_min = takeoff_df["flight_datetime"].min()
    date_max = takeoff_df["flight_datetime"].max()
    if not cruise_df.empty:
        date_min = min(date_min, cruise_df["flight_datetime"].min())
        date_max = max(date_max, cruise_df["flight_datetime"].max())

    engine_ids_flight = (
        set(takeoff_df["engine_id"].unique()) | set(cruise_df["engine_id"].unique())
    )
    available_engines = sorted(
        engine_ids_flight,
        key=lambda e: _eng_sort_key(e, engine_family_map),
    )

    return AircraftBundle(
        aircraft_type=aircraft_type,
        onwing_df=onwing_df,
        maintenance_df=maintenance_df,
        takeoff_df=takeoff_df,
        cruise_df=cruise_df,
        utilization_df=utilization_df,
        wash_maint=wash_maint,
        engine_labels=engine_labels,
        engine_family_map=engine_family_map,
        available_engines=available_engines,
        date_min=date_min,
        date_max=date_max,
    )


def _load_all() -> dict[str, AircraftBundle]:
    out: dict[str, AircraftBundle] = {}
    for ac_type, sources in AIRCRAFT_DATA_REGISTRY.items():
        print(f"Loading {ac_type} data…")
        out[ac_type] = _load_one(ac_type, sources)
        print(f"  {ac_type}: {len(out[ac_type].available_engines)} engines")
    return out


LOADED: dict[str, AircraftBundle] = _load_all()
