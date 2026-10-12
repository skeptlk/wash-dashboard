"""Offline migration and Constructor regression coverage."""

import asyncio
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from webapp.components.constructor_fig import build_chart
from webapp.data import flight_db
from webapp.data.migrate_flights import migrate


async def _settle(state, updates):
    """Dispatch scheduled chart events, as Reflex does after a control event."""
    from webapp.state.constructor import ConstructorState

    events = [item async for item in updates]
    for event in events:
        if event.handler == ConstructorState.prepare_chart:
            children = [item async for item in ConstructorState.prepare_chart.fn(
                state, state.chart_generation
            )]
            if children:
                await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 0)
    return events


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


def test_installations_use_full_engine_history_across_phases(database):
    first = pd.Timestamp("2025-01-01 01:02:03")
    with duckdb.connect(str(database)) as db:
        # The first report has no selected reading, but still starts the history.
        db.execute("""UPDATE reports SET egthdm = NULL
            WHERE aircraft_type = 'B737' AND engine_id = '101'
              AND flight_datetime = '2025-01-01 01:02:03'""")
        db.execute("""INSERT INTO onwing (engine_id, install_datetime, removal_datetime)
            VALUES ('101', '2024-12-01', '2024-12-02'),
                   ('101', '2025-01-01 01:02:03', NULL)""")
    _, events = flight_db.read_trends(
        "B737", "101", ["EGTHDM@TAKEOFF"], "", "", path=database
    )
    installs = [dt for dt, kind, _ in events if kind == "Install"]
    assert installs == [first, pd.Timestamp("2025-01-02 10:00")]
    assert (pd.Timestamp("2024-12-02"), "Removal", None) in events
    _, narrowed = flight_db.read_trends(
        "B737", "101", ["DEGT@CRUISE"], "2025-01-02", "", path=database
    )
    assert (pd.Timestamp("2025-01-02 10:00"), "Install", None) in narrowed


def test_early_installation_does_not_extend_chart_timeline(database):
    fig = build_chart("B737", "102", ["EGTHDM@TAKEOFF"], "", "", path=database)
    assert len(next(trace for trace in fig.data if trace.name == "Install").x) == 0
    assert not fig.layout.shapes
    assert pd.Timestamp(fig.layout.xaxis.tickvals[0]) == pd.Timestamp("2025-01-03")


def test_gap_overlays_and_cached_markers_keep_their_subplot():
    from webapp.components.constructor_fig import add_series, copy_series, empty_chart

    entry = {"name": "EGTHDM", "phase": "TAKEOFF"}
    frame = pd.DataFrame(
        {
            "flight_datetime": pd.to_datetime(
                ["2025-01-01", "2025-01-02", "2025-02-02"]
            ),
            "value": [10.0, 20.0, 30.0],
            "smoothed": [10.0, 15.0, 20.0],
        }
    )
    events = [
        (pd.Timestamp("2025-01-10"), "Install", None),
        (pd.Timestamp("2025-01-20"), "Removal", "Replacement"),
    ]
    source = empty_chart("B737", "101", [entry])
    add_series(source, entry, frame, events, 1, 15)
    original = source.to_json()
    copied = empty_chart("B737", "101", [entry, entry, entry])
    for row in (1, 2, 3):
        copy_series(copied, source, row)
    assert source.to_json() == original
    assert len(copied.layout.shapes) == 9
    for row, xref, yref in [
        (1, "x", "y domain"),
        (2, "x2", "y3 domain"),
        (3, "x3", "y5 domain"),
    ]:
        shapes = copied.layout.shapes[(row - 1) * 3 : row * 3]
        assert [shape.type for shape in shapes] == ["rect", "line", "line"]
        assert all(shape.xref == xref and shape.yref == yref for shape in shapes)
        assert (shapes[0].x0, shapes[0].x1) == (
            pd.Timestamp("2025-01-02"),
            pd.Timestamp("2025-02-02"),
        )
        annotation = next(a for a in copied.layout.annotations if a.xref == xref)
        assert annotation.text == "No data" and annotation.yref == yref
        assert pd.Timestamp(annotation.x) == pd.Timestamp("2025-01-17 12:00")
        assert annotation.y == 0.5 and annotation.textangle == -90
    direct = empty_chart("B737", "101", [entry, entry, entry])
    for row in (1, 2, 3):
        add_series(direct, entry, frame, events, row, 15)
    assert json.loads(copied.to_json()) == json.loads(direct.to_json())


