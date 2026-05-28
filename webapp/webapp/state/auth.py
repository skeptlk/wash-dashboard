"""Authentication state — single shared password via APP_PASSWORD env var."""

from __future__ import annotations

import os

import reflex as rx

_PASSWORD = os.environ.get("APP_PASSWORD", "ecm")


class AuthState(rx.State):
    authenticated: bool = False
    error: str = ""

    @rx.event
    def login(self, form_data: dict):
        if form_data.get("password", "") == _PASSWORD:
            self.authenticated = True
            self.error = ""
            return rx.redirect("/")
        self.error = "Incorrect password"

    @rx.event
    def logout(self):
        self.authenticated = False
        return rx.redirect("/login")

    @rx.event
    def require_auth(self):
        if not self.authenticated:
            return rx.redirect("/login")

    @rx.event
    def redirect_if_authenticated(self):
        if self.authenticated:
            return rx.redirect("/")
