"""Constructor reads through Quack, with explicit file mode for offline use."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from .aircraft_registry import AIRCRAFT_REG
from .quack import connect_remote

DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "data" / "flights.duckdb"
META_COLUMNS = {
    "aircraft_type",
    "aircraft_id",
    "engine_position",
    "engine_id",
    "flight_datetime",
    "flight_phase",
    "n1_modifier",
}


def database_path() -> Path:
    return (
        Path(os.environ.get("FLIGHT_DATABASE_PATH", str(DEFAULT_DATABASE)))
        .expanduser()
        .resolve()
    )


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect(path: Path | None = None):
    # An explicit path is reserved for offline tools/tests. Remote failures must
    # never silently open another database or compete with the service's lock.
    mode = os.environ.get("FLIGHT_DATABASE_MODE", "quack")
    if path is None and mode == "quack":
        return connect_remote()
    if path is None and mode != "file":
        raise ValueError("FLIGHT_DATABASE_MODE must be quack or file.")
    path = path or database_path()
    if not path.is_file():
        raise FileNotFoundError(
            "Flight database is not available. Run the flight-data migration first "
            "(see webapp/README.md)."
        )
    db = duckdb.connect(str(path), read_only=True)
    try:
        db.execute("""
            CREATE TEMP VIEW constructor_reports AS
            SELECT rowid AS _report_rowid, * FROM reports
        """)
        return db
    except Exception:
        db.close()
        raise


def engine_options(path: Path | None = None) -> list[dict]:
    with connect(path) as db:
        rows = db.execute("""
            SELECT aircraft_type, engine_id, arg_max(aircraft_id, flight_datetime)
            FROM reports WHERE engine_id IS NOT NULL AND flight_datetime IS NOT NULL
            GROUP BY aircraft_type, engine_id ORDER BY aircraft_type, engine_id
        """).fetchall()
    return [
        {
            "id": eid,
            "aircraft_type": family,
            "key": f"{family}:{eid}",
            "label": f"{eid}: {family} {AIRCRAFT_REG.get(aid, aid) or ''}",
        }
        for family, eid, aid in rows
    ]


def parameter_catalog(aircraft_type: str, path: Path | None = None) -> list[dict]:
    with connect(path) as db:
        rows = db.execute(
            """
            SELECT flight_phase, column_name FROM report_parameters
            WHERE aircraft_type = ?
            ORDER BY CASE flight_phase WHEN 'TAKEOFF' THEN 0 ELSE 1 END, column_name
        """,
            [aircraft_type],
        ).fetchall()
    return [
        {
            "id": f"{col.upper()}@{phase}",
            "name": col.upper(),
            "phase": phase,
            "column": col,
        }
        for phase, col in rows
    ]


def date_bounds(aircraft_type: str, engine_id: str, path: Path | None = None):
    with connect(path) as db:
        return db.execute(
            """
            SELECT min(flight_datetime), max(flight_datetime) FROM reports
            WHERE aircraft_type = ? AND engine_id = ?
        """,
            [aircraft_type, engine_id],
        ).fetchone()


def read_trends(
    aircraft_type: str,
    engine_id: str,
    parameter_ids: list[str],
    start: str,
    end: str,
    window: int = 26,
    path: Path | None = None,
):
    """Filter in SQL, keeping trailing history before clipping the date window.

    The end date includes the entire selected day. Null readings do not count
    towards the rolling window, matching the EGT page's trailing mean.
    """
    lo = pd.Timestamp(start) if start else None
    hi = pd.Timestamp(end) + pd.Timedelta(days=1) if end else None
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError("Start date must be on or before end date.")
    if not 1 <= window <= 1000:
        raise ValueError("Smoothing window must be between 1 and 1000.")
    catalog = {e["id"]: e for e in parameter_catalog(aircraft_type, path)}
    if any(pid not in catalog for pid in parameter_ids):
        raise ValueError("Unknown chart parameter.")
    series = []
    with connect(path) as db:
        for pid in parameter_ids:
            entry = catalog[pid]
            column = quote_identifier(entry["column"])
            frame = db.execute(
                f"""
                SELECT * FROM (
                    SELECT flight_datetime, {column} AS value,
                        avg({column}) OVER (
                            ORDER BY flight_datetime, _report_rowid ROWS BETWEEN {window - 1} PRECEDING
                            AND CURRENT ROW
                        ) AS smoothed
                    FROM constructor_reports
                    WHERE aircraft_type = ? AND engine_id = ? AND flight_phase = ?
                      AND {column} IS NOT NULL AND flight_datetime IS NOT NULL
                      AND (? IS NULL OR flight_datetime < ?)
                ) WHERE (? IS NULL OR flight_datetime >= ?) ORDER BY flight_datetime
            """,
                [aircraft_type, engine_id, entry["phase"], hi, hi, lo, lo],
            ).fetchdf()
            series.append((entry, frame))
        history = db.execute(
            """
            SELECT install_datetime, removal_datetime, reason_for_removal
            FROM onwing WHERE engine_id = ?
        """,
            [engine_id],
        ).fetchall()
    events = [
        (dt, kind, reason)
        for installed, removed, removal_reason in history
        for dt, kind, reason in (
            (installed, "Install", None),
            (removed, "Removal", removal_reason),
        )
        if dt is not None and (lo is None or lo <= dt) and (hi is None or dt < hi)
    ]
    return series, sorted(set(events), key=lambda e: e[0])
