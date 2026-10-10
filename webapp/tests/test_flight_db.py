"""Offline migration and Constructor regression coverage."""

import asyncio
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from webapp.components.constructor_fig import build_chart
from webapp.data import flight_db
from webapp.data.migrate_flights import migrate


@pytest.fixture
def sources(tmp_path):
    history = tmp_path / "onwing.csv"
    pd.DataFrame(
        {
            "engine_id": [101, 102],
            "aircraft_id": [123, 456],
            "install_datetime": ["2025-01-02 10:00:00", "2025-01-01 00:00:00"],
            "removal_datetime": ["2025-01-03 23:00:00", None],
            "reason_for_removal": ["Replacement", None],
        }
    ).to_csv(history, index=False)
    registry = {}
    for family, phases in {
        "B737": ["takeoff", "cruise"],
        "A320": ["takeoff"],
        "E170": ["takeoff"],
    }.items():
        registry[family] = {"onwing": str(history)}
        for phase in phases:
            path = tmp_path / f"{family}_{phase}.parquet"
            frame = pd.DataFrame(
                {
                    "aircraft_id": [123] * 5,
                    "engine_position": [1] * 5,
                    "engine_id": [101.0, 101.0, 101.0, 102.0, None],
                    "flight_datetime": pd.to_datetime(
                        [
                            "2025-01-01 01:02:03",
                            "2025-01-02 12:00:00",
                            "2025-01-03 23:59:59.123456789",
                            "2025-01-03",
                            None,
                        ],
                        format="mixed",
                    ),
                    "flight_phase": phase.upper(),
                    "egthdm" if phase == "takeoff" else "degt": [
                        10.0,
                        20.0,
                        30.0,
                        999.0,
                        50.0,
                    ],
                    "status": ["ok"] * 5,
                }
            )
            if family == "E170":
                frame["emb_only"] = [1.0, 2.0, 3.0, 4.0, 5.0]
            frame.to_parquet(path, index=False)
            registry[family][phase] = str(path)
    return registry


@pytest.fixture
def database(tmp_path, sources, monkeypatch):
    monkeypatch.setenv("FLIGHT_DATABASE_MODE", "file")
    path = tmp_path / "test.duckdb"
    migrate(path, sources)
    return path


