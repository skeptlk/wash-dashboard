"""Incremental PostgreSQL → Quack ingestion; one pass per scheduler invocation."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
import json
import logging
import math
import os
from pathlib import Path
import re

from .quack import QuackConnectionError, connect_remote, sql_literal, transaction
from .postgres_diagnostics import (
    PasswordFileError,
    configured_password,
    connection_error_detail,
    password_file,
)

LOG = logging.getLogger(__name__)
PARAMETERS = json.loads(Path(__file__).with_name("sync_parameters.json").read_text())
KEY = (
    "aircraft_type",
    "aircraft_id",
    "engine_position",
    "flight_phase",
    "flight_datetime",
)
HISTORY_COLUMNS = (
    "aircraft_id",
    "engine_position",
    "install_datetime",
    "engine_id",
    "aircraft_family",
    "engine_family",
    "thrust_rating",
    "removal_datetime",
    "hrs_at_install",
    "cyc_at_install",
    "hrs_at_removal",
    "cyc_at_removal",
    "number_removals",
    "number_shop_visits",
    "deletion_flag",
    "reason_for_removal",
)


class SourceDataError(ValueError):
    """An actionable validation message containing no credentials or SQL."""


def aircraft_family(source_family, source_type):
    """Resolve the parameter catalog from the aircraft registry, family first."""
    for value in (source_family, source_type):
        value = (value or "").strip().upper()
        for prefixes, family in (
            (("B737",), "B737"),
            (("A319", "A320", "A321"), "A320"),
            (("E170", "ERJ"), "E170"),
        ):
            if value.startswith(prefixes):
                return family
    return None


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    """Typed SQL literals for server-side Quack queries (no credentials here)."""
    if value is None:
        return "NULL"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError("Expected UTC wall-clock timestamp without tzinfo")
        return "TIMESTAMP " + sql_literal(value.isoformat())
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite measurement in source")
        return str(value)
    return sql_literal(str(value))


def values_sql(rows):
    return ",".join("(" + ",".join(map(literal, row)) + ")" for row in rows)


def report_query(family, phase):
    """Same numeric MAX/COALESCE pivot and engine-key union as legacy exports.

    Identifiers and parameter names come only from the checked-in catalog.
    Runtime aircraft IDs, phases and time bounds are PostgreSQL bind parameters.
    """
    ctes, selections = [], []
    for table, parameters in PARAMETERS[family][phase].items():
        keys = "aircraft_id, flight_datetime"
        if table != "aircraft_input":
            keys += ", engine_position"
        expressions = [
            "MAX(COALESCE(float_value, integer_value::double precision)) "
            f"FILTER (WHERE parameter_name = {sql_literal(p)}) AS {identifier(p.lower())}"
            for p in parameters
        ]
        ctes.append(f"""{table} AS (
            SELECT {keys}, {", ".join(expressions)} FROM s7_mdb.{table}
            WHERE aircraft_id = %(aircraft)s AND flight_phase = %(phase)s
              AND flight_datetime >= %(start)s AND flight_datetime <= %(end)s
            GROUP BY {keys})""")
        selections.extend(f"{table}.{identifier(p.lower())}" for p in parameters)
    ctes.append("""spine AS (
        SELECT aircraft_id, engine_position, flight_datetime FROM engine_input
        UNION
        SELECT aircraft_id, engine_position, flight_datetime FROM engine_raw_output
    )""")
    return f"""WITH {", ".join(ctes)}
        SELECT s.aircraft_id, s.engine_position, s.flight_datetime,
            %(phase)s::text AS flight_phase, {", ".join(selections)},
            h.engine_id, h.engine_matches AS _engine_matches,
            h.engine_candidates AS _engine_candidates, h.install_datetime AS _install_datetime
        FROM spine s
        LEFT JOIN engine_input USING (aircraft_id, engine_position, flight_datetime)
        LEFT JOIN engine_raw_output USING (aircraft_id, engine_position, flight_datetime)
        LEFT JOIN aircraft_input USING (aircraft_id, flight_datetime)
        LEFT JOIN LATERAL (
            SELECT min(engine_id) AS engine_id, count(DISTINCT engine_id) AS engine_matches,
                string_agg(DISTINCT engine_id, ', ' ORDER BY engine_id) AS engine_candidates,
                max(install_datetime) AS install_datetime
            FROM (
                SELECT o.engine_id, o.install_datetime,
                    dense_rank() OVER (ORDER BY o.install_datetime DESC) AS installation_rank
                FROM s7_mdb.onwing_engine o
                WHERE o.aircraft_id = s.aircraft_id AND o.engine_position = s.engine_position
                  AND o.install_datetime <= s.flight_datetime
                  AND (o.removal_datetime IS NULL OR s.flight_datetime < o.removal_datetime)
            ) candidates WHERE installation_rank = 1
        ) h ON TRUE
        ORDER BY s.flight_datetime, s.engine_position"""


@contextmanager
def postgres_read_cursor(db):
    """Keep settings inside each transaction, including with transaction pooling.

    Poolers may reject startup options or assign a different backend to the next
    transaction. SET LOCAL neither relies on nor leaks session-wide settings.
    """
    with db.transaction(), db.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5min'")
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        yield cur


class PostgresSource:
    def __init__(self, db, max_rows=20000):
        self.db, self.max_rows = db, max_rows

    def watermarks(self):
        # Explicit UTC conversion: source reports are timestamp WITHOUT time zone.
        with postgres_read_cursor(self.db) as cur:
            cur.execute("""
                SELECT n.aircraft_id, a.aircraft_id, a.aircraft_family,
                    a.aircraft_type, n.flight_phase,
                    max(n.last_seen_flight_datetime) AT TIME ZONE 'UTC'
                FROM ecmapp.no_data_report n
                LEFT JOIN s7_mdb.aircraft a ON a.aircraft_id = n.aircraft_id
                WHERE n.last_seen_flight_datetime IS NOT NULL
                  AND n.flight_phase IN ('TAKEOFF', 'CRUISE')
                GROUP BY n.aircraft_id, a.aircraft_id, a.aircraft_family,
                    a.aircraft_type, n.flight_phase
                ORDER BY n.aircraft_id, n.flight_phase
            """)
            streams = []
            seen, stream_keys, skipped = {}, set(), set()
            for (
                aircraft,
                registry_id,
                source_family,
                source_type,
                phase,
                target,
            ) in cur.fetchall():
                family = aircraft_family(source_family, source_type)
                if aircraft in seen and seen[aircraft] != family:
                    raise SourceDataError(
                        f"Ambiguous aircraft family in s7_mdb.aircraft for {aircraft}: "
                        f"{seen[aircraft]} vs {family} "
                        f"(aircraft_family={source_family!r}, aircraft_type={source_type!r})"
                    )
                seen[aircraft] = family
                if family is None:
                    if aircraft not in skipped:
                        if registry_id is None:
                            LOG.warning(
                                "Skipping aircraft %r: no matching aircraft_id in "
                                "s7_mdb.aircraft; checkpoint unchanged",
                                aircraft,
                            )
                        else:
                            LOG.warning(
                                "Skipping aircraft %r: unsupported or empty "
                                "aircraft_family=%r, aircraft_type=%r in "
                                "s7_mdb.aircraft; checkpoint unchanged",
                                aircraft,
                                source_family,
                                source_type,
                            )
                        skipped.add(aircraft)
                    continue
                if (aircraft, phase) in stream_keys:
                    continue
                stream_keys.add((aircraft, phase))
                streams.append((family, aircraft, phase, target))
            LOG.info(
                "Aircraft registry: %d aircraft, %d streams selected; %d aircraft skipped",
                len(seen) - len(skipped),
                len(streams),
                len(skipped),
            )
            return streams

    def earliest(self, aircraft, phase):
        with postgres_read_cursor(self.db) as cur:
            cur.execute(
                """
                SELECT min(dt) FROM (
                    SELECT min(flight_datetime) AS dt FROM s7_mdb.engine_input
                    WHERE aircraft_id = %s AND flight_phase = %s
                    UNION ALL
                    SELECT min(flight_datetime) AS dt FROM s7_mdb.engine_raw_output
                    WHERE aircraft_id = %s AND flight_phase = %s
                ) t
            """,
                (aircraft, phase, aircraft, phase),
            )
            return cur.fetchone()[0]

    def window(self, family, aircraft, phase, start, end):
        # Bound each snapshot to one aircraft/time window, not the whole backlog.
        with postgres_read_cursor(self.db) as cur:
            cur.execute(
                report_query(family, phase) + " LIMIT %(row_limit)s",
                {
                    "aircraft": aircraft,
                    "phase": phase,
                    "start": start,
                    "end": end,
                    "row_limit": self.max_rows + 1,
                },
            )
            columns = [c.name for c in cur.description]
            rows = cur.fetchmany(self.max_rows + 1)
            if len(rows) > self.max_rows:
                raise SourceDataError("Window exceeds max rows; reduce --window-days")
            # One source snapshot for engine mapping and the exported history.
            cur.execute(
                f"SELECT {', '.join(HISTORY_COLUMNS)} FROM s7_mdb.onwing_engine "
                "WHERE aircraft_id = %s",
                (aircraft,),
            )
            history = cur.fetchall()
        return prepare_rows(family, columns, rows), history


def prepare_rows(family, columns, rows):
    records = []
    for row in rows:
        record = dict(zip(columns, row, strict=True))
        candidates = record.pop("_engine_candidates", None)
        installed = record.pop("_install_datetime", None)
        if record.pop("_engine_matches") > 1:
            raise SourceDataError(
                "Ambiguous latest onwing installation: "
                f"aircraft={record['aircraft_id']}, position={record['engine_position']}, "
                f"flight={record['flight_datetime']}, install={installed}, engines={candidates}"
            )
        record["aircraft_type"] = family
        record["aircraft_id"] = str(record["aircraft_id"]).zfill(5)
        records.append(record)
    return records


class QuackSink:
    def __init__(self, db):
        self.db = db
        self.prepared = set()

    def execute(self, sql):
        # Execute filters, joins and writes on the server, including remote views.
        return self.db.execute("FROM flights.query(?)", [sql])

    def atomic(self):
        return transaction(self.db)

    def setup(self, *, dry_run=False):
        if not dry_run:
            self.execute("""CREATE TABLE IF NOT EXISTS postgres_sync_state (
            aircraft_type VARCHAR, aircraft_id VARCHAR, flight_phase VARCHAR,
            cursor_datetime TIMESTAMP, target_datetime TIMESTAMP, complete BOOLEAN,
            updated_at TIMESTAMP,
                PRIMARY KEY (aircraft_type, aircraft_id, flight_phase))""")
        self.has_state = bool(
            self.execute("""SELECT count(*) FROM information_schema.tables
            WHERE table_schema='main' AND table_name='postgres_sync_state'""").fetchone()[
                0
            ]
        )
        for table in ("reports", "report_parameters", "onwing"):
            self.execute(f"SELECT * FROM {table} LIMIT 0")

    def checkpoint(self, family, aircraft, phase):
        if not self.has_state:
            return None
        return self.execute(f"""SELECT cursor_datetime, target_datetime, complete
            FROM postgres_sync_state WHERE {self.scope(family, aircraft, phase)}""").fetchone()

    @staticmethod
    def scope(family, aircraft, phase):
        return (
            f"aircraft_type = {literal(family)} AND aircraft_id = {literal(aircraft.zfill(5))} "
            f"AND flight_phase = {literal(phase)}"
        )

    def bootstrap(self, family, aircraft, phase):
        # Never use a fleet-wide maximum. Also respect a lagging second engine.
        rows = self.execute(f"""SELECT engine_position, max(flight_datetime)
            FROM reports WHERE {self.scope(family, aircraft, phase)}
            GROUP BY engine_position""").fetchall()
        ends = {position: dt for position, dt in rows}
        if not ends.get(1) or not ends.get(2):
            return None
        return min(ends[1], ends[2])

    def ensure_parameters(self, family, phase):
        if (family, phase) in self.prepared:
            return
        parameters = [
            p.lower() for ps in PARAMETERS[family][phase].values() for p in ps
        ]
        if len(parameters) != len(set(parameters)):
            raise ValueError("Parameter catalog contains conflicting names")
        existing = {
            r[0].lower(): r[1] for r in self.execute("DESCRIBE reports").fetchall()
        }
        changed = False
        for name in parameters:
            if name not in existing:
                self.execute(
                    f"ALTER TABLE reports ADD COLUMN {identifier(name)} DOUBLE"
                )
                changed = True
            elif existing[name] != "DOUBLE":
                raise SourceDataError(f"Expected DOUBLE measurement column: {name}")
        # Refresh even after an interrupted DDL run. Server-side view binds rowid.
        self.execute("""CREATE OR REPLACE VIEW constructor_reports AS
            SELECT rowid AS _report_rowid, * FROM reports""")
        if changed:
            LOG.info("Added measurement columns for %s %s", family, phase)
        self.prepared.add((family, phase))

    def write_window(self, family, aircraft, phase, end, target, records, history):
        with self.atomic():
            # MERGE only source-owned columns. Keep n1_modifier and other extras.
            for offset in range(0, len(records), 250):
                batch = records[offset : offset + 250]
                columns = list(batch[0])
                names = ",".join(map(identifier, columns))
                rows = [[r[c] for c in columns] for r in batch]
                match = " AND ".join(
                    f"t.{identifier(k)} = s.{identifier(k)}" for k in KEY
                )
                # Constant bounds allow the server to prune the historical table
                # before matching a small incoming batch during initial catch-up.
                dates = [r["flight_datetime"] for r in batch]
                match += (
                    f" AND t.aircraft_type = {literal(family)}"
                    f" AND t.aircraft_id = {literal(aircraft.zfill(5))}"
                    f" AND t.flight_phase = {literal(phase)}"
                    f" AND t.flight_datetime >= {literal(min(dates))}"
                    f" AND t.flight_datetime <= {literal(max(dates))}"
                )
                updates = ",".join(
                    f"{identifier(c)} = s.{identifier(c)}"
                    for c in columns
                    if c not in KEY
                )
                self.execute(f"""MERGE INTO reports t
                    USING (VALUES {values_sql(rows)}) AS s({names}) ON {match}
                    WHEN MATCHED THEN UPDATE SET {updates}
                    WHEN NOT MATCHED THEN INSERT ({names}) VALUES
                    ({",".join("s." + identifier(c) for c in columns)})""")
            self.execute(
                f"DELETE FROM onwing WHERE aircraft_id = {literal(aircraft.zfill(5))}"
            )
            for offset in range(0, len(history), 250):
                rows = [
                    (str(r[0]).zfill(5), *r[1:]) for r in history[offset : offset + 250]
                ]
                self.execute(
                    f"INSERT INTO onwing ({','.join(HISTORY_COLUMNS)}) VALUES {values_sql(rows)}"
                )
            parameters = [
                p.lower() for ps in PARAMETERS[family][phase].values() for p in ps
            ]
            self.execute(f"""INSERT INTO report_parameters
                SELECT v.* FROM (VALUES {values_sql([(family, phase, p) for p in parameters])})
                    v(aircraft_type, flight_phase, column_name)
                WHERE NOT EXISTS (SELECT 1 FROM report_parameters p
                    WHERE p.aircraft_type=v.aircraft_type AND p.flight_phase=v.flight_phase
                      AND p.column_name=v.column_name)""")
            self.execute(
                f"DELETE FROM postgres_sync_state WHERE {self.scope(family, aircraft, phase)}"
            )
            self.execute(
                "INSERT INTO postgres_sync_state VALUES ("
                + ",".join(
                    map(
                        literal,
                        (
                            family,
                            aircraft.zfill(5),
                            phase,
                            end,
                            target,
                            end == target,
                        ),
                    )
                )
                + ", current_timestamp)"
            )


def sync(
    source,
    sink,
    *,
    window_days=7,
    overlap_hours=24,
    since=None,
    aircraft_ids=(),
    max_windows=None,
    dry_run=False,
):
    sink.setup(dry_run=dry_run)
    windows, total = 0, 0
    for family, aircraft, phase, watermark in source.watermarks():
        if aircraft_ids and aircraft not in aircraft_ids:
            continue
        state = sink.checkpoint(family, aircraft, phase)
        if state and watermark < state[1]:
            raise SourceDataError(
                f"Source watermark moved backwards for {aircraft} {phase}"
            )
        if since is not None:
            start, target = since, watermark
        elif state and not state[2]:
            start, target = state[:2]  # Resume the captured target, including boundary.
        elif state and state[1] == watermark:
            continue
        else:
            initial = state[0] if state else sink.bootstrap(family, aircraft, phase)
            start = (
                initial - timedelta(hours=overlap_hours)
                if initial
                else source.earliest(aircraft, phase)
            )
            target = watermark
        if start is None:
            # Do not acknowledge a watermark without any source engine reports.
            raise SourceDataError(
                f"No engine reports for advertised stream {aircraft} {phase}"
            )
        if start > target:
            if since is not None:
                continue
            raise SourceDataError(
                f"Destination is ahead of source for {aircraft} {phase}"
            )
        if not dry_run:
            sink.ensure_parameters(family, phase)
        while True:
            end = min(start + timedelta(days=window_days), target)
            LOG.info("Reading %s %s %s [%s, %s]", family, aircraft, phase, start, end)
            records, history = source.window(family, aircraft, phase, start, end)
            if not dry_run:
                sink.write_window(
                    family, aircraft, phase, end, target, records, history
                )
            total += len(records)
            windows += 1
            LOG.info(
                "%s %s %s [%s, %s]: %s reports; target=%s%s",
                family,
                aircraft,
                phase,
                start,
                end,
                len(records),
                target,
                " (dry run)" if dry_run else "",
            )
            if max_windows and windows >= max_windows:
                LOG.info(
                    "Window budget reached%s",
                    " (dry run; nothing saved)"
                    if dry_run
                    else "; next invocation resumes from checkpoint",
                )
                return total
            if end == target:
                break
            start = end
    return total


@contextmanager
def single_instance(path):
    """OS lock releases on process exit/crash, including on Windows 10."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def postgres_error_hint(exc):
    """Classify driver details without echoing DSNs, SQL or credential values."""
    message = str(exc).lower()
    reasons = (
        (
            ("no password supplied", "password is required"),
            "No password supplied. Check PGPASSFILE exists and its host:port:database:user fields match the connection.",
        ),
        (
            ("password authentication failed",),
            "Password authentication failed. Check PGUSER and the matching password in PGPASSFILE.",
        ),
        (
            ("no pg_hba.conf entry",),
            "Server access rules rejected this connection. Ask the PostgreSQL administrator to check client address, user, database and SSL policy.",
        ),
        (
            ("does not support ssl",),
            "The endpoint does not support SSL, but PGSSLMODE requires it. Confirm the correct endpoint and SSL policy with the administrator.",
        ),
        (
            (
                "certificate verify failed",
                "root certificate file",
                "server certificate",
            ),
            "TLS certificate validation failed. Check PGSSLROOTCERT, PGHOST and the server certificate.",
        ),
        (
            (
                "could not translate host name",
                "could not resolve",
                "getaddrinfo",
                "name or service not known",
            ),
            "Host name resolution failed. Check PGHOST and access to corporate DNS/VPN.",
        ),
        (
            ("connection refused", "actively refused"),
            "TCP connection refused. Check PGHOST/PGPORT and whether PostgreSQL listens on that endpoint.",
        ),
        (
            (
                "timeout expired",
                "timed out",
                "network is unreachable",
                "no route to host",
            ),
            "PostgreSQL is unreachable or timed out. Check network/VPN, firewall and PGHOST/PGPORT.",
        ),
        (
            ("server closed the connection", "connection reset", "ssl syscall error"),
            "Connection was interrupted. Check the network and PostgreSQL server logs.",
        ),
    )
    hints = [hint for patterns, hint in reasons if any(p in message for p in patterns)]
    if "database" in message and "does not exist" in message:
        hints.append("Database does not exist. Check PGDATABASE.")
    if "role" in message and "does not exist" in message:
        hints.append("Role does not exist. Check PGUSER.")
    code = getattr(exc, "sqlstate", None)
    suffix = (
        f" SQLSTATE={code}."
        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code)
        else ""
    )
    return (
        " ".join(hints)
        if hints
        else "Unclassified PostgreSQL error; check server logs for application engine-wash-sync at this time."
    ) + suffix