@pytest.mark.parametrize(
    "gap, expected",
    [
        (pd.Timedelta(days=7), False),
        (pd.Timedelta(days=30), False),
        (pd.Timedelta(days=30, seconds=1), True),
    ],
)
def test_constructor_no_data_requires_more_than_thirty_days(gap, expected):
    import numpy as np
    from webapp.components.constructor_fig import add_series, empty_chart

    entry = {"name": "EGTHDM", "phase": "TAKEOFF"}
    first = pd.Timestamp("2025-01-01")
    frame = pd.DataFrame(
        {
            "flight_datetime": [first, first + gap],
            "value": [10.0, 20.0],
            "smoothed": [10.0, 15.0],
        }
    )
    fig = empty_chart("B737", "101", [entry])
    add_series(fig, entry, frame, [], 1, 15)
    assert bool(fig.layout.shapes) == expected
    assert any(a.text == "No data" for a in fig.layout.annotations) == expected
    assert bool(np.isnan(fig.data[1].x).any()) == expected


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
        "Raw",
        "Smoothed (window=26)",
        "Install",
        "Removal",
    ]
    assert len(fig.data[0].x) == 3
    assert fig.data[0].marker.size == 4
    assert fig.layout.title.text is None
    assert fig.layout.annotations[0].text == (
        "EGTHDM (Takeoff), ESN = 101, Pos = 1, 00123, B737"
    )
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
        _ = await _settle(state, state.on_load())
        assert state.has_chart and not state.error
        _ = await _settle(state, state.select_engine("E170:101"))
        assert "EMB_ONLY@TAKEOFF" in {e["id"] for e in state.catalog}
        _ = await _settle(state, state.toggle_param("EMB_ONLY@TAKEOFF", True))
        assert "EMB_ONLY@TAKEOFF" in state.selected_params
        _ = await _settle(state, state.select_engine("B737:101"))
        assert "EMB_ONLY@TAKEOFF" not in state.selected_params
        _ = await _settle(state, state.set_start_date("2025-01-01"))
        _ = await _settle(state, state.set_end_date("2020-01-01"))
        assert not state.has_chart and "Start date" in state.error
        monkeypatch.setenv(
            "FLIGHT_DATABASE_PATH", str(Path(database).parent / "missing.duckdb")
        )
        _ = await _settle(state, state.on_load())
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
        _ = await _settle(state, state.on_load())
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
        _ = await _settle(restored, restored.on_load())
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
        _ = await _settle(state, state.toggle_param("DEGT@CRUISE", False))
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", False))
        _ = await _settle(state, state.set_start_date(""))
        _ = await _settle(state, state.set_end_date(""))
        empty_url = sync_url(state, url)
        assert parse_qs(urlsplit(empty_url).query, keep_blank_values=True)[
            "params"
        ] == [""]
        restored = state_at(empty_url)
        _ = await _settle(restored, restored.on_load())
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
        _ = await _settle(state, state.on_load())
        assert not state.error and state.has_chart
        assert state.selected_engine in {e["key"] for e in state.engines}
        assert state.selected_params == ["EGTHDM@TAKEOFF"]
        assert state.smoothing_window == "26" and not state.timeline_start
        state.on_plot_relayout(
            {"xaxis.range[0]": "2025-01-02", "xaxis.range[1]": "2025-01-03"}
        )
        _ = await _settle(state, state.set_smoothing_window("3"))
        assert state.timeline_start == "2025-01-02"
        _ = await _settle(state, state.set_start_date("2025-01-01"))
        assert not state.timeline_start and state.chart_figure.layout.xaxis.autorange
        _ = await _settle(state, state.set_end_date(""))
        assert state.end_date == ""

    asyncio.run(run())


