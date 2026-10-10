"""Serve the flight database from one process: python -m webapp.data.quack_server."""

from __future__ import annotations

import logging
import os
import signal
import threading

import duckdb

from .flight_db import database_path
from .quack import DEFAULT_URI, extension_config, token

logger = logging.getLogger(__name__)


def serve(stop: threading.Event) -> None:
    credential = token()
    path = database_path()
    if not path.is_file():
        raise FileNotFoundError(
            "Flight database is missing; run webapp.data.migrate_flights first."
        )
    uri = os.environ.get("QUACK_LISTEN_URI", DEFAULT_URI)
    with duckdb.connect(str(path), config=extension_config()) as db:
        db.execute("LOAD quack")
        # Fail early on an incomplete/wrong database, before opening the listener.
        for table in ("reports", "onwing", "report_parameters", "import_sources"):
            db.execute(f"SELECT * FROM {table} LIMIT 0")
        # Quack 1.5.6 cannot ATTACH a catalog containing a function-valued
        # column default (e.g. current_timestamp). Existing timestamps survive;
        # the migration now supplies imported_at explicitly instead.
        db.execute("ALTER TABLE import_sources ALTER COLUMN imported_at DROP DEFAULT")
        # Quack catalogs do not expose the implicit rowid. Keep its ordering for
        # duplicate report timestamps without adding columns to the report table.
        db.execute("""
            CREATE OR REPLACE VIEW constructor_reports AS
            SELECT rowid AS _report_rowid, * FROM reports
        """)
        # Keep localhost-only defaults; external clients use an SSH tunnel or
        # a TLS reverse proxy. Do not log the returned row (it contains the token).
        db.execute("CALL quack_serve(?, token := ?)", [uri, credential]).fetchall()
        logger.info("Flight database ready at %s", uri)
        try:
            stop.wait()
        finally:
            db.execute("CALL quack_stop(?)", [uri])
            db.execute("CHECKPOINT")
            logger.info("Flight database stopped cleanly")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        serve(stop)
    except Exception as exc:
        # SQL exceptions can contain credentials. Report the class, not SQL text.
        logger.error(
            "Quack service failed (%s). Check database path, token and extension installation.",
            type(exc).__name__,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
