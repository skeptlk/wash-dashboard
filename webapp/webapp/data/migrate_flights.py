"""One-time Parquet → DuckDB migration, runnable without dashboard startup.

From the repository root:
    PYTHONPATH=webapp python -m webapp.data.migrate_flights
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse
from urllib.request import urlretrieve

import duckdb
import pandas as pd
from pandas.api.types import is_numeric_dtype

from .flight_db import META_COLUMNS, database_path
from .registry import AIRCRAFT_DATA_REGISTRY


def normalize_id(values: pd.Series, *, aircraft: bool = False) -> pd.Series:
    # Float IDs in merged Parquet are integers with nulls; keep nulls as SQL NULL.
    result = values.astype("string").str.replace(r"^(\d+)\.0$", r"\1", regex=True)
    return result.str.zfill(5) if aircraft else result


def migrate(
    path: Path, registry: dict, source_dir: Path | None = None, replace: bool = False
) -> list[tuple]:
    """Build beside the destination and publish only after all sources validate.

    Refuses an existing destination unless --replace was explicitly selected.
    Rerunning with --replace rebuilds the snapshot, never appends duplicate rows.
    """
    path = path.resolve()
    if path.exists() and not replace:
        raise FileExistsError(f"{path} already exists; use --replace to rebuild it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="flight-migration-", dir=path.parent
    ) as work:
        work = Path(work)
        staging = work / "flights.duckdb"
        cache = {}

        def local(source):
            if source in cache:
                return cache[source]
            filename = Path(urlparse(source).path).name
            target = source_dir / filename if source_dir else work / filename
            if source_dir:
                if not target.is_file():
                    raise FileNotFoundError(target)
            elif urlparse(source).scheme in {"https", "http"}:
                urlretrieve(source, target)
            else:
                target = Path(source)
            cache[source] = target
            return target

        counts = []
        with duckdb.connect(str(staging)) as db:
            db.execute(
                "CREATE TABLE report_parameters (aircraft_type VARCHAR, flight_phase VARCHAR, column_name VARCHAR)"
            )
            db.execute(
                "CREATE TABLE import_sources (aircraft_type VARCHAR, flight_phase VARCHAR, source VARCHAR, row_count BIGINT, imported_at TIMESTAMP)"
            )
            tables = []
            for family, sources in registry.items():
                for phase in ("takeoff", "cruise"):
                    if phase not in sources:
                        continue
                    source = sources[phase]
                    frame = pd.read_parquet(local(source))
                    required = {
                        "aircraft_id",
                        "engine_position",
                        "engine_id",
                        "flight_datetime",
                        "flight_phase",
                    }
                    if missing := required - set(frame.columns):
                        raise ValueError(f"{source}: missing columns {sorted(missing)}")
                    if (
                        frame.columns.str.lower().duplicated().any()
                        or "aircraft_type" in frame
                    ):
                        raise ValueError(f"{source}: conflicting column names")
                    if not frame.flight_phase.eq(phase.upper()).all():
                        raise ValueError(f"{source}: unexpected flight phase")
                    frame["aircraft_type"] = family
                    frame["engine_id"] = normalize_id(frame.engine_id)
                    frame["aircraft_id"] = normalize_id(
                        frame.aircraft_id, aircraft=True
                    )
                    frame["flight_datetime"] = pd.to_datetime(frame.flight_datetime)
                    parameters = [
                        (family, phase.upper(), col)
                        for col in frame
                        if col not in META_COLUMNS and is_numeric_dtype(frame[col])
                    ]
                    if parameters:
                        db.executemany(
                            "INSERT INTO report_parameters VALUES (?, ?, ?)", parameters
                        )
                    table = f"source_{len(tables)}"
                    db.register("source_frame", frame)
                    db.execute(f"CREATE TABLE {table} AS SELECT * FROM source_frame")
                    db.unregister("source_frame")
                    tables.append(table)
                    count = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    if count != len(frame):
                        raise ValueError(f"Row count mismatch for {source}")
                    db.execute(
                        "INSERT INTO import_sources (aircraft_type, flight_phase, source, row_count, imported_at) VALUES (?, ?, ?, ?, current_timestamp)",
                        [family, phase.upper(), source, count],
                    )
                    counts.append((family, phase.upper(), count))
                    print(f"{family} {phase.upper()}: {count:,} reports", flush=True)
            if not tables:
                raise ValueError("No flight sources configured")
            union = " UNION ALL BY NAME ".join(
                f"SELECT * FROM {table}" for table in tables
            )
            db.execute(
                f"CREATE TABLE reports AS SELECT * FROM ({union}) ORDER BY aircraft_type, engine_id, flight_datetime"
            )
            if db.execute("SELECT count(*) FROM reports").fetchone()[0] != sum(
                c for _, _, c in counts
            ):
                raise ValueError("Combined report row count mismatch")
            for table in tables:
                db.execute(f"DROP TABLE {table}")
            # The registry commonly points every aircraft type at the same history.
            frames = [
                pd.read_csv(
                    local(source),
                    dtype={"engine_id": "string", "aircraft_id": "string"},
                )
                for source in dict.fromkeys(s["onwing"] for s in registry.values())
            ]
            history = pd.concat(frames, ignore_index=True).drop_duplicates()
            history["engine_id"] = normalize_id(history.engine_id)
            history["aircraft_id"] = normalize_id(history.aircraft_id, aircraft=True)
            for col in ("install_datetime", "removal_datetime"):
                history[col] = pd.to_datetime(history[col])
            db.register("history", history)
            db.execute("CREATE TABLE onwing AS SELECT * FROM history")
            db.unregister("history")
            db.execute("CHECKPOINT")
        # All connections are closed before publishing the complete database.
        os.replace(staging, path)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=database_path())
    parser.add_argument(
        "--source-dir", type=Path, help="Read registry filenames from a local directory"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Rebuild the existing snapshot; stop writers first",
    )
    args = parser.parse_args()
    migrate(args.database, AIRCRAFT_DATA_REGISTRY, args.source_dir, args.replace)
    print(f"Database ready: {args.database.resolve()}")


if __name__ == "__main__":
    main()
