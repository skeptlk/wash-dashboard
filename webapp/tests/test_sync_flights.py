"""Ingestion regressions: source pivot, replay, checkpoints and real Quack writes."""

from contextlib import contextmanager
from datetime import datetime as DT, timedelta
import os
from pathlib import Path
import re

import duckdb
import pytest

from webapp.data import sync_flights as syncer


class LocalSink(syncer.QuackSink):
    def execute(self, sql):
        return self.db.execute(sql)

    @contextmanager
    def atomic(self):
        self.db.execute("BEGIN")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise


def create_target(db):
    db.execute("""CREATE TABLE reports (
        aircraft_type VARCHAR, aircraft_id VARCHAR, engine_position BIGINT,
        flight_phase VARCHAR, flight_datetime TIMESTAMP_NS, engine_id VARCHAR,
        egthdm DOUBLE, n1_modifier DOUBLE)""")
    db.execute(
        "CREATE TABLE report_parameters (aircraft_type VARCHAR, flight_phase VARCHAR, column_name VARCHAR)"
    )
    schema = Path(__file__).resolve().parents[2] / "external_schema/schema.sql"
    history_sql = (
        schema.read_text().split("CREATE TABLE s7_mdb.onwing_engine")[1].split(";")[0]
    )
    db.execute("CREATE TABLE onwing" + history_sql)
    db.execute("CREATE TABLE import_sources (imported_at TIMESTAMP)")


@pytest.fixture
def sink():
    with duckdb.connect() as db:
        create_target(db)
        yield LocalSink(db)


def report(dt, pos=1, engine="new", value=10):
    return dict(
        aircraft_type="B737",
        aircraft_id="00123",
        engine_position=pos,
        flight_phase="TAKEOFF",
        flight_datetime=dt,
        engine_id=engine,
        egthdm=value,
    )


def history():
    return [
        (
            "00123",
            1,
            DT(2025, 1, 1),
            "new",
            "B737",
            "CFM",
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            None,
            None,
            "reason ' quoted",
        )
    ]


class Source:
    target = DT(2025, 1, 25)
    fail_at = None

    def __init__(self):
        self.calls = []

    def watermarks(self):
        return [("B737", "00123", "TAKEOFF", self.target)]

    def earliest(self, *args):
        return DT(2025, 1, 1)

    def window(self, family, aircraft, phase, start, end):
        self.calls.append((start, end))
        if self.fail_at == len(self.calls):
            raise RuntimeError("source unavailable")
        return [report(start), report(end)] if start < end else [report(end)], history()


def test_backlog_restart_and_unchanged_watermark(sink):
    source = Source()
    source.fail_at = 3
    with pytest.raises(RuntimeError):
        syncer.sync(source, sink)
    checkpoint = sink.checkpoint("B737", "00123", "TAKEOFF")
    assert checkpoint == (DT(2025, 1, 15), source.target, False)
    before = sink.execute("SELECT count(*) FROM reports").fetchone()[0]
    source.fail_at = None
    source.calls.clear()
    syncer.sync(source, sink)
    assert source.calls[0][0] == checkpoint[0]
    assert sink.checkpoint("B737", "00123", "TAKEOFF") == (
        source.target,
        source.target,
        True,
    )
    assert sink.execute("SELECT count(*) FROM reports").fetchone()[0] == before + 2
    source.calls.clear()
    assert syncer.sync(source, sink) == 0
    assert source.calls == []
    assert (
        sink.execute("SELECT count(*) FROM reports").fetchone()
        == sink.execute(
            "SELECT count(*) FROM (SELECT DISTINCT aircraft_type,aircraft_id,engine_position,flight_phase,flight_datetime FROM reports)"
        ).fetchone()
    )


def test_atomic_write_rollback_and_nullable_engine(sink):
    sink.setup()
    sink.ensure_parameters("B737", "TAKEOFF")
    target = DT(2025, 1, 1)
    sink.write_window(
        "B737",
        "00123",
        "TAKEOFF",
        target,
        target,
        [report(target, engine=None)],
        history(),
    )
    sink.execute("UPDATE reports SET n1_modifier=1.2")
    sink.write_window(
        "B737",
        "00123",
        "TAKEOFF",
        target,
        target,
        [report(target, engine="updated", value=30)],
        history(),
    )
    assert sink.execute(
        "SELECT engine_id, egthdm, n1_modifier FROM reports"
    ).fetchall() == [("updated", 30, 1.2)]
    original = sink.execute

    def fail(sql):
        if sql.startswith("INSERT INTO postgres_sync_state"):
            raise RuntimeError("disconnect before checkpoint")
        return original(sql)

    sink.execute = fail
    with pytest.raises(RuntimeError):
        sink.write_window(
            "B737",
            "00123",
            "TAKEOFF",
            target + timedelta(days=1),
            target,
            [report(target, value=999)],
            [],
        )
    sink.execute = original
    assert sink.execute("SELECT egthdm FROM reports").fetchall() == [(30,)]
    assert sink.execute("SELECT count(*) FROM onwing").fetchone()[0] == 1
    assert sink.checkpoint("B737", "00123", "TAKEOFF")[0] == target


