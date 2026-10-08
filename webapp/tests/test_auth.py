"""Persistent shared login and backend event authorization, without datasets."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import reflex as rx
from reflex.state import OnLoadInternalState, StateUpdate, UpdateVarsInternalState
from reflex_base.event import Event, get_hydrate_event

from webapp import auth_middleware
from webapp.state import auth


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(auth, "_PASSWORD", "test-password")
    return auth.AuthState(_reflex_internal_init=True)


def test_login_survives_new_server_session_and_password_rotation(state, monkeypatch):
    state.login({"password": "wrong"})
    assert not state.authenticated
    assert state.error == "Incorrect password"
    state.login({"password": "test-password"})
    saved_token = state.auth_token
    assert state.authenticated
    assert "test-password" not in saved_token

    fresh = auth.AuthState(_reflex_internal_init=True)
    fresh.auth_token = saved_token  # Browser restores localStorage after restart.
    assert fresh.authenticated
    assert fresh.require_auth() is None
    assert fresh.redirect_if_authenticated() is not None
    monkeypatch.setattr(auth, "_PASSWORD", "rotated-password")
    assert not fresh.authenticated
    assert fresh.require_auth() is not None


def test_logout_clears_persistent_login(state):
    state.login({"password": "test-password"})
    state.logout()
    assert state.auth_token == ""
    assert not state.authenticated


@pytest.mark.parametrize("token", ["", "true", "ecm", "x" * 129, "x" * 64 + "." + "é" * 64, None])
def test_forged_and_malformed_tokens_are_rejected(token):
    assert not auth._valid_token(token)


def test_tampered_token_is_rejected(state):
    state.login({"password": "test-password"})
    nonce, signature = state.auth_token.split(".")
    assert not auth._valid_token(nonce + "." + ("0" if signature[0] != "0" else "1") + signature[1:])


@pytest.mark.parametrize("name", [
    "webapp___state___egt____egt_state.apply_label",
    "webapp___state___egt____egt_state.delete_label",
    "webapp___state___egt____egt_state.export_dataset",
    "webapp___state___degradation____degradation_state.recompute",
    "webapp___state___analysis____analysis_state.on_load",
    "webapp___state___schedule____schedule_state.on_load",
    "webapp___state___egt____egt_state.setvar",
])
def test_direct_dashboard_events_require_valid_login(state, name):
    async def run():
        root = SimpleNamespace(get_state=AsyncMock(return_value=state))
        root._get_root_state = lambda: root
        guard = auth_middleware.AuthMiddleware()
        event = Event(name=f"{rx.State.get_full_name()}.{name}")
        denied = await guard.preprocess(None, root, event)
        assert denied.delta == {}
        assert denied.events[0].payload["path"] == "/login"
        state.auth_token = "forged"
        assert await guard.preprocess(None, root, event) is not None
        state.login({"password": "test-password"})
        assert await guard.preprocess(None, root, event) is None
        state.logout()
        assert await guard.preprocess(None, root, event) is not None
    asyncio.run(run())


def test_bootstrap_is_allowed_but_generic_auth_setter_is_not(state):
    async def run():
        root = SimpleNamespace(get_state=AsyncMock(return_value=state))
        root._get_root_state = lambda: root
        guard = auth_middleware.AuthMiddleware()
        for cls, handler in [
            (UpdateVarsInternalState, "update_vars_internal"),
            (OnLoadInternalState, "on_load_internal"),
            (rx.State, "set_is_hydrated"),
            (auth.AuthState, "login"),
            (auth.AuthState, "logout"),
            (auth.AuthState, "require_auth"),
            (auth.AuthState, "redirect_if_authenticated"),
        ]:
            assert await guard.preprocess(None, root, Event(name=f"{cls.get_full_name()}.{handler}")) is None
        for cls in [rx.State, auth.AuthState, UpdateVarsInternalState]:
            assert await guard.preprocess(None, root, Event(name=f"{cls.get_full_name()}.setvar")) is not None
    asyncio.run(run())


def test_hydration_does_not_return_previous_dashboard_data(state, monkeypatch):
    async def run():
        root_name = rx.State.get_full_name()
        auth_name = auth.AuthState.get_full_name()
        delta = {
            root_name: {"is_hydrated": False},
            auth_name: {"auth_token": "", "authenticated": False},
            f"{root_name}.dashboard": {"rows": ["private data"]},
        }
        hydrate = AsyncMock(return_value=StateUpdate(delta=delta))
        monkeypatch.setattr(auth_middleware.HydrateMiddleware, "preprocess", hydrate)
        root = SimpleNamespace()
        root._get_root_state = lambda: root
        update = await auth_middleware.AuthMiddleware().preprocess(
            None, root, Event(name=get_hydrate_event(rx.State)),
        )
        assert set(update.delta) == {root_name, auth_name}
        hydrate.assert_awaited_once()
    asyncio.run(run())
