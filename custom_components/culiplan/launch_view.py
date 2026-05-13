"""
Launch endpoint that bridges the Home Assistant user into the Culiplan web
app inside an iframe panel.

When the user clicks the "Culiplan" entry in the HA sidebar, HA navigates the
iframe to ``/api/culiplan/launch`` (this view). The view:

  1. Verifies the request comes from an authenticated HA user (HA's standard
     view auth — same mechanism the rest of HA's REST API uses).
  2. Resolves the user's Culiplan config entry and obtains a *fresh* OAuth
     access token via the OAuth2Session helper. ``async_ensure_token_valid``
     refreshes the token if it expired.
  3. POSTs that bearer token to ``/api/oauth/sso/exchange`` on the Culiplan
     backend, which returns a one-time, IP-bound, 60-second bridge code.
  4. 302-redirects the browser to ``https://culiplan.com/ha-bridge#<code>``.
     The hash fragment is never sent to a server, never logged in our access
     logs, and is scrubbed client-side by the bridge page before any
     analytics flush.

Failure modes:
- No config entry / no token       → 503 with explanatory message.
- Backend rejects exchange         → 502 (bad gateway).
- Network error talking to backend → 502.

We never log the code, the access token, or anything derived from them.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .const import BASE_URL, DOMAIN, WEB_URL

_LOGGER = logging.getLogger(__name__)


class CuliplanLaunchView(HomeAssistantView):
    """HA HTTP view that issues a one-time SSO code and redirects."""

    url = "/api/culiplan/launch"
    name = "api:culiplan:launch"
    # Explicit — HomeAssistantView defaults to True, but we state it here
    # because the auth check is load-bearing for the SSO bridge.
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.StreamResponse:
        # `request['hass_user']` is populated by HA's auth middleware when
        # ``requires_auth = True``. We use it to pick the right config entry
        # on multi-user HA installs.
        ha_user = request.get("hass_user")
        ha_user_id = getattr(ha_user, "id", None) if ha_user is not None else None

        entry = self._entry_for_user(ha_user_id)
        if entry is None:
            _LOGGER.warning(
                "[culiplan][launch] No Culiplan config entry matched ha_user_id=%s",
                ha_user_id,
            )
            return web.Response(
                status=403,
                text="Your Home Assistant user has not linked a Culiplan account. "
                "Add the Culiplan integration in Settings → Devices & Services.",
                content_type="text/plain",
            )

        try:
            implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
                self._hass, entry
            )
            session = config_entry_oauth2_flow.OAuth2Session(self._hass, entry, implementation)
            await session.async_ensure_token_valid()
            access_token: str = session.token["access_token"]
        except Exception as err:  # noqa: BLE001 — token problems must not surface raw stack
            _LOGGER.warning("[culiplan][launch] Could not obtain access token: %s", err)
            return web.Response(
                status=503,
                text="Culiplan session has expired. Re-link the integration in "
                "Settings → Devices & Services.",
                content_type="text/plain",
            )

        try:
            client = aiohttp_client.async_get_clientsession(self._hass)
            async with client.post(
                f"{BASE_URL}/api/oauth/sso/exchange",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.warning(
                        "[culiplan][launch] Exchange failed: status=%s body=%s",
                        resp.status,
                        body[:200],
                    )
                    return web.Response(
                        status=502,
                        text="Culiplan SSO bridge is unavailable. Please try again "
                        "in a moment.",
                        content_type="text/plain",
                    )
                payload: dict[str, Any] = await resp.json()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("[culiplan][launch] Network error during exchange: %s", err)
            return web.Response(
                status=502,
                text="Could not reach Culiplan. Check your internet connection.",
                content_type="text/plain",
            )

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            _LOGGER.warning("[culiplan][launch] Exchange response missing code.")
            return web.Response(
                status=502,
                text="Culiplan SSO bridge returned an invalid response.",
                content_type="text/plain",
            )

        # Hash fragment is client-only. We deliberately do NOT pass the code
        # via query string or response body to keep it out of HA access logs.
        return web.Response(
            status=302,
            headers={"Location": f"{WEB_URL}/ha-bridge#{code}"},
        )

    def _entry_for_user(self, ha_user_id: str | None) -> ConfigEntry | None:
        """Pick the loaded Culiplan entry that belongs to this HA user.

        Multi-user safety: each entry is tagged with the HA user id of
        whoever ran the OAuth flow (see ``config_flow.async_oauth_create_entry``).
        Entries created before that tagging landed have no ``ha_user_id`` —
        we fall back to the legacy single-entry-for-everyone behaviour for
        those, with a warning, so existing installs don't break on upgrade.
        """
        loaded = [
            e
            for e in self._hass.config_entries.async_entries(DOMAIN)
            if e.state.value == "loaded"
        ]
        if not loaded:
            return None

        if ha_user_id:
            for e in loaded:
                if e.data.get("ha_user_id") == ha_user_id:
                    return e
            # User-bound match failed. If any entry HAS a ha_user_id tag,
            # treat this as a "wrong user" 403 — never silently bridge.
            if any(e.data.get("ha_user_id") for e in loaded):
                return None

        # No user binding available (legacy entry pre-tagging, or anonymous
        # caller). Use the first entry and log so multi-user installs can
        # spot the misconfiguration.
        if len(loaded) > 1:
            _LOGGER.warning(
                "[culiplan][launch] %d Culiplan entries are loaded and none "
                "carry an ha_user_id tag; defaulting to the first. Re-link "
                "the integration to enable per-user routing.",
                len(loaded),
            )
        return loaded[0]
