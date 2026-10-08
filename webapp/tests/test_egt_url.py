"""EGT URL restoration and Plotly viewport events, without dataset downloads."""
import asyncio
import importlib
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import reflex as rx
from reflex.istate.data import ReflexURL, RouterData


@pytest.fixture(scope="module")
def modules():
    root = Path(__file__).resolve().parents[1] / "webapp"
    name = "_egt_url_test"
    package = types.ModuleType(name)
    package.__path__ = [str(root)]
    data = types.ModuleType(f"{name}.data")
    data.__path__ = [str(root / "data")]
    data.LOADED = {}
    data.AIRCRAFT_TYPES = []
    stubs = {name: package, data.__name__: data}
    for child, attrs in {
        "labels": {"labels_for": lambda eid: []},
        "versions": {"list_versions": lambda: []},
        "derived": {"install_removal_events_for": lambda *a: [], "maint_events_for_ata": lambda *a: []},
        "egt_indication": {
            "EGT_FAILURE_ENGINES": set(), "EGT_PREDICTION_ENGINES": set(),
            "failure_spans_for": lambda *a, **kw: [],
        },
    }.items():
        module = types.ModuleType(f"{name}.data.{child}")
        module.__dict__.update(attrs)
        stubs[module.__name__] = module
    with patch.dict(sys.modules, stubs):
        yield (
            importlib.import_module(f"{name}.state.egt"),
            importlib.import_module(f"{name}.state.base"),
            importlib.import_module(f"{name}.pages.egt"),
        )


def test_url_restores_engine_dates_and_precise_zoom(modules):
    egt, base, _ = modules

    async def run():
        state = egt.EgtState(_reflex_internal_init=True)
        gs = base.GlobalState(_reflex_internal_init=True)
        state.parent_state = rx.State(_reflex_internal_init=True)
        state.router = RouterData(url=ReflexURL(
            "http://localhost/egt?engine=888797&start=2025-01-01&end=2025-12-31"
            "&x_start=2025-02-01T12:34:56&x_end=2025-03-01T01:02:03"
        ))
        state.available_engines_labeled = [{"id": "888797", "label": "Engine"}]
        with patch.object(egt.EgtState, "get_state", AsyncMock(return_value=gs)), \
             patch.object(egt.EgtState, "_build_engine_list"), \
             patch.object(egt.EgtState, "_build_chart", AsyncMock()):
            _ = [update async for update in state.on_load()]
            assert state.selected_engine_id == "888797"
            assert (gs.start_date, gs.end_date) == ("2025-01-01", "2025-12-31")
            assert state.timeline_start == "2025-02-01T12:34:56"
            assert state.timeline_end == "2025-03-01T01:02:03"
            _ = [update async for update in state.set_start_date("2025-01-15")]
            assert not state.timeline_start
            assert gs.start_date == "2025-01-15"
            _ = [update async for update in state.set_start_date("2025-99-99")]
            assert gs.start_date == "2025-01-15"
    asyncio.run(run())


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("handler,args,field,expected", [
    ("toggle_param", ("IAI@TAKEOFF", True), "selected_params", ["IAI@TAKEOFF"]),
    ("toggle_param", ("EGTHDM@TAKEOFF", False), "selected_params", []),
    ("reset_params", (), "selected_params", ["EGTHDM@TAKEOFF", "DEGT@CRUISE", "GWFM@CRUISE"]),
    ("set_model_param", ("smoothing_window", "40"), "smoothing_window", 40),
    ("set_version", ("snapshot",), "selected_version", "snapshot"),
    ("set_start_date", ("2025-01-15",), "start_date", "2025-01-15"),
    ("set_end_date", ("2025-12-15",), "end_date", "2025-12-15"),
])
def test_filters_publish_values_before_build(modules, fails, handler, args, field, expected):
    egt, base, _ = modules

    async def run():
        state = egt.EgtState(_reflex_internal_init=True)
        gs = base.GlobalState(_reflex_internal_init=True)
        state.selected_engine_id = "888797"
        state.selected_params = ["EGTHDM@TAKEOFF"] if args == ("EGTHDM@TAKEOFF", False) else []
        state.label_mode = True
        build = AsyncMock(side_effect=RuntimeError("build failed") if fails else None)
        with patch.object(egt.EgtState, "get_state", AsyncMock(return_value=gs)), \
             patch.object(egt.EgtState, "_build_chart", build):
            event = getattr(state, handler)(*args)
            assert await anext(event) is None
            target = gs if field in ("start_date", "end_date") else state
            assert getattr(target, field) == expected
            assert state.is_computing
            if handler == "set_version":
                assert not state.label_mode
            build.assert_not_awaited()
            if fails:
                with pytest.raises(RuntimeError, match="build failed"):
                    _ = [update async for update in event]
            else:
                _ = [update async for update in event]
            build.assert_awaited_once()
            assert not state.is_computing

    asyncio.run(run())


def test_label_mode_only_updates_drag_mode(modules):
    egt, _, _ = modules
    state = egt.EgtState(_reflex_internal_init=True)
    state.selected_engine_id = "888797"
    state.chart_figure.add_scatter(x=[1, 2], y=[3, 4])
    with patch.object(egt.EgtState, "_build_chart", AsyncMock()) as build:
        for value, mode in ((True, "select"), (False, "zoom")):
            state.toggle_label_mode(value)
            assert state.label_mode == value
            assert state.chart_figure.layout.dragmode == mode
            assert list(state.chart_figure.data[0].y) == [3, 4]
        build.assert_not_awaited()


