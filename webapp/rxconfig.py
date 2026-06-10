import os

import reflex as rx

# Public URL the browser uses to reach the backend (WebSocket /_event etc.).
# In dev this stays at the Reflex default (http://localhost:8000). On the
# server, set REFLEX_API_URL=https://ecm.korzh.tech so the compiled frontend
# talks to the same host the page came from.
_API_URL = os.getenv("REFLEX_API_URL")
_DEPLOY_URL = os.getenv("REFLEX_DEPLOY_URL")

_kwargs = {
    "app_name": "webapp",
    "plugins": [
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(theme=rx.theme(accent_color="blue", radius="medium")),
    ],
}
if _API_URL:
    _kwargs["api_url"] = _API_URL
if _DEPLOY_URL:
    _kwargs["deploy_url"] = _DEPLOY_URL

config = rx.Config(**_kwargs)