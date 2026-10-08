"""Authentication state — single shared password via APP_PASSWORD env var."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

import reflex as rx

_PASSWORD = os.environ.get("APP_PASSWORD", "ecm")


def _sign(nonce: str) -> str:
    return hmac.new(
        _PASSWORD.encode(), f"enginewash-browser-v1:{nonce}".encode(), hashlib.sha256
    ).hexdigest()


def _new_token() -> str:
    nonce = secrets.token_hex(32)
    return f"{nonce}.{_sign(nonce)}"


def _valid_token(token: str) -> bool:
    if not isinstance(token, str) or len(token) != 129:
        return False
    nonce, separator, signature = token.partition(".")
    return bool(separator) and hmac.compare_digest(
        signature.encode(), _sign(nonce).encode()
    )


class AuthState(rx.State):
    # No expiry: independent of Reflex's short-lived server session. Changing
    # APP_PASSWORD invalidates every saved token, including after a restart.
    auth_token: str = rx.LocalStorage("", name="ew_auth_token", sync=True)
    error: str = ""

    @rx.var(cache=False)
    def authenticated(self) -> bool:
        return _valid_token(self.auth_token)

    @rx.event
    def login(self, form_data: dict):
        password = form_data.get("password", "")
        if isinstance(password, str) and hmac.compare_digest(password.encode(), _PASSWORD.encode()):
            self.auth_token = _new_token()
            self.error = ""
            return rx.redirect("/")
        self.error = "Incorrect password"

    @rx.event
    def logout(self):
        self.auth_token = ""
        self.error = ""
        return rx.redirect("/login")

    @rx.event
    def require_auth(self):
        if not self.authenticated:
            return rx.redirect("/login")

    @rx.event
    def redirect_if_authenticated(self):
        if self.authenticated:
            return rx.redirect("/")