def test_bootstrap_uses_slowest_engine_and_replay_preserves_extra_columns(sink):
    sink.setup()
    sink.ensure_parameters("B737", "TAKEOFF")
    dt = DT(2025, 1, 10)
    sink.write_window(
        "B737",
        "00123",
        "TAKEOFF",
        dt,
        dt,
        [report(dt), report(dt - timedelta(days=5), pos=2)],
        history(),
    )
    assert sink.bootstrap("B737", "00123", "TAKEOFF") == dt - timedelta(days=5)
    assert sink.bootstrap("B737", "00456", "TAKEOFF") is None
    source = Source()
    syncer.sync(source, sink, since=DT(2025, 1, 1), max_windows=1)
    assert source.calls == [(DT(2025, 1, 1), DT(2025, 1, 8))]
    assert sink.checkpoint("B737", "00123", "TAKEOFF")[2] is False


def test_regression_of_watermark_does_not_write(sink):
    source = Source()
    syncer.sync(source, sink)
    source.target -= timedelta(days=1)
    with pytest.raises(ValueError, match="backwards"):
        syncer.sync(source, sink)


def test_dry_run_does_not_create_tables_or_change_reports(sink):
    source = Source()
    tables = sink.execute("SHOW TABLES").fetchall()
    assert syncer.sync(source, sink, dry_run=True, max_windows=1) == 2
    assert sink.execute("SHOW TABLES").fetchall() == tables
    assert sink.execute("SELECT count(*) FROM reports").fetchone()[0] == 0


def test_new_watermark_overlap_and_same_time_engine_keys(sink):
    source = Source()
    syncer.sync(source, sink)
    old_target = source.target
    source.target += timedelta(days=3)
    source.calls.clear()
    syncer.sync(source, sink)
    assert source.calls == [(old_target - timedelta(days=1), source.target)]
    sink.write_window(
        "B737",
        "00123",
        "TAKEOFF",
        source.target,
        source.target,
        [report(source.target, 1), report(source.target, 2, engine=None)],
        history(),
    )
    assert (
        sink.execute(
            "SELECT count(*) FROM reports WHERE flight_datetime="
            + syncer.literal(source.target)
        ).fetchone()[0]
        == 2
    )
    assert sink.execute("SELECT count(*) FROM report_parameters").fetchone()[0] == 41


def test_source_sql_pivot_matches_exports_and_engine_boundaries():
    # The query uses shared PostgreSQL/DuckDB SQL. Execute against the supplied
    # source DDL locally; this does not replace a real PostgreSQL integration test.
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA s7_mdb; CREATE SCHEMA ecmapp")
        schema = Path(__file__).resolve().parents[2] / "external_schema/schema.sql"
        db.execute(schema.read_text().replace("USING btree", ""))
        db.execute("""INSERT INTO s7_mdb.engine_input VALUES
            ('00123',1,'TAKEOFF','2025-01-02','ZPCN12',42,NULL,NULL),
            ('00123',2,'TAKEOFF','2025-01-03','ZPCN12',NULL,55,NULL),
            ('00123',2,'TAKEOFF','2025-01-03','ZPCN12',NULL,54,NULL);
            INSERT INTO s7_mdb.engine_raw_output VALUES
            ('00123',1,'TAKEOFF','2025-01-02','EGTHDM',999,10,NULL),
            ('00123',1,'TAKEOFF','2025-01-04','EGTHDM',NULL,20,NULL),
            ('00123',1,'CRUISE','2025-01-02','EGTHDM',NULL,666,NULL),
            ('00456',1,'TAKEOFF','2025-01-02','EGTHDM',NULL,777,NULL);
            INSERT INTO s7_mdb.aircraft_input VALUES
            ('00123','TAKEOFF','2025-01-02','ZALT',100,NULL,NULL),
            ('00123','TAKEOFF','2025-01-05','ZALT',200,NULL,NULL);
            INSERT INTO s7_mdb.onwing_engine
            (aircraft_id,engine_position,install_datetime,engine_id,aircraft_family,engine_family,removal_datetime,number_removals)
            VALUES ('00123',1,'2024-01-01','old','B737','CFM','2025-01-02',0),
                   ('00123',1,'2025-01-02','new','B737','CFM',NULL,0)
        """)
        sql = re.sub(r"%\((\w+)\)s", r"$\1", syncer.report_query("B737", "TAKEOFF"))
        params = dict(
            aircraft="00123", phase="TAKEOFF", start=DT(2025, 1, 2), end=DT(2025, 1, 4)
        )
        result = db.execute(sql, params)
        cols = [r[0] for r in result.description]
        records = syncer.prepare_rows("B737", cols, result.fetchall())
        assert len(records) == 3  # includes input-only, output-only and null engine ID
        assert records[0]["engine_id"] == "new"
        assert records[0]["egthdm"] == 10  # float precedes integer
        assert records[0]["zalt"] == 100
        assert records[1]["engine_id"] is None and records[1]["zpcn12"] == 55
        assert records[2]["egthdm"] == 20
        db.execute("""INSERT INTO s7_mdb.onwing_engine
            (aircraft_id,engine_position,install_datetime,engine_id,aircraft_family,engine_family,number_removals)
            VALUES ('00123',1,'2025-01-01','overlap','B737','CFM',0)""")
        result = db.execute(sql, params)
        assert (
            syncer.prepare_rows("B737", cols, result.fetchall())[0]["engine_id"]
            == "new"
        )
        db.execute("""INSERT INTO s7_mdb.onwing_engine
            (aircraft_id,engine_position,install_datetime,engine_id,aircraft_family,engine_family,number_removals)
            VALUES ('00123',1,'2025-01-03','newest','B737','CFM',0),
                   ('00123',1,'2025-01-05','future','B737','CFM',0)""")
        result = db.execute(sql, params)
        records = syncer.prepare_rows("B737", cols, result.fetchall())
        assert records[0]["engine_id"] == "new"
        assert records[2]["engine_id"] == "newest"
        assert "_install_datetime" not in records[2]
        db.execute("""INSERT INTO s7_mdb.onwing_engine
            (aircraft_id,engine_position,install_datetime,engine_id,aircraft_family,engine_family,number_removals)
            VALUES ('00123',1,'2025-01-03','conflict','B737','CFM',0)""")
        result = db.execute(sql, params)
        with pytest.raises(
            ValueError, match="Ambiguous latest onwing installation"
        ) as caught:
            syncer.prepare_rows("B737", cols, result.fetchall())
        assert "aircraft=00123" in str(caught.value) and "position=1" in str(
            caught.value
        )
        assert "2025-01-03" in str(caught.value)
        assert "conflict" in str(caught.value) and "newest" in str(caught.value)
        for family, phases in syncer.PARAMETERS.items():
            for phase in phases:
                query = re.sub(
                    r"%\((\w+)\)s", r"$\1", syncer.report_query(family, phase)
                )
                db.execute(query, {**params, "phase": phase}).fetchall()


