"""Quack connection setup shared by the dashboard and trusted ingestion clients."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import duckdb

DEFAULT_URI = "quack:127.0.0.1:9494"


def extension_config() -> dict[str, str]:
    directory = os.environ.get("DUCKDB_EXTENSION_DIRECTORY")
    return (
        {"extension_directory": str(Path(directory).expanduser())} if directory else {}
    )


def token() -> str:
    """Read server-side credentials; never include them in logs or Reflex state."""
    filename = os.environ.get("QUACK_TOKEN_FILE")
    value = (
        Path(filename).expanduser().read_text().strip()
        if filename
        else os.environ.get("QUACK_TOKEN", "").strip()
    )
    if len(value) < 32:
        raise ValueError(
            "Set QUACK_TOKEN_FILE or QUACK_TOKEN to a random token of at least 32 characters."
        )
    return value


def sql_literal(value: str) -> str:
    # ATTACH does not support bound parameters. Escape its string literals.
    return "'" + value.replace("'", "''") + "'"


def connect_remote(*, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Connect to the service; never fall back to the local database on failure.

    READ_ONLY prevents accidental client writes. The token still grants trusted
    SQL access to the server; it is not a separate read-only security role.
    """
    uri = os.environ.get("FLIGHT_QUACK_URL", DEFAULT_URI)
    if not uri.startswith("quack:"):
        raise ValueError("FLIGHT_QUACK_URL must be a quack: URI.")
    credential = token()
    db = duckdb.connect(config=extension_config())
    try:
        # Extensions are installed during deployment, not on every connection.
        db.execute("LOAD quack")
        options = f"TYPE quack, TOKEN {sql_literal(credential)}"
        if read_only:
            options += ", READ_ONLY"
        db.execute(f"ATTACH {sql_literal(uri)} AS flights ({options})")
        db.execute("USE flights")
        return db
    except Exception:
        db.close()
        # DuckDB parser/transport errors may echo the ATTACH SQL and its token.
        raise RuntimeError(
            "Could not connect to the flight Quack service. Check the service, "
            "FLIGHT_QUACK_URL, credentials and the installed Quack extension."
        ) from None


@contextmanager
def transaction(db: duckdb.DuckDBPyConnection):
    """Start the transaction on the server, not on the client's memory database.

    In Quack 1.5.6 a plain client BEGIN does not isolate remote INSERTs. Sending
    transaction commands through the attached catalog keeps batches atomic.
    Use for DML batches; execute schema changes separately before the batch.
    """
    db.execute("FROM flights.query('BEGIN')")
    try:
        yield db
        db.execute("FROM flights.query('COMMIT')")
    except BaseException:
        try:
            db.execute("FROM flights.query('ROLLBACK')")
        except duckdb.Error:
            pass  # Preserve the original failure, including a lost connection.
        raise


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check"))
    args = parser.parse_args()
    if args.action == "install":
        with duckdb.connect(config=extension_config()) as db:
            db.execute("INSTALL quack")
            db.execute("LOAD quack")
        print(f"Quack extension installed for DuckDB {duckdb.__version__}")
    else:
        with connect_remote() as db:
            count = db.execute("SELECT count(*) FROM reports").fetchone()[0]
        print(f"Quack connection OK: {count:,} reports")


if __name__ == "__main__":
    main()