def main(argv=None, *, connection_context=nullcontext):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--overlap-hours", type=int, default=24)
    parser.add_argument("--max-window-rows", type=int, default=20000)
    parser.add_argument(
        "--max-windows", type=int, help="Stop cleanly after this many committed windows"
    )
    parser.add_argument(
        "--aircraft",
        action="append",
        default=[],
        help="Exact PostgreSQL aircraft_id; repeatable",
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="Explicit UTC wall-clock replay start (no offset)",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "postgres-sync.lock",
    )
    parser.add_argument("--log-file", type=Path)
    parser.add_argument(
        "--check-postgres",
        action="store_true",
        help="Test only PostgreSQL with SELECT 1; do not connect to Quack or import data",
    )
    parser.add_argument(
        "--ask-password",
        action="store_true",
        help="With --check-postgres, prompt for a password instead of using the password file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and validate source windows without changing DuckDB",
    )
    args = parser.parse_args(argv)
    if args.ask_password and not args.check_postgres:
        parser.error("--ask-password requires --check-postgres")
    if (
        args.window_days < 1
        or args.overlap_hours < 0
        or args.max_window_rows < 1
        or (args.max_windows is not None and args.max_windows < 1)
    ):
        parser.error(
            "Window and row limits must be positive; overlap must be nonnegative"
        )
    if args.since and args.since.tzinfo:
        parser.error("--since must be a UTC wall-clock timestamp without an offset")
    handlers = [logging.StreamHandler()]
    if args.log_file:
        from logging.handlers import RotatingFileHandler

        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                args.log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    stage = "startup / SSH tunnel"
    psycopg = None
    supplied_password = None
    try:
        import psycopg

        with (
            single_instance(args.lock_file),
            nullcontext() if args.check_postgres else connection_context(),
        ):
            stage = "PostgreSQL connection"
            if args.check_postgres:
                for note in password_file()[0]:
                    LOG.info("%s", note)
            options = {}
            if args.ask_password:
                from getpass import getpass

                supplied_password = getpass("PostgreSQL password (not saved): ")
                if not supplied_password:
                    raise SourceDataError(
                        "Empty interactive password; connection test cancelled"
                    )
            else:
                supplied_password = configured_password()
                if supplied_password is not None:
                    LOG.info(
                        "PostgreSQL password loaded from the matching PGPASSFILE entry"
                    )
            if supplied_password is not None:
                options["password"] = supplied_password
            LOG.info("Connecting to PostgreSQL")
            with psycopg.connect(
                os.environ.get("SYNC_POSTGRES_DSN", ""),
                autocommit=True,
                prepare_threshold=None,
                connect_timeout=30,
                application_name="engine-wash-sync",
                **options,
            ) as source_db:
                LOG.info("PostgreSQL connected")
                if args.check_postgres:
                    stage = "PostgreSQL SELECT 1"
                    with postgres_read_cursor(source_db) as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                    LOG.info("PostgreSQL check OK; no data imported")
                    return
                stage = "Quack connection"
                LOG.info("Connecting to Quack")
                with connect_remote(read_only=args.dry_run) as target_db:
                    LOG.info("Quack connected")
                    stage = "data synchronization"
                    count = sync(
                        PostgresSource(source_db, args.max_window_rows),
                        QuackSink(target_db),
                        window_days=args.window_days,
                        overlap_hours=args.overlap_hours,
                        since=args.since,
                        aircraft_ids=args.aircraft,
                        max_windows=args.max_windows,
                        dry_run=args.dry_run,
                    )
                    LOG.info(
                        "Sync complete: %s reports processed (including overlaps)",
                        count,
                    )
    except (SourceDataError, PasswordFileError) as exc:
        LOG.error("Sync stopped: %s; checkpoint retained", exc)
        raise SystemExit(1) from None
    except QuackConnectionError as exc:
        LOG.error("%s; checkpoint retained", exc)
        raise SystemExit(1) from None
    except Exception as exc:
        # Driver exceptions may contain connection strings/passwords or SQL data.
        if isinstance(exc, getattr(psycopg, "Error", ())):
            LOG.error(
                "PostgreSQL failed during %s (%s): %s Checkpoint retained.",
                stage,
                type(exc).__name__,
                postgres_error_hint(exc),
            )
            if stage == "PostgreSQL connection":
                LOG.error(
                    "PostgreSQL detail: %s",
                    connection_error_detail(exc, supplied_password),
                )
        else:
            LOG.error(
                "Sync failed during %s (%s); checkpoint retained. Check connections, source schema, onwing overlaps and window size.",
                stage,
                type(exc).__name__,
            )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
