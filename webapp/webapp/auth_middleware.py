"""Protect dashboard events, including direct WebSocket calls and setters."""

import reflex as rx
from reflex.middleware.hydrate_middleware import HydrateMiddleware
from reflex.state import OnLoadInternalState, StateUpdate, UpdateVarsInternalState
from reflex_base.event import Event, get_hydrate_event

from .state.auth import AuthState


class AuthMiddleware(rx.Middleware):
    async def preprocess(self, app, state, event):
        # Hydration precedes restoration of localStorage. Return only login and
        # framework state so reconnecting cannot expose an old dashboard snapshot.
        root = state._get_root_state()
        if event.name == get_hydrate_event(rx.State):
            update = await HydrateMiddleware().preprocess(app, root, event)
            delta = {
                name: values for name, values in update.delta.items()
                if name in {rx.State.get_full_name(), AuthState.get_full_name()}
            }
            return StateUpdate(delta=delta)

        # These exact events bootstrap the browser and restore client storage.
        # update_vars_internal only writes declared client-storage vars; a
        # supplied token is still verified on every protected event below.
        public_events = {
            f"{UpdateVarsInternalState.get_full_name()}.update_vars_internal",
            f"{OnLoadInternalState.get_full_name()}.on_load_internal",
            f"{rx.State.get_full_name()}.set_is_hydrated",
            *(f"{AuthState.get_full_name()}.{name}" for name in (
                "login", "logout", "require_auth", "redirect_if_authenticated",
            )),
        }
        if event.name in public_events:
            return None
        auth = await root.get_state(AuthState)
        if auth.authenticated:
            return None
        return StateUpdate(events=Event.from_event_type(rx.redirect("/login")))