def test_migration_preserves_all_rows_and_wide_columns(database):
    with duckdb.connect(str(database), read_only=True) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 20
        assert (
            db.execute(
                "SELECT count(*) FROM reports WHERE engine_id IS NULL"
            ).fetchone()[0]
            == 4
        )
        assert db.execute("SELECT DISTINCT aircraft_id FROM reports").fetchall() == [
            ("00123",)
        ]
        assert (
            db.execute(
                "SELECT count(*) FROM reports WHERE aircraft_type = 'B737' AND emb_only IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT count(*) FROM onwing").fetchone()[0] == 2
        assert (
            db.execute("SELECT count(*) FROM reports WHERE status = 'ok'").fetchone()[0]
            == 20
        )
    params = flight_db.parameter_catalog("E170", database)
    assert {p["id"] for p in params} == {"EMB_ONLY@TAKEOFF", "EGTHDM@TAKEOFF"}
    assert "EMB_ONLY@TAKEOFF" not in {
        p["id"] for p in flight_db.parameter_catalog("B737", database)
    }
    assert {e["aircraft_type"] for e in flight_db.engine_options(database)} == {
        "B737",
        "A320",
        "E170",
    }


def test_repeat_import_and_failed_rebuild_preserve_snapshot(database, sources):
    with pytest.raises(FileExistsError):
        migrate(database, sources)
    migrate(database, sources, replace=True)
    before = database.read_bytes()
    bad = {
        **sources,
        "BROKEN": {"onwing": sources["B737"]["onwing"], "takeoff": "/missing.parquet"},
    }
    with pytest.raises(FileNotFoundError):
        migrate(database, bad, replace=True)
    assert database.read_bytes() == before
    assert not list(database.parent.glob("flight-migration-*"))


def test_sql_filters_inclusive_end_date_and_history_before_start(database):
    series, events = flight_db.read_trends(
        "B737",
        "101",
        ["EGTHDM@TAKEOFF", "DEGT@CRUISE"],
        "2025-01-03",
        "2025-01-03",
        3,
        database,
    )
    assert len(series) == 2
    for _, frame in series:
        assert frame.value.tolist() == [30.0]
        assert frame.smoothed.tolist() == [20.0]
        assert frame.flight_datetime.iloc[0] == pd.Timestamp(
            "2025-01-03 23:59:59.123456789"
        )
    assert events == [(pd.Timestamp("2025-01-03 23:00:00"), "Removal", "Replacement")]
    for eid, family in [("absent", "B737"), ("101", "absent")]:
        if family == "absent":
            with pytest.raises(ValueError):
                flight_db.read_trends(
                    family, eid, ["EGTHDM@TAKEOFF"], "", "", path=database
                )
        else:
            result, _ = flight_db.read_trends(
                family, eid, ["EGTHDM@TAKEOFF"], "", "", path=database
            )
            assert result[0][1].empty


def test_invalid_parameters_dates_and_missing_database(database, tmp_path):
    for params, start, end in [
        (["unknown; DROP TABLE reports"], "", ""),
        (["EGTHDM@TAKEOFF"], "2025-02-01", "2025-01-01"),
    ]:
        with pytest.raises(ValueError):
            flight_db.read_trends("B737", "101", params, start, end, path=database)
    missing = tmp_path / "missing.duckdb"
    with pytest.raises(FileNotFoundError):
        flight_db.engine_options(missing)
    assert not missing.exists()


def test_chart_has_trends_and_replacements_without_failure_features(database):
    fig = build_chart(
        "B737", "101", ["EGTHDM@TAKEOFF"], "2025-01-01", "2025-01-03", path=database
    )
    assert [trace.name for trace in fig.data] == [
        "Actual",
        "Smoothed (window=26)",
        "Install",
        "Removal",
    ]
    assert len(fig.data[0].x) == 3
    assert len(fig.layout.shapes) == 2
    assert fig.layout.yaxis2.visible is False
    assert (
        build_chart(
            "B737", "101", ["EGTHDM@TAKEOFF"], "2026-01-01", "2026-02-01", path=database
        )
        is None
    )
    assert build_chart("B737", "101", [], "", "", path=database) is None


def test_constructor_switches_families_and_shows_errors(database, monkeypatch):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        _ = [item async for item in state.on_load()]
        assert state.has_chart and not state.error
        _ = [item async for item in state.select_engine("E170:101")]
        assert "EMB_ONLY@TAKEOFF" in {e["id"] for e in state.catalog}
        _ = [item async for item in state.toggle_param("EMB_ONLY@TAKEOFF", True)]
        assert "EMB_ONLY@TAKEOFF" in state.selected_params
        _ = [item async for item in state.select_engine("B737:101")]
        assert "EMB_ONLY@TAKEOFF" not in state.selected_params
        _ = [item async for item in state.set_end_date("2020-01-01")]
        assert not state.has_chart and "Start date" in state.error
        monkeypatch.setenv(
            "FLIGHT_DATABASE_PATH", str(Path(database).parent / "missing.duckdb")
        )
        _ = [item async for item in state.on_load()]
        assert not state.has_chart and "migration" in state.error

    asyncio.run(run())


def test_constructor_url_roundtrip_and_zoom(database, monkeypatch):
    import json
    import shutil
    import subprocess
    from urllib.parse import parse_qs, urlencode, urlsplit

    import reflex as rx
    from reflex.istate.data import ReflexURL, RouterData
    from reflex_base.vars.base import LiteralVar
    from webapp.state.constructor import ConstructorState

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise URL synchronization")
    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    query = {
        "engine": "B737:101",
        "start": "2025-01-01",
        "end": "2025-01-03",
        "params": "DEGT@CRUISE,EGTHDM@TAKEOFF",
        "smoothing": "3",
        "x_start": "2025-01-02T12:00:00",
        "x_end": "2025-01-03T23:59:59.123456",
    }

    def state_at(url):
        state = ConstructorState(_reflex_internal_init=True)
        state.parent_state = rx.State(_reflex_internal_init=True)
        state.router = RouterData(url=ReflexURL(url))
        return state

    def sync_url(state, url):
        event = state._sync_url()
        code = next(
            LiteralVar.create(value)._decode()
            for name, value in event.args
            if str(name) == "javascript_code"
        )
        script = (
            f"global.window = {{location: {{href: {json.dumps(url)}}}, history: {{"
            "state: {}, replaceState(state, title, url) { window.location.href = url; }}};"
            + code
            + "; console.log(window.location.href);"
        )
        return subprocess.check_output([node, "-e", script], text=True).strip()

    async def run():
        state = state_at("http://localhost/constructor?" + urlencode(query))
        _ = [item async for item in state.on_load()]
        assert not state.error and state.has_chart
        assert state.selected_engine == query["engine"]
        assert state.selected_params == query["params"].split(",")
        assert state.smoothing_window == "3"
        assert list(state.chart_figure.layout.xaxis.range) == [
            query["x_start"],
            query["x_end"],
        ]
        url = sync_url(state, "http://localhost/constructor?unrelated=keep")
        assert parse_qs(urlsplit(url).query) == {
            k: [v] for k, v in {**query, "unrelated": "keep"}.items()
        }
        assert sync_url(state, "http://localhost/egt") == "http://localhost/egt"
        restored = state_at(url)
        _ = [item async for item in restored.on_load()]
        assert restored.selected_params == state.selected_params
        assert restored.timeline_start == state.timeline_start
        state.on_plot_relayout({"xaxis2.range": ["2025-01-02", "2025-01-03"]})
        assert state.timeline_start == "2025-01-02"
        assert (
            state.on_plot_relayout({"xaxis.range": ["invalid", "2025-01-03"]}) is None
        )
        state.on_plot_relayout({"xaxis.autorange": True})
        assert not state.timeline_start and state.chart_figure.layout.xaxis.autorange
        assert "x_start" not in parse_qs(urlsplit(sync_url(state, url)).query)
        _ = [item async for item in state.toggle_param("DEGT@CRUISE", False)]
        _ = [item async for item in state.toggle_param("EGTHDM@TAKEOFF", False)]
        _ = [item async for item in state.set_start_date("")]
        _ = [item async for item in state.set_end_date("")]
        empty_url = sync_url(state, url)
        assert parse_qs(urlsplit(empty_url).query, keep_blank_values=True)[
            "params"
        ] == [""]
        restored = state_at(empty_url)
        _ = [item async for item in restored.on_load()]
        assert restored.selected_params == [] and not restored.has_chart
        assert restored.start_date == restored.end_date == ""

    asyncio.run(run())


def test_constructor_invalid_url_values_and_reset_zoom(database, monkeypatch):
    import reflex as rx
    from reflex.istate.data import ReflexURL, RouterData
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.parent_state = rx.State(_reflex_internal_init=True)
        state.router = RouterData(
            url=ReflexURL(
                "http://localhost/constructor?engine=missing&start=bad&end=2025-99-99"
                "&params=EGTHDM%40TAKEOFF,unknown,EGTHDM%40TAKEOFF&smoothing=0&x_start=bad&x_end=bad"
            )
        )
        _ = [item async for item in state.on_load()]
        assert not state.error and state.has_chart
        assert state.selected_engine in {e["key"] for e in state.engines}
        assert state.selected_params == ["EGTHDM@TAKEOFF"]
        assert state.smoothing_window == "26" and not state.timeline_start
        state.on_plot_relayout(
            {"xaxis.range[0]": "2025-01-02", "xaxis.range[1]": "2025-01-03"}
        )
        _ = [item async for item in state.set_smoothing_window("3")]
        assert state.timeline_start == "2025-01-02"
        _ = [item async for item in state.set_start_date("2025-01-01")]
        assert not state.timeline_start and state.chart_figure.layout.xaxis.autorange
        _ = [item async for item in state.set_end_date("")]
        assert state.end_date == ""

    asyncio.run(run())


@pytest.mark.parametrize(
    "handler,args",
    [
        ("select_engine", ("E170:101",)),
        ("toggle_param", ("EGTHDM@TAKEOFF", True)),
    ],
)
def test_constructor_loading_keeps_previous_chart(database, monkeypatch, handler, args):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        _ = [item async for item in state.on_load()]
        previous = state.chart_figure.to_json()
        previous_height = state.chart_height
        updates = getattr(state, handler)(*args)
        await anext(updates)
        assert state.is_computing and state.has_chart
        assert state.chart_figure.to_json() == previous
        assert state.chart_height == previous_height
        _ = [item async for item in updates]
        assert not state.is_computing and state.has_chart

    asyncio.run(run())


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("", "", [10.0, 20.0, 30.0]),
        ("", "2025-01-02", [10.0, 20.0]),
        ("2025-01-02", "", [20.0, 30.0]),
    ],
)
def test_open_date_bounds_do_not_overflow_timestamp_precision(
    database, start, end, expected
):
    series, _ = flight_db.read_trends(
        "B737",
        "101",
        ["EGTHDM@TAKEOFF"],
        start,
        end,
        path=database,
    )
    assert series[0][1].value.tolist() == expected