@pytest.mark.parametrize(
    "handler,args",
    [
        ("select_engine", ("E170:101",)),
    ],
)
def test_constructor_loading_keeps_previous_chart(database, monkeypatch, handler, args):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        _ = await _settle(state, state.on_load())
        previous = state.chart_figure.to_json()
        previous_height = state.chart_height
        updates = getattr(state, handler)(*args)
        await anext(updates)
        assert state.is_computing and state.has_chart
        assert state.chart_figure.to_json() == previous
        assert state.chart_height == previous_height
        _ = await _settle(state, updates)
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
        with flight_db.connect():
            pass
    assert not (tmp_path / "missing.duckdb").exists()


def test_progressive_parameters_are_acknowledged_and_not_retransmitted(
    database, monkeypatch
):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    calls = []
    original = flight_db.read_trends

    def read(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(flight_db, "read_trends", read)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        assert state.selected_params == ["EGTHDM@TAKEOFF", "DEGT@CRUISE"]
        assert calls == [["EGTHDM@TAKEOFF"]]
        assert state.has_chart and state.is_computing
        assert state.loaded_params == 1 and state.chart_offset == 0
        generation = state.chart_generation
        first = state.chart_figure.to_json()
        await ConstructorState.load_next_parameter.fn(state, generation - 1, 1)
        await ConstructorState.load_next_parameter.fn(state, generation, 0)
        assert state.chart_figure.to_json() == first
        await ConstructorState.load_next_parameter.fn(state, generation, 1)
        assert calls == [["EGTHDM@TAKEOFF"], ["DEGT@CRUISE"]]
        assert state.loaded_params == 2 and not state.is_computing
        assert state.chart_offset == 4 and len(state.chart_figure.data) == 4
        assert state.chart_figure.data[0].xaxis == "x2"
        expected = build_chart(
            "B737",
            "101",
            state.selected_params,
            state.start_date,
            state.end_date,
            path=database,
        )
        import json

        expected.update_xaxes(range=None, autorange=True)
        expected.update_layout(uirevision=state.chart_data_generation)
        for row, pid in enumerate(state.selected_params, 1):
            expected.update_yaxes(
                uirevision=f"{state.chart_data_generation}:{pid}",
                row=row,
                col=1,
                secondary_y=False,
            )
            for index, trace in enumerate(expected.data[(row - 1) * 4 : row * 4]):
                trace.meta = f"{pid}:{index}"
        assert json.loads(state._chart_figure.to_json()) == json.loads(
            expected.to_json()
        )
        await ConstructorState.load_next_parameter.fn(state, generation, 1)
        assert len(calls) == 2
        state.on_plot_relayout({"xaxis.range": ["2025-01-02", "2025-01-03"]})
        assert len(state.chart_figure.data) == 0 and state.chart_offset == 8
        assert list(state.chart_figure.layout.xaxis.range) == [
            "2025-01-02",
            "2025-01-03",
        ]
        _ = await _settle(state, state.select_engine("B737:102"))
        await ConstructorState.load_next_parameter.fn(state, generation, 2)
        assert state.loaded_params == 1

    asyncio.run(run())


def test_progressive_empty_first_row_and_later_failure(database, monkeypatch):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    # Give the first selected parameter no readings; later rows must still load.
    with duckdb.connect(str(database)) as db:
        db.execute("UPDATE reports SET egthdm=NULL WHERE aircraft_type='B737'")

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        assert state.has_chart and state.is_computing
        assert len(state.chart_figure.data[0].x) == 0
        await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 1)
        assert state.has_chart and not state.is_computing
        _ = await _settle(state, state.set_end_date("2025-01-03"))
        _ = await _settle(state, state.set_start_date("2026-01-01"))
        assert state.error  # invalid date order stops loading
        state.start_date = "2025-01-01"
        _ = await _settle(state, state._refresh())

        def fail(*args, **kwargs):
            raise RuntimeError("transport lost")

        monkeypatch.setattr(flight_db, "read_trends", fail)
        await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 1)
        assert not state.is_computing and "remaining parameters" in state.error

    asyncio.run(run())


