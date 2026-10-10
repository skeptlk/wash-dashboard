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