def test_local_lock_releases_after_failure(tmp_path):
    path = tmp_path / "sync.lock"
    with pytest.raises(RuntimeError):
        with syncer.single_instance(path):
            with pytest.raises(OSError):
                with syncer.single_instance(path):
                    pass
            raise RuntimeError("crash")
    with syncer.single_instance(path):
        pass


@pytest.fixture
def remote_sink(tmp_path, monkeypatch):
    import secrets
    import socket
    import subprocess
    import sys
    import time

    if os.environ.get("RUN_QUACK_TESTS") != "1":
        pytest.skip("Set RUN_QUACK_TESTS=1 for actual Quack transport")
    path = tmp_path / "sync.duckdb"
    with duckdb.connect(str(path)) as db:
        create_target(db)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    uri = f"quack:127.0.0.1:{port}"
    for key, val in dict(
        FLIGHT_DATABASE_PATH=str(path),
        FLIGHT_QUACK_URL=uri,
        QUACK_LISTEN_URI=uri,
        QUACK_TOKEN=secrets.token_hex(32),
    ).items():
        monkeypatch.setenv(key, val)
    monkeypatch.delenv("QUACK_TOKEN_FILE", raising=False)
    with (tmp_path / "quack.log").open("w+") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "webapp.data.quack_server"], stdout=log, stderr=log
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                log.seek(0)
                if "Flight database ready" in log.read():
                    break
                if proc.poll() is not None or time.monotonic() > deadline:
                    pytest.fail("Quack server failed to start")
                time.sleep(0.05)
            with syncer.connect_remote(read_only=False) as db:
                yield syncer.QuackSink(db)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def test_actual_quack_schema_merge_replay_and_transaction(remote_sink):
    from webapp.data.flight_db import read_trends

    sink = remote_sink
    source = Source()
    assert syncer.sync(source, sink, dry_run=True, max_windows=1) == 2
    assert sink.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    syncer.sync(source, sink, max_windows=1)
    first = sink.checkpoint("B737", "00123", "TAKEOFF")
    assert first == (DT(2025, 1, 8), source.target, False)
    syncer.sync(source, sink)
    assert sink.execute("SELECT count(*) FROM reports").fetchone()[0] == 5
    assert syncer.sync(source, sink) == 0
    syncer.sync(source, sink, since=DT(2025, 1, 1))
    assert sink.execute("SELECT count(*) FROM reports").fetchone()[0] == 5
    series, _ = read_trends("B737", "new", ["EGTHDM@TAKEOFF"], "", "")
    assert len(series[0][1]) == 5
    original = sink.execute

    def fail(sql):
        if sql.startswith("INSERT INTO postgres_sync_state"):
            raise RuntimeError("injected failure")
        return original(sql)

    sink.execute = fail
    with pytest.raises(RuntimeError):
        sink.write_window(
            "B737",
            "00123",
            "TAKEOFF",
            source.target,
            source.target,
            [report(source.target, value=999)],
            [],
        )
    sink.execute = original
    assert sink.execute("SELECT max(egthdm) FROM reports").fetchone()[0] == 10
    assert sink.execute("SELECT count(*) FROM onwing").fetchone()[0] == 1