@pytest.mark.parametrize("xs", [
    [1646251935000, 1646269638000],
    ["2022-03-02T20:12:15", "2022-03-03T01:07:18"],
    [1646251935000, "2022-03-03T01:07:18"],
])
def test_selection_accepts_timestamp_milliseconds_and_date_strings(modules, xs):
    egt, _, _ = modules
    state = egt.EgtState(_reflex_internal_init=True)
    state.chart_figure.add_scattergl(x=xs, y=[1, 2], meta="reading")
    state.chart_figure.add_scatter(x=[0], y=[1], name="Maintenance")
    state.on_plot_selected([
        {"x": xs[1], "curveNumber": 0},
        {"x": xs[0], "curveNumber": 0},
        {"x": 0, "curveNumber": 1},
        {"x": "invalid", "curveNumber": 0},
    ])
    assert state.label_start == "2022-03-02T20:12:15"
    assert state.label_end == "2022-03-03T01:07:18"
    assert state.label_mode


def test_zoom_pan_reset_and_unrelated_relayout(modules):
    egt, base, _ = modules

    async def run():
        state = egt.EgtState(_reflex_internal_init=True)
        gs = base.GlobalState(_reflex_internal_init=True)
        with patch.object(egt.EgtState, "get_state", AsyncMock(return_value=gs)):
            bounds = ["2025-02-01 12:00:00", "2025-03-01 15:00:00"]
            await state.on_plot_relayout({"xaxis2.range[0]": bounds[0], "xaxis2.range[1]": bounds[1]})
            assert list(state.chart_figure.layout.xaxis.range) == bounds
            assert await state.on_plot_relayout({"xaxis.range": bounds}) is None
            await state.on_plot_relayout({"yaxis.range": [0, 100]})
            assert state.timeline_start == bounds[0]
            await state.on_plot_relayout({"xaxis.range": ["invalid", bounds[1]]})
            assert state.timeline_start == bounds[0]
            await state.on_plot_relayout({"xaxis.autorange": True})
            assert not state.timeline_start
            assert state.chart_figure.layout.xaxis.autorange
    asyncio.run(run())


def test_page_compiles_relayout_payload_and_multiline_labels(modules):
    _, _, page = modules
    from reflex.compiler.compiler import compile_page

    component = page.egt_page()
    rendered = str(component)
    assert "onRelayout" in rendered
    assert "pre-line" in rendered
    assert "on_plot_relayout" in rendered
    assert "Updating chart" in rendered
    assert "is_computing" in rendered
    assert "egtDateFigure(" in rendered
    _, compiled = compile_page("egt", component)
    assert "function egtDateFigure(figure)" in compiled
    assert "new WeakMap()" in compiled


@pytest.mark.parametrize("fails", [False, True])
def test_engine_selection_yields_loading_before_build_and_clears_it(modules, fails):
    egt, base, _ = modules

    async def run():
        state = egt.EgtState(_reflex_internal_init=True)
        gs = base.GlobalState(_reflex_internal_init=True)
        build = AsyncMock(side_effect=RuntimeError("build failed") if fails else None)
        with patch.object(egt.EgtState, "get_state", AsyncMock(return_value=gs)), \
             patch.object(egt.EgtState, "_build_chart", build):
            event = state.select_engine("888797")
            assert await anext(event) is None
            assert state.selected_engine_id == "888797"
            assert state.is_computing
            build.assert_not_awaited()
            if fails:
                with pytest.raises(RuntimeError, match="build failed"):
                    await anext(event)
            else:
                assert await anext(event) is not None  # URL synchronization
                with pytest.raises(StopAsyncIteration):
                    await anext(event)
            build.assert_awaited_once()
            assert not state.is_computing

    asyncio.run(run())


@pytest.mark.parametrize("timezone", ["UTC", "Europe/Moscow", "America/New_York"])
def test_date_transport_decoder_is_timezone_independent(modules, timezone):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chart date decoder test")
    egt, _, page = modules
    from reflex.utils import serializers

    fig = egt.go.Figure(egt.go.Scattergl(
        x=egt.egt_params.plotly_timestamps([
            "2022-03-02 20:12:15", None, "2025-10-08 16:47:34.123456",
        ]),
        y=egt.np.array([1.2345678901234567, egt.np.nan, 3.5]),
    ))
    wire = json.dumps(serializers.serialize(fig))
    code = page._DATE_FIGURE_JS + "\nconst original = " + wire + ";\n" + """
const decoded = egtDateFigure(original);
console.log(JSON.stringify({
    x: decoded.data[0].x,
    cached: egtDateFigure(original) === decoded,
    originalUnchanged: original.data[0].x.dtype === 'f8',
    yUnchanged: decoded.data[0].y === original.data[0].y,
    newFigureDecoded: egtDateFigure({...original}) !== decoded,
}));
"""
    result = subprocess.run(
        [node, "-e", code], env={**os.environ, "TZ": timezone},
        capture_output=True, text=True, check=True,
    )
    decoded = json.loads(result.stdout)
    assert decoded["x"][0] == "2022-03-02T20:12:15.000"
    assert decoded["x"][1] is None
    assert abs(egt.pd.Timestamp(decoded["x"][2]) - egt.pd.Timestamp(
        "2025-10-08 16:47:34.123456"
    )) < egt.pd.Timedelta(microseconds=1)
    assert all(decoded[key] for key in (
        "cached", "originalUnchanged", "yUnchanged", "newFigureDecoded",
    ))