def test_constructor_reuses_catalog_for_same_family(database, monkeypatch):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    original = flight_db.parameter_catalog
    calls = []

    def catalog(family, *args):
        calls.append(family)
        return original(family, *args)

    monkeypatch.setattr(flight_db, "parameter_catalog", catalog)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 1)
        _ = await _settle(state, state.select_engine("B737:102"))
        await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 1)
        assert sorted(calls) == ["A320", "B737", "E170"]
        _ = await _settle(state, state.select_engine("E170:101"))
        assert sorted(calls) == ["A320", "B737", "E170"]

    asyncio.run(run())


def test_sql_string_values_cannot_change_query(database):
    attack = "B737' OR TRUE --"
    assert flight_db.parameter_catalog(attack, database) == []
    assert flight_db.date_bounds("B737", "101' OR TRUE --", database) == (None, None)
    series, events = flight_db.read_trends(
        "B737", "101' OR TRUE --", ["EGTHDM@TAKEOFF"], "", "", path=database
    )
    assert series[0][1].empty and events == []


def test_parameter_selector_loads_and_switches_families(database, monkeypatch):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    with duckdb.connect(str(database)) as db:
        db.execute("""
            INSERT INTO report_parameters VALUES
                ('B737', 'TAKEOFF', 'pip_hidden'),
                ('B737', 'CRUISE', 'PIP_HIDDEN'),
                ('B737', 'TAKEOFF', 'visible_pip_value')
        """)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        # Hydration initially renders empty selectors before on_load runs.
        assert state.catalog == []
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        delta = state.get_delta()[state.get_full_name()]
        assert {p["name"] for p in delta["catalog_rx_state_"]} == {
            "EGTHDM", "VISIBLE_PIP_VALUE", "DEGT",
        }
        assert all(not p["name"].lower().startswith("pip_") for p in state.catalog)
        _ = await _settle(state, state.select_engine("E170:101"))
        assert {p["name"] for p in state.catalog} == {"EGTHDM", "EMB_ONLY"}
        assert all(p["phase"] == "TAKEOFF" for p in state.catalog)

    asyncio.run(run())


