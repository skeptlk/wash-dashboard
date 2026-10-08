"""EGT URL restoration and Plotly viewport events, without dataset downloads."""
import asyncio
import importlib
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
    rendered = str(page.egt_page())
    assert "onRelayout" in rendered
    assert "pre-line" in rendered
    assert "on_plot_relayout" in rendered
    assert "Updating chart" in rendered
    assert "is_computing" in rendered


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
