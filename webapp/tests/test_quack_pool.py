"""Exclusive reader leases, configuration changes and failure recovery."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from webapp.data import quack


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.delenv("QUACK_TOKEN_FILE", raising=False)
    monkeypatch.setenv("QUACK_TOKEN", "a" * 32)
    created = []

    class Connection:
        closed = False

        def close(self):
            self.closed = True

    def connect():
        db = Connection()
        created.append(db)
        return db

    monkeypatch.setattr(quack, "connect_remote", connect)
    pool = quack.ReadConnectionPool(size=2)
    yield pool, created
    pool.close()


def test_readers_are_exclusive_and_reused(pool):
    pool, created = pool
    barrier = Barrier(2)

    def read(_):
        with pool.connection() as db:
            barrier.wait(timeout=5)
            return db

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(read, range(2))
    assert first is not second
    assert len(created) == 2
    with pool.connection() as db:
        assert db in (first, second)
    assert len(created) == 2


def test_failed_connection_is_discarded_and_next_request_recovers(pool):
    pool, created = pool
    with pytest.raises(RuntimeError):
        with pool.connection() as failed:
            raise RuntimeError("disconnected")
    assert failed.closed
    with pool.connection() as healthy:
        assert healthy is not failed and not healthy.closed
    assert len(created) == 2


def test_configuration_changes_do_not_reuse_old_connections(pool, monkeypatch):
    pool, _ = pool
    with pool.connection() as previous:
        pass
    monkeypatch.setenv("QUACK_TOKEN", "b" * 32)
    with pool.connection() as current:
        assert previous.closed and previous is not current
    with pool.connection() as active:
        pool.close()
    assert active.closed


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_windows_token_file_encoding(tmp_path, monkeypatch, encoding):
    path = tmp_path / "quack.token"
    path.write_text("a" * 64 + "\n", encoding=encoding)
    monkeypatch.setenv("QUACK_TOKEN_FILE", str(path))
    assert quack.token() == "a" * 64


@pytest.mark.parametrize(
    ("failing_sql", "stage"),
    [
        ("LOAD", "loading Quack extension"),
        ("ATTACH", "attaching remote Quack catalog"),
        ("USE", "selecting remote Quack catalog"),
    ],
)
def test_connection_error_identifies_stage_and_redacts_token(
    monkeypatch, failing_sql, stage
):
    from unittest.mock import Mock
    from urllib.parse import quote

    secret = "secret'token/" * 4
    monkeypatch.delenv("QUACK_TOKEN_FILE", raising=False)
    monkeypatch.setenv("QUACK_TOKEN", secret)
    db = Mock()

    def execute(sql):
        if sql.startswith(failing_sql):
            raise RuntimeError(
                "original driver error "
                + sql
                + " "
                + secret
                + " "
                + quote(secret, safe="")
            )

    db.execute.side_effect = execute
    monkeypatch.setattr(quack.duckdb, "connect", lambda **kw: db)
    with pytest.raises(quack.QuackConnectionError) as caught:
        quack.connect_remote()
    message = str(caught.value)
    assert stage in message and "original driver error" in message
    assert secret not in message
    assert secret.replace("'", "''") not in message
    assert quote(secret, safe="") not in message
    assert "DuckDB" in message
    db.close.assert_called_once()


def test_missing_token_file_has_actionable_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("QUACK_TOKEN_FILE", str(tmp_path / "missing.token"))
    with pytest.raises(
        quack.QuackConnectionError, match="reading Quack credentials"
    ) as caught:
        quack.connect_remote()
    assert "FileNotFoundError" in str(caught.value)


def test_sync_prints_safe_quack_error(tmp_path, monkeypatch, caplog):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    from webapp.data import sync_flights

    monkeypatch.delenv("PGPASSFILE", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *a, **kw: nullcontext(object())),
    )

    def fail(**kwargs):
        raise quack.QuackConnectionError(
            "Could not connect during loading Quack extension. Detail: missing extension"
        )

    monkeypatch.setattr(sync_flights, "connect_remote", fail)
    with pytest.raises(SystemExit):
        sync_flights.main(["--dry-run", "--lock-file", str(tmp_path / "lock")])
    assert (
        "loading Quack extension" in caplog.text and "missing extension" in caplog.text
    )