def test_constructor_zoom_keeps_dates_data_and_independent_y_ranges(
    database, monkeypatch
):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    calls = []
    original = flight_db.read_trends

    def read(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(flight_db, "read_trends", read)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        dates = state.start_date, state.end_date
        generation = state.chart_generation
        state.on_plot_relayout(
            {
                "xaxis.range[0]": "2025-01-02",
                "xaxis.range[1]": "2025-01-03",
                "yaxis.range[0]": 15,
                "yaxis.range[1]": 25,
            }
        )
        assert calls == [["EGTHDM@TAKEOFF"]]
        assert (state.start_date, state.end_date) == dates
        assert state.chart_generation == generation and state.loaded_params == 1
        assert len(state.chart_figure.data) == 0
        assert state._chart_figure.layout.yaxis.range == (15, 25)
        assert state._chart_figure.layout.yaxis3.range is None
        assert state._chart_figure.layout.yaxis2.range == (0, 1)
        for axis in (state.chart_figure.layout.xaxis, state.chart_figure.layout.xaxis2):
            assert axis.range == ("2025-01-02", "2025-01-03")
        # A parameter already being loaded retains the viewport on arrival.
        await ConstructorState.load_next_parameter.fn(state, generation, 1)
        assert state.chart_figure.layout.yaxis.range == (15, 25)
        assert len(calls) == 2
        state.on_plot_relayout({"yaxis3.range": [12, 18]})
        assert state.chart_figure.layout.yaxis3.range == (12, 18)
        assert state.chart_figure.layout.yaxis.range == (15, 25)
        assert len(calls) == 2 and (state.start_date, state.end_date) == dates
        # Repeated events from Plotly.react do not trigger an update loop.
        assert state.on_plot_relayout({"yaxis3.range": [12, 18]}) is None
        assert state.on_plot_relayout({"yaxis3.range": [None, 18]}) is None
        state.on_plot_relayout({"yaxis3.autorange": True})
        assert state.chart_figure.layout.yaxis3.range is None
        assert state.chart_figure.layout.yaxis.range == (15, 25)
        state.on_plot_relayout({"xaxis.autorange": True, "yaxis.autorange": True})
        assert state.chart_figure.layout.yaxis.range is None
        assert state.chart_figure.layout.xaxis.range is None
        assert len(calls) == 2

    asyncio.run(run())


def test_subplot_titles_use_registration_from_engine_list(database, monkeypatch):
    monkeypatch.setitem(flight_db.AIRCRAFT_REG, "00123", "RA-73424")
    engine = next(
        e for e in flight_db.engine_options(database) if e["key"] == "A320:101"
    )
    fig = build_chart("A320", "101", ["EGTHDM@TAKEOFF"], "", "", path=database)
    assert engine["label"].endswith("RA-73424")
    assert fig.layout.annotations[0].text == (
        "EGTHDM (Takeoff), ESN = 101, Pos = 1, RA-73424, A320"
    )


def test_aircraft_model_uses_latest_aircraft_without_changing_family(database):
    with duckdb.connect(str(database)) as db:
        db.execute("INSERT INTO aircraft VALUES ('00456', 'A320', 'A321-200')")
        db.execute("""UPDATE reports SET aircraft_id='00456'
            WHERE aircraft_type='A320' AND engine_id='101'
            AND flight_datetime > '2025-01-03'""")
    options = {e["key"]: e for e in flight_db.engine_options(database)}
    assert options["A320:101"]["label"] == "101: A321-200 00456"
    assert options["A320:101"]["aircraft_type"] == "A320"
    assert options["B737:101"]["aircraft_model"] == "B737"
    fig = build_chart("A320", "101", ["EGTHDM@TAKEOFF"], "", "", path=database)
    assert fig.layout.annotations[0].text.endswith("00456, A321-200")


def test_empty_dates_follow_each_engine_full_history_and_reset_zoom(
    database, monkeypatch
):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    with duckdb.connect(str(database)) as db:
        db.execute("""UPDATE reports SET flight_datetime=flight_datetime + INTERVAL '4 years'
            WHERE engine_id='102'""")

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        _ = await _settle(state, state.on_load())
        assert state.start_date == state.end_date == ""
        assert len(state.chart_figure.data[0].x) == 3
        state.on_plot_relayout({"xaxis.range": ["2025-01-02", "2025-01-03"]})
        _ = await _settle(state, state.select_engine("B737:102"))
        assert state.start_date == state.end_date == ""
        assert state.timeline_start == state.timeline_end == ""
        assert state.chart_figure.layout.xaxis.autorange
        assert state.has_chart and len(state.chart_figure.data[0].x) == 1
        assert pd.to_datetime(state.chart_figure.data[0].x[0], unit="ms").year == 2029
        _ = await _settle(state, state.set_start_date("2029-01-01"))
        _ = await _settle(state, state.select_engine("B737:101"))
        assert state.start_date == "2029-01-01" and state.end_date == ""

    asyncio.run(run())


def test_time_ticks_include_last_reading_and_follow_zoom():
    import plotly.graph_objects as go
    from webapp.components.constructor_fig import empty_chart, update_time_ticks
    from webapp.data.egt_params import plotly_timestamps

    fig = empty_chart("B737", "101", [{"name": "EGTHDM", "phase": "TAKEOFF"}])
    fig.add_trace(
        go.Scatter(x=plotly_timestamps(["2022-01-01", "2026-09-14"]), name="Raw")
    )
    update_time_ticks(fig)
    assert len(fig.layout.xaxis.tickvals) == 12
    assert pd.Timestamp(fig.layout.xaxis.tickvals[-1]) == pd.Timestamp("2026-09-14")
    fig.add_trace(go.Scatter(x=plotly_timestamps(["2016-07-01"]), name="Install"))
    update_time_ticks(fig)
    assert pd.Timestamp(fig.layout.xaxis.tickvals[0]) == pd.Timestamp("2016-07-01")
    assert pd.Timestamp(fig.layout.xaxis.tickvals[-1]) == pd.Timestamp("2026-09-14")
    update_time_ticks(fig, "2023-01-01", "2024-01-01")
    assert pd.Timestamp(fig.layout.xaxis.tickvals[0]) == pd.Timestamp("2023-01-01")
    assert pd.Timestamp(fig.layout.xaxis.tickvals[-1]) == pd.Timestamp("2024-01-01")


def test_quack_aircraft_import(tmp_path, quack_database):
    from webapp.data.import_aircraft import import_aircraft
    from webapp.data.quack import connect_remote

    source = tmp_path / "aircraft.csv"
    source.write_text("aircraft_id,aircraft_family,aircraft_type\n123,A320,A321-200\n")
    assert import_aircraft(source) == import_aircraft(source) == 1
    with connect_remote() as db:
        assert db.execute("SELECT * FROM aircraft").fetchall() == [
            ("00123", "A320", "A321-200")
        ]
    option = next(e for e in flight_db.engine_options() if e["key"] == "A320:101")
    assert "A321-200" in option["label"]


def test_parameter_changes_reuse_series_and_preserve_zoom(database, monkeypatch):
    from reflex.utils.serializers import serialize
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    calls = []
    original = flight_db.read_trends

    def read(*args, **kwargs):
        calls.append((args[1], args[2], args[5]))
        return original(*args, **kwargs)

    monkeypatch.setattr(flight_db, "read_trends", read)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "E170:101"
        _ = await _settle(state, state.on_load())
        revision = state.chart_data_generation
        initial = state._chart_figure.to_json()
        # Checking an already selected parameter is a no-op.
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", True))
        assert state._chart_figure.to_json() == initial and len(calls) == 1
        state.on_plot_relayout(
            {
                "xaxis.range": ["2025-01-02", "2025-01-03"],
                "yaxis.range": [15, 25],
            }
        )
        updates = state.toggle_param("EMB_ONLY@TAKEOFF", True)
        await anext(updates)
        assert state.has_chart and state.loaded_params == 0  # old chart stays visible
        _ = await _settle(state, updates)
        assert [call[1] for call in calls] == [["EGTHDM@TAKEOFF"], ["EMB_ONLY@TAKEOFF"]]
        assert state.chart_data_generation == revision
        assert state.chart_figure.layout.yaxis.range == (15, 25)
        assert state.chart_figure.layout.xaxis2.range == ("2025-01-02", "2025-01-03")
        wire = serialize(state.chart_figure)["data"]
        assert all("x" not in t and "y" not in t for t in wire[:4])
        assert wire[0]["meta"] == "EGTHDM@TAKEOFF:0"
        assert "x" in wire[4] and "y" in wire[4]
        state.on_plot_relayout({"yaxis3.range": [1.5, 2.5]})
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", False))
        assert len(calls) == 2 and not state.is_computing
        assert state.chart_figure.layout.yaxis.range == (1.5, 2.5)
        assert state.chart_figure.data[0].xaxis == "x"
        assert state.chart_figure.data[0].showlegend is True
        assert all(
            "x" not in t and "y" not in t for t in serialize(state.chart_figure)["data"]
        )
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", True))
        assert len(calls) == 2
        assert state.chart_figure.layout.yaxis.range == (1.5, 2.5)
        assert state.chart_figure.layout.yaxis3.range == (15, 25)
        # Reset can reorder existing parameters without querying them again.
        _ = await _settle(state, state.reset_params())
        assert len(calls) == 2 and state.chart_figure.layout.yaxis.range == (15, 25)
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", False))
        assert not state.has_chart
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", True))
        assert len(calls) == 2 and state.has_chart
        # An unmounted chart needs arrays again, though no SQL reload is needed.
        assert "x" in serialize(state.chart_figure)["data"][0]
        _ = await _settle(state, state.set_smoothing_window("3"))
        assert len(calls) == 3 and state.chart_data_generation != revision
        _ = await _settle(state, state.select_engine("E170:102"))
        assert calls[-1][0] == "102" and len(calls) == 4
        assert state._chart_figure.data[0].y.tolist() == [999.0]
        _ = await _settle(state, state.set_start_date("2025-01-03"))
        assert len(calls) == 5

    asyncio.run(run())


def test_constructor_predictions_match_default_model_with_full_history(database):
    from enginewash import FlightPhase, FlightRecord, predict_egt_failure_enhanced
    from webapp.data.egt_model import DEFAULT_MODEL_PARAMS

    times = pd.date_range("2025-01-01", periods=80, freq="12h")
    # Constant EGTHDM: only the cruise DEGT change can trigger a prediction.
    values = [0.0] * 40 + [40.0] * 40
    records = [
        FlightRecord("101", t, "EGTHDM", FlightPhase.TAKEOFF, 30.0)
        for t in times
    ]
    cruise = [
        FlightRecord("101", t + pd.Timedelta(hours=1), "DEGT", FlightPhase.CRUISE, v)
        for t, v in zip(times, values)
    ]
    with duckdb.connect(str(database)) as db:
        db.execute("DELETE FROM reports")
        db.executemany(
            "INSERT INTO reports (aircraft_type, engine_id, flight_datetime, flight_phase, egthdm, degt) VALUES (?, ?, ?, ?, ?, ?)",
            [("B737", "101", r.flight_datetime, "TAKEOFF", r.float_value, None) for r in records]
            + [("B737", "101", r.flight_datetime, "CRUISE", None, r.float_value) for r in cruise],
        )
    expected = predict_egt_failure_enhanced("101", records, cruise, **DEFAULT_MODEL_PARAMS)
    lo, hi = pd.Timestamp("2025-01-25"), pd.Timestamp("2025-01-26")
    expected = [(t, v) for t, v in expected if lo <= t < hi]
    assert expected
    catalog = flight_db.parameter_catalog("B737", database)
    actual = flight_db.read_egt_predictions(
        "B737", "101", "2025-01-25", "2025-01-25", catalog=catalog, path=database
    )
    assert actual == expected
    assert flight_db.read_egt_predictions(
        "B737", "102", "", "", catalog=catalog, path=database
    ) == []
    assert flight_db.read_egt_predictions(
        "B737", "101", "", "", catalog=[], path=database
    ) == []


def test_constructor_prediction_toggle_and_cache(database, monkeypatch):
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    calls = []

    def predict(family, eid, start, end, *, catalog):
        calls.append((family, eid, start, end))
        return [(pd.Timestamp("2025-01-02 12:00"), 12.5)]

    monkeypatch.setattr(flight_db, "read_egt_predictions", predict)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        _ = await _settle(state, state.on_load())
        assert not calls
        # Restored LocalStorage value is used by on_load, just like a toggle.
        state.egt_indication_store = "true"
        _ = await _settle(state, state.on_load())
        assert len(calls) == 1
        prediction = next(t for t in state._chart_figure.data if t.name == "EGT Indication")
        assert prediction.yaxis == "y" and list(prediction.y) == [12.5]
        generation = state.chart_data_generation
        _ = await _settle(state, state.set_smoothing_window("10"))
        assert len(calls) == 1  # Chart smoothing never changes the model.
        _ = await _settle(state, state.set_egt_indication(False))
        assert state.egt_indication_store == "false"
        assert state.chart_data_generation > generation
        assert not any(t.name == "EGT Indication" for t in state._chart_figure.data)
        _ = await _settle(state, state.set_egt_indication(True))
        assert len(calls) == 1
        _ = await _settle(state, state.select_engine("B737:102"))
        assert calls[-1][:2] == ("B737", "102")
        _ = await _settle(state, state.set_start_date("2025-01-02"))
        assert calls[-1][2] == "2025-01-02"
        _ = await _settle(state, state.toggle_param("DEGT@CRUISE", True))
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", False))
        assert not any(t.name == "EGT Indication" for t in state._chart_figure.data)
        _ = await _settle(state, state.toggle_param("EGTHDM@TAKEOFF", True))
        predictions = [t for t in state._chart_figure.data if t.name == "EGT Indication"]
        assert len(predictions) == 1
        assert predictions[0].yaxis == "y3" and predictions[0].showlegend

    asyncio.run(run())


@pytest.mark.parametrize("fail_old", [False, True])
@pytest.mark.parametrize("stage", ["first", "next", "predictions"])
def test_constructor_switches_before_old_request_finishes(database, monkeypatch, fail_old, stage):
    """A new engine and parameter choice completes before a blocked old read."""
    import threading
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    started, release = threading.Event(), threading.Event()
    original = flight_db.read_trends

    def wait_for_release():
        started.set()
        assert release.wait(10)
        if fail_old:
            raise RuntimeError("obsolete request failed")

    def read(family, eid, params, *args, **kwargs):
        if eid == "101" and (
            stage == "first" or (stage == "next" and params == ["DEGT@CRUISE"])
        ):
            wait_for_release()
        return original(family, eid, params, *args, **kwargs)

    def predictions(family, eid, *args, **kwargs):
        if eid == "101":
            wait_for_release()
        return []

    monkeypatch.setattr(flight_db, "read_trends", read)
    monkeypatch.setattr(flight_db, "read_egt_predictions", predictions)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        state.egt_indication_store = "true" if stage == "predictions" else "false"
        if stage == "next":
            await _settle(state, state.on_load())
            old = asyncio.create_task(ConstructorState.load_next_parameter.fn(
                state, state.chart_generation, 1
            ))
        else:
            old = asyncio.create_task(_settle(state, state.on_load()))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            async with asyncio.timeout(3):
                await _settle(state, state.select_engine("E170:102"))
                await _settle(state, state.toggle_param("EMB_ONLY@TAKEOFF", True))
            assert not old.done()
            assert state.selected_engine == "E170:102"
            assert state.selected_params == ["EGTHDM@TAKEOFF", "EMB_ONLY@TAKEOFF"]
            assert state.has_chart and not state.is_computing
            assert not state.error
            latest = state._chart_figure.to_json()
            generation = state.chart_generation
        finally:
            release.set()
            await asyncio.wait_for(old, 5)
        assert state.chart_generation == generation
        assert state._chart_figure.to_json() == latest
        assert not state.error and not state._loading_param

    asyncio.run(run())


@pytest.mark.parametrize("persisted", [False, True])
def test_constructor_reload_resends_cached_arrays_and_catalog(database, monkeypatch, persisted):
    """A browser reload has no trace cache, even when server state survives."""
    from reflex.utils.serializers import serialize
    from webapp.state.constructor import ConstructorState

    monkeypatch.setenv("FLIGHT_DATABASE_PATH", str(database))
    calls = []
    original = flight_db.read_trends

    def read(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(flight_db, "read_trends", read)

    async def run():
        state = ConstructorState(_reflex_internal_init=True)
        state.selected_engine = "B737:101"
        await _settle(state, state.on_load())
        await ConstructorState.load_next_parameter.fn(state, state.chart_generation, 1)
        assert len(calls) == 2
        if persisted:
            import pickle
            state._chart_figure = pickle.loads(pickle.dumps(state._chart_figure))
            state._series_cache = pickle.loads(pickle.dumps(dict(state._series_cache)))
        state._clean()
        await _settle(state, state.on_load())
        assert len(calls) == 2  # reuse SQL results, not the vanished browser cache
        wire = serialize(state.chart_figure)
        raw = [trace for trace in wire['data'] if trace['name'] == 'Raw']
        assert len(raw) == 2 and all('x' in t and 'y' in t for t in raw)
        delta = state.get_delta()[state.get_full_name()]
        assert delta['catalog_rx_state_']
        assert delta['selected_engine_rx_state_'] == 'B737:101'
        assert state.has_chart and not state.is_computing

    asyncio.run(run())