@pytest.fixture
def quack_database(database, monkeypatch):
    """Opt-in real network test, using the same fixtures as the file backend."""
    import os
    import secrets
    import socket
    import subprocess
    import sys
    import time

    if os.environ.get("RUN_QUACK_TESTS") != "1":
        pytest.skip("Set RUN_QUACK_TESTS=1 after installing the Quack extension")
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    credential = secrets.token_hex(32)
    # Emulate a database created before Quack support was added.
    with duckdb.connect(str(database)) as db:
        db.execute(
            "ALTER TABLE import_sources ALTER COLUMN imported_at SET DEFAULT current_timestamp"
        )
    uri = f"quack:127.0.0.1:{port}"
    monkeypatch.setenv("FLIGHT_DATABASE_MODE", "quack")
    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    monkeypatch.setenv("FLIGHT_QUACK_URL", uri)
    monkeypatch.setenv("QUACK_LISTEN_URI", uri)
    monkeypatch.setenv("QUACK_TOKEN", credential)
    monkeypatch.delenv("QUACK_TOKEN_FILE", raising=False)
    with (database.parent / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "webapp.data.quack_server"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                log.seek(0)
                if "Flight database ready" in log.read():
                    break
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Quack server did not start")
                time.sleep(0.05)
            yield process
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.seek(0)
            output = log.read()
            assert credential not in output
            assert process.returncode == 0


def test_quack_queries_match_file_and_writes_are_persistent(database, quack_database):
    from concurrent.futures import ThreadPoolExecutor
    from webapp.data.quack import connect_remote, transaction

    # A separate process owns the file throughout this test. All reads and writes
    # below travel over Quack; no in-process shared-connection shortcut is used.
    with connect_remote() as reader:
        assert reader.execute("SELECT count(*) FROM reports").fetchone()[0] == 20
        with pytest.raises(duckdb.Error):
            reader.execute("INSERT INTO reports (engine_id) VALUES ('blocked')")
    assert len(flight_db.engine_options()) == 6
    assert {e["id"] for e in flight_db.parameter_catalog("B737")} == {
        "EGTHDM@TAKEOFF",
        "DEGT@CRUISE",
    }
    assert flight_db.date_bounds("B737", "101")[0] == pd.Timestamp(
        "2025-01-01 01:02:03"
    )
    series, events = flight_db.read_trends(
        "B737",
        "101",
        ["EGTHDM@TAKEOFF"],
        "2025-01-03",
        "2025-01-03",
        3,
    )
    assert series[0][1].value.tolist() == [30.0]
    assert series[0][1].smoothed.tolist() == [20.0]
    assert series[0][1].flight_datetime.iloc[0] == pd.Timestamp(
        "2025-01-03 23:59:59.123456789"
    )
    assert events == [(pd.Timestamp("2025-01-03 23:00:00"), "Removal", "Replacement")]
    assert build_chart("B737", "101", ["EGTHDM@TAKEOFF"], "", "") is not None

    def read():
        with connect_remote() as db:
            return db.execute("SELECT count(*) FROM reports").fetchone()[0]

    with connect_remote(read_only=False) as writer, transaction(writer):
        writer.execute("""
            INSERT INTO reports (aircraft_type, aircraft_id, engine_position,
                engine_id, flight_phase, flight_datetime, egthdm)
            VALUES ('B737', '00123', 1, '101', 'TAKEOFF', '2025-01-04 12:00:00', 40)
        """)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: read(), range(2))) == [20, 20]
    assert read() == 21
    with connect_remote(read_only=False) as writer:
        with pytest.raises(ValueError, match="abort batch"):
            with transaction(writer):
                writer.execute("INSERT INTO reports (engine_id) VALUES ('rolled-back')")
                raise ValueError("abort batch")
    assert read() == 21
    series, _ = flight_db.read_trends(
        "B737", "101", ["EGTHDM@TAKEOFF"], "2025-01-04", "", 3
    )
    assert series[0][1].smoothed.tolist() == [30.0]
    quack_database.terminate()
    quack_database.wait(timeout=10)
    with duckdb.connect(str(database), read_only=True) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 21


def test_quack_rejects_bad_token_without_file_fallback(quack_database, monkeypatch):
    monkeypatch.setenv("QUACK_TOKEN", "wrong-token-" * 4)
    with pytest.raises(RuntimeError, match="Could not connect") as error:
        flight_db.engine_options()
    assert "wrong-token" not in str(error.value)


def test_quack_mode_requires_credentials_and_never_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHT_DATABASE_MODE", "quack")
    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(tmp_path / "missing.duckdb"))
    monkeypatch.delenv("QUACK_TOKEN_FILE", raising=False)
    monkeypatch.delenv("QUACK_TOKEN", raising=False)
    with pytest.raises(ValueError, match="QUACK_TOKEN"):
        flight_db.connect()
    assert not (tmp_path / "missing.duckdb").exists()
