"""
Launch endpoint that bridges the Home Assistant user into the Culiplan web
app inside the custom Lit panel.

When the custom panel's JS fetches ``/api/culiplan/launch`` (this view) it
sends the HA bearer token in the ``Authorization`` header.  The view:

  1. Verifies the request comes from an authenticated HA user (HA's standard
     view auth — same mechanism the rest of HA's REST API uses).
  2. Resolves the user's Culiplan config entry and obtains a *fresh* OAuth
     access token via the OAuth2Session helper. ``async_ensure_token_valid``
     refreshes the token if it expired.
  3. Generates a one-time ``verifier`` and POSTs that bearer token plus
     ``code_challenge = base64url(SHA-256(verifier))`` to
     ``/api/oauth/sso/exchange`` on the Culiplan backend, which returns a
     one-time, 60-second bridge code bound to that challenge.
  4. Returns JSON: ``{"redirect_url": "https://culiplan.com/ha-bridge?...#<code>",
     "expires_in": 60, "verifier": "<verifier>"}``

     The panel posts the verifier to the Culiplan iframe (postMessage,
     Culiplan origin only), which redeems code + verifier. The verifier never
     appears in a URL, so a leaked code is useless on its own. This replaces
     binding the code to the network, which failed whenever the browser and
     the HA box reach the internet from different addresses (remote access,
     iCloud Private Relay, VPNs, company proxies).

     The code is embedded in the fragment (``#``), so it is never sent to a
     server, never appears in HA access logs, and is scrubbed client-side by
     the bridge page before any analytics flush.

Failure modes are returned as JSON with a short ``error`` code and a
``message`` suitable for display in the panel error card:

- 503 — no config entry / no token.
- 502 — backend exchange failed or network error.

We NEVER log the SSO code, the verifier, the bearer token, or the resolved redirect_url —
all three carry the secret code.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from typing import Any

from aiohttp import ClientTimeout, web
from homeassistant.components.http import HomeAssistantView  # type: ignore[attr-defined]
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .const import BASE_URL, DOMAIN, WEB_URL

_LOGGER = logging.getLogger(__name__)

_SSO_CODE_EXPIRES_IN = 60  # seconds — must match backend value

# How long a launch waits for the user's entry to finish (re)loading before
# answering ``not_ready``. A reload takes a second or two; HA startup longer.
_ENTRY_READY_TIMEOUT = 15.0
_ENTRY_READY_POLL = 0.25

# States waiting won't fix (needs reauth, migration failed, unload failed).
_ENTRY_FAILED_STATES = frozenset(
    {
        ConfigEntryState.SETUP_ERROR,
        ConfigEntryState.MIGRATION_ERROR,
        ConfigEntryState.FAILED_UNLOAD,
    }
)


def _new_verifier_pair() -> tuple[str, str]:
    """Return ``(verifier, S256 challenge)`` as in RFC 7636."""
    verifier = secrets.token_urlsafe(32)  # 43 chars, base64url
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class CuliplanLaunchView(HomeAssistantView):
    """HA HTTP view that issues a one-time SSO code and returns the redirect URL as JSON."""

    url = "/api/culiplan/launch"
    name = "api:culiplan:launch"
    # Explicit — HomeAssistantView defaults to True, but we state it here
    # because the auth check is load-bearing for the SSO bridge.
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        # ``request['hass_user']`` is populated by HA's auth middleware when
        # ``requires_auth = True``. We use it to pick the right config entry
        # on multi-user HA installs.
        ha_user = request.get("hass_user")
        ha_user_id = getattr(ha_user, "id", None) if ha_user is not None else None

        entry = self._entry_for_user(ha_user_id)
        if entry is not None and entry.state in _ENTRY_FAILED_STATES:
            return web.Response(
                status=503,
                content_type="application/json",
                text='{"error": "entry_error", "message": "Culiplan is not running in Home Assistant. Open Settings → Devices & Services → Culiplan to fix it."}',
            )
        if entry is not None and entry.state is not ConfigEntryState.LOADED:
            # The user's entry exists but is starting or reloading (HA startup,
            # options change, integration update). Wait for it rather than
            # telling a linked user to link Culiplan.
            if not await self._async_wait_until_loaded(entry):
                _LOGGER.info(
                    "[culiplan][launch] Entry not ready after %.0fs (state=%s)",
                    _ENTRY_READY_TIMEOUT,
                    entry.state,
                )
                return web.Response(
                    status=503,
                    content_type="application/json",
                    text='{"error": "not_ready", "message": "Culiplan is still starting in Home Assistant. Try again in a moment."}',
                )
        if entry is None:
            _LOGGER.warning(
                "[culiplan][launch] No Culiplan config entry matched ha_user_id=%s",
                ha_user_id,
            )
            return web.Response(
                status=503,
                content_type="application/json",
                text='{"error": "no_entry", "message": "Your Home Assistant user has not linked a Culiplan account. Add the Culiplan integration in Settings → Devices & Services."}',
            )

        try:
            implementation = (
                await config_entry_oauth2_flow.async_get_config_entry_implementation(
                    self._hass, entry
                )
            )
            session = config_entry_oauth2_flow.OAuth2Session(
                self._hass, entry, implementation
            )
            await session.async_ensure_token_valid()
            access_token: str = session.token["access_token"]
        except Exception as err:  # noqa: BLE001 — token problems must not surface raw stack
            _LOGGER.warning("[culiplan][launch] Could not obtain access token: %s", err)
            return web.Response(
                status=503,
                content_type="application/json",
                text='{"error": "token_expired", "message": "Culiplan session has expired. Re-link the integration in Settings → Devices & Services."}',
            )

        # Verifier binding only when the panel asks for it (0.16.3+ panels send
        # ?binding=verifier). After an integration update, a browser tab that
        # stays open keeps running the previous panel script (a custom element
        # can't be redefined); that panel never hands over a verifier, so it
        # must keep getting a network-bound code.
        use_verifier = request.query.get("binding") == "verifier"
        verifier, challenge = _new_verifier_pair() if use_verifier else (None, None)

        try:
            client = aiohttp_client.async_get_clientsession(self._hass)
            async with client.post(
                f"{BASE_URL}/api/oauth/sso/exchange",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"code_challenge": challenge} if challenge else None,
                timeout=ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.warning(
                        "[culiplan][launch] Exchange failed: status=%s body=<redacted len=%d>",
                        resp.status,
                        len(body),
                    )
                    # Distinguish *why* the exchange failed so the panel can pick
                    # the right recovery. 401/403 = the backend rejected our
                    # (already-refreshed) token; the bridge can't succeed, but the
                    # user can still sign in directly, so the panel falls back to
                    # the in-app login. Any other status is a backend-side problem
                    # (5xx, Redis down) where retrying shortly is the right move.
                    if resp.status in (401, 403):
                        return web.Response(
                            status=502,
                            content_type="application/json",
                            text='{"error": "auth_rejected", "message": "Your Culiplan sign-in needs to be renewed. Please sign in again."}',
                        )
                    return web.Response(
                        status=502,
                        content_type="application/json",
                        text='{"error": "backend_unavailable", "message": "Culiplan SSO bridge is unavailable. Please try again in a moment."}',
                    )
                payload: dict[str, Any] = await resp.json()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("[culiplan][launch] Network error during exchange: %s", err)
            return web.Response(
                status=502,
                content_type="application/json",
                text='{"error": "network_error", "message": "Could not reach Culiplan. Check your internet connection."}',
            )

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            _LOGGER.warning("[culiplan][launch] Exchange response missing code.")
            return web.Response(
                status=502,
                content_type="application/json",
                text='{"error": "invalid_response", "message": "Culiplan SSO bridge returned an invalid response."}',
            )

        # The code is placed in the fragment (#) so it is never sent to a
        # server and never appears in access logs.  We do NOT log redirect_url
        # because the fragment contains the secret code.
        #
        # ?embed=ha is a server-readable hint to the web app that it is being
        # rendered inside the HA iframe panel.  The front-end uses it (plus
        # window.self !== window.top) to enable "embed mode" — hiding its own
        # sidebar, logo, greeting, and account block to avoid duplicating
        # chrome that HA's own UI already shows.  Not sensitive; safe in the
        # query string.  The fragment stays the LAST component so the
        # one-time code remains in the URL hash (never sent to a server).
        #
        # ?pkce=1 tells the bridge page to wait for the verifier from the
        # panel before redeeming; without it (older panels) it redeems at once.
        # The verifier goes back in the JSON body only, never in the URL, and
        # like the code it is never logged.
        import json

        launch: dict[str, Any]
        if verifier is None:
            launch = {
                "redirect_url": f"{WEB_URL}/ha-bridge?embed=ha#{code}",
                "expires_in": _SSO_CODE_EXPIRES_IN,
            }
        else:
            launch = {
                "redirect_url": f"{WEB_URL}/ha-bridge?embed=ha&pkce=1#{code}",
                "expires_in": _SSO_CODE_EXPIRES_IN,
                "verifier": verifier,
            }
        return web.Response(
            status=200,
            content_type="application/json",
            text=json.dumps(launch),
        )

    async def _async_wait_until_loaded(self, entry: ConfigEntry) -> bool:
        """Poll until *entry* is loaded, up to ``_ENTRY_READY_TIMEOUT``."""
        deadline = time.monotonic() + _ENTRY_READY_TIMEOUT
        while entry.state is not ConfigEntryState.LOADED:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(_ENTRY_READY_POLL)
        return True

    def _entry_for_user(self, ha_user_id: str | None) -> ConfigEntry | None:
        """Pick the enabled Culiplan entry that belongs to this HA user.

        Any state counts: the caller waits for a starting or reloading entry
        instead of reporting that the user has no Culiplan account linked.

        Multi-user safety: each entry is tagged with the HA user id of
        whoever ran the OAuth flow (see ``config_flow.async_oauth_create_entry``).
        Entries created before that tagging landed have no ``ha_user_id`` —
        we fall back to the legacy single-entry-for-everyone behaviour for
        those, with a warning, so existing installs don't break on upgrade.
        """
        candidates = [
            e
            for e in self._hass.config_entries.async_entries(DOMAIN)
            if e.disabled_by is None
        ]
        if not candidates:
            return None

        if ha_user_id:
            for e in candidates:
                if e.data.get("ha_user_id") == ha_user_id:
                    return e
            # User-bound match failed. If any entry HAS a ha_user_id tag,
            # treat this as a "wrong user" 503 — never silently bridge.
            if any(e.data.get("ha_user_id") for e in candidates):
                return None

        # No user binding available (legacy entry pre-tagging, or anonymous
        # caller). Use the first entry and log so multi-user installs can
        # spot the misconfiguration.
        if len(candidates) > 1:
            _LOGGER.warning(
                "[culiplan][launch] %d Culiplan entries are set up and none "
                "carry an ha_user_id tag; defaulting to the first. Re-link "
                "the integration to enable per-user routing.",
                len(candidates),
            )
        return candidates[0]
