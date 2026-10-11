"""Import an aircraft CSV into the running Quack database.

PYTHONPATH=webapp python -m webapp.data.import_aircraft /path/to/aircraft.csv
"""

import argparse
import csv
from pathlib import Path

from .quack import connect_remote, sql_literal, transaction

AIRCRAFT_COLUMNS = ("aircraft_id", "aircraft_family", "aircraft_type")
CREATE_AIRCRAFT_SQL = """CREATE TABLE IF NOT EXISTS aircraft (
    aircraft_id VARCHAR PRIMARY KEY,
    aircraft_family VARCHAR NOT NULL,
    aircraft_type VARCHAR NOT NULL
)"""


def read_aircraft_csv(path: Path) -> list[tuple[str, str, str]]:
    """Keep one model per normalized ID; reject conflicting source records."""
    aircraft = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if missing := set(AIRCRAFT_COLUMNS) - set(reader.fieldnames or []):
            raise ValueError(f"Missing aircraft columns: {sorted(missing)}")
        for row in reader:
            values = tuple((row.get(col) or "").strip() for col in AIRCRAFT_COLUMNS)
            if not all(values):
                raise ValueError(
                    f"Empty aircraft ID/family/model at CSV line {reader.line_num}"
                )
            aid, family, model = values
            aid = aid.zfill(5)
            if aid in aircraft and aircraft[aid] != (aid, family, model):
                raise ValueError(f"Conflicting aircraft models for {aid}")
            aircraft[aid] = (aid, family, model)
    if not aircraft:
        raise ValueError("Aircraft CSV is empty")
    return sorted(aircraft.values())


def aircraft_upsert_sql(rows: list[tuple[str, str, str]]) -> str:
    values = ",".join("(" + ",".join(map(sql_literal, row)) + ")" for row in rows)
    return f"""INSERT INTO aircraft ({",".join(AIRCRAFT_COLUMNS)}) VALUES {values}
        ON CONFLICT (aircraft_id) DO UPDATE SET
            aircraft_family = excluded.aircraft_family,
            aircraft_type = excluded.aircraft_type"""


def import_aircraft(path: Path) -> int:
    rows = read_aircraft_csv(path)
    with connect_remote(read_only=False) as db:
        # Quack schema changes must precede the server-side DML transaction.
        db.execute("FROM flights.query(?)", [CREATE_AIRCRAFT_SQL])
        with transaction(db):
            db.execute("FROM flights.query(?)", [aircraft_upsert_sql(rows)])
            stored = db.execute(
                "FROM flights.query('SELECT aircraft_id, aircraft_family, aircraft_type FROM aircraft')"
            ).fetchall()
            if not set(rows).issubset(set(stored)):
                raise ValueError("Aircraft import verification failed")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    print(f"Imported {import_aircraft(args.csv)} aircraft via Quack")


if __name__ == "__main__":
    main()
