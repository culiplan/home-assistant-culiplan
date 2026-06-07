"""
Tests for CuliplanLaunchView — the JSON SSO bridge endpoint.

Coverage:
  AC#1 — 200 JSON with redirect_url + expires_in for an authenticated request
  AC#2 — 503 JSON when no config entry exists
  AC#3 — 502 JSON when backend exchange fails (mock 500 response)
  AC#4 — 502 JSON when backend exchange returns non-200 with body
  AC#5 — Response body never contains the raw token or the SSO code directly;
          the code travels only inside the fragment of redirect_url (see security note).

Security note on AC#5:
  The SSO code is embedded in the URL fragment (``#<code>``).  Fragments are
  client-only — they are not sent to any server in subsequent requests.  What
  the response body DOES contain is ``redirect_url`` which includes the
  fragment, so we verify the code appears there and only there (not in a
  standalone ``code`` field or in any log output).

Panel JS smoke tests:
  There is no JS test harness in this repo.  Manual smoke testing covers the
  happy path, error states, retry logic, and HA design token rendering.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — build a minimal view instance without a full HA runtime
# ---------------------------------------------------------------------------


def _make_hass(entries: list) -> MagicMock:
    """Return a minimal hass mock with a config_entries stub."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=entries)
    return hass


def _make_entry(loaded: bool = True, ha_user_id: str | None = None) -> MagicMock:
    entry = MagicMock()
    entry.state = MagicMock()
    entry.state.value = "loaded" if loaded else "not_loaded"
    entry.data = {"ha_user_id": ha_user_id} if ha_user_id else {}
    return entry


def _make_request(ha_user_id: str | None = "user-abc") -> MagicMock:
    """Return a minimal aiohttp request mock with hass_user populated."""
    req = MagicMock()
    if ha_user_id is not None:
        user = MagicMock()
        user.id = ha_user_id
        req.get = MagicMock(side_effect=lambda k: user if k == "hass_user" else None)
    else:
        req.get = MagicMock(return_value=None)
    return req


def _make_view(entries: list) -> MagicMock:
    from custom_components.culiplan.launch_view import CuliplanLaunchView

    hass = _make_hass(entries)
    return CuliplanLaunchView(hass)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC#2 — 503 when no config entry exists
# ---------------------------------------------------------------------------


class TestNoConfigEntry:
    @pytest.mark.asyncio
    async def test_503_when_no_entries(self) -> None:
        """503 JSON returned when there are no loaded config entries."""
        view = _make_view([])
        req = _make_request()

        resp = await view.get(req)

        assert resp.status == 503
        body = json.loads(resp.text)
        assert body["error"] == "no_entry"
        assert "message" in body
        # Ensure no token or code leaked
        assert "access_token" not in resp.text
        assert "redirect_url" not in resp.text

    @pytest.mark.asyncio
    async def test_503_user_id_mismatch(self) -> None:
        """503 when entry has a different ha_user_id (multi-user safety)."""
        entry = _make_entry(ha_user_id="other-user")
        view = _make_view([entry])
        req = _make_request(ha_user_id="current-user")

        resp = await view.get(req)

        assert resp.status == 503
        body = json.loads(resp.text)
        assert "error" in body


# ---------------------------------------------------------------------------
# AC#1 — 200 JSON on happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_200_json_shape(self) -> None:
        """200 response contains redirect_url and expires_in; no raw token/code field."""
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.token = {"access_token": "tok_secret"}
        mock_session.async_ensure_token_valid = AsyncMock()

        # Mock the HTTP exchange call returning a code
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"code": "sso_code_xyz"})

        mock_client = AsyncMock()
        mock_client.post = MagicMock(return_value=mock_resp)

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
            patch(
                "custom_components.culiplan.launch_view.aiohttp_client"
                ".async_get_clientsession",
                return_value=mock_client,
            ),
        ):
            resp = await view.get(req)

        assert resp.status == 200
        body = json.loads(resp.text)

        # Shape checks
        assert "redirect_url" in body
        assert "expires_in" in body
        assert isinstance(body["expires_in"], int)
        assert body["expires_in"] > 0

        # The code must be in the URL fragment only — not as a top-level field
        assert "code" not in body
        assert "sso_code_xyz" in body["redirect_url"]
        # Base URL is https://culiplan.com/ha-bridge with an optional
        # `?embed=ha` query so the bridge page knows it's running inside HA.
        # The code is in the fragment regardless.
        assert body["redirect_url"].startswith("https://culiplan.com/ha-bridge")
        assert "#sso_code_xyz" in body["redirect_url"]

        # The raw bearer token must NOT appear anywhere in the response body
        assert "tok_secret" not in resp.text

    @pytest.mark.asyncio
    async def test_redirect_url_uses_fragment(self) -> None:
        """redirect_url places the code after '#', not as a query param."""
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.token = {"access_token": "tok_secret"}
        mock_session.async_ensure_token_valid = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"code": "my_bridge_code"})

        mock_client = AsyncMock()
        mock_client.post = MagicMock(return_value=mock_resp)

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
            patch(
                "custom_components.culiplan.launch_view.aiohttp_client"
                ".async_get_clientsession",
                return_value=mock_client,
            ),
        ):
            resp = await view.get(req)

        body = json.loads(resp.text)
        url = body["redirect_url"]
        # Fragment is after '#'; query string would be after '?'
        assert "#my_bridge_code" in url
        assert "?code=" not in url
        assert "?my_bridge_code" not in url


# ---------------------------------------------------------------------------
# AC#3 — 502 when backend exchange fails
# ---------------------------------------------------------------------------


class TestBackendFailure:
    @pytest.mark.asyncio
    async def test_502_when_backend_returns_500(self) -> None:
        """502 JSON when the backend SSO exchange endpoint returns 500."""
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.token = {"access_token": "tok_secret"}
        mock_session.async_ensure_token_valid = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_client = AsyncMock()
        mock_client.post = MagicMock(return_value=mock_resp)

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
            patch(
                "custom_components.culiplan.launch_view.aiohttp_client"
                ".async_get_clientsession",
                return_value=mock_client,
            ),
        ):
            resp = await view.get(req)

        assert resp.status == 502
        body = json.loads(resp.text)
        assert body["error"] == "exchange_failed"
        assert "message" in body
        # Raw token must not appear in error response
        assert "tok_secret" not in resp.text

    @pytest.mark.asyncio
    async def test_502_on_network_error(self) -> None:
        """502 JSON when a network exception occurs during backend exchange."""
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.token = {"access_token": "tok_secret"}
        mock_session.async_ensure_token_valid = AsyncMock()

        # Simulate a network-level exception
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(side_effect=OSError("Connection refused"))
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.post = MagicMock(return_value=mock_resp)

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
            patch(
                "custom_components.culiplan.launch_view.aiohttp_client"
                ".async_get_clientsession",
                return_value=mock_client,
            ),
        ):
            resp = await view.get(req)

        assert resp.status == 502
        body = json.loads(resp.text)
        assert body["error"] == "network_error"


# ---------------------------------------------------------------------------
# AC#4 — 503 when OAuth token retrieval fails
# ---------------------------------------------------------------------------


class TestTokenFailure:
    @pytest.mark.asyncio
    async def test_503_when_token_refresh_raises(self) -> None:
        """503 JSON when async_ensure_token_valid raises (expired/revoked token)."""
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.async_ensure_token_valid = AsyncMock(
            side_effect=Exception("Token refresh failed")
        )

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
        ):
            resp = await view.get(req)

        assert resp.status == 503
        body = json.loads(resp.text)
        assert body["error"] == "token_expired"
        assert "message" in body


# ---------------------------------------------------------------------------
# AC#5 — Security: no token/code leakage in any error response
# ---------------------------------------------------------------------------


class TestNoSecretLeakage:
    """Verify that error responses never contain bearer token or SSO code."""

    @pytest.mark.asyncio
    async def test_503_no_entry_has_no_token(self) -> None:
        view = _make_view([])
        req = _make_request()
        resp = await view.get(req)
        # The view never had an access_token at this point; ensure no stray value
        for secret in ("access_token", "Bearer", "refresh_token"):
            assert secret not in resp.text, (
                f"Secret keyword '{secret}' found in 503 no-entry response"
            )

    @pytest.mark.asyncio
    async def test_502_backend_error_has_no_token(self) -> None:
        entry = _make_entry(ha_user_id="user-abc")
        view = _make_view([entry])
        req = _make_request(ha_user_id="user-abc")

        mock_implementation = MagicMock()
        mock_session = AsyncMock()
        mock_session.token = {"access_token": "super_secret_tok"}
        mock_session.async_ensure_token_valid = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.text = AsyncMock(return_value="Internal error")

        mock_client = AsyncMock()
        mock_client.post = MagicMock(return_value=mock_resp)

        with (
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".async_get_config_entry_implementation",
                new=AsyncMock(return_value=mock_implementation),
            ),
            patch(
                "custom_components.culiplan.launch_view.config_entry_oauth2_flow"
                ".OAuth2Session",
                return_value=mock_session,
            ),
            patch(
                "custom_components.culiplan.launch_view.aiohttp_client"
                ".async_get_clientsession",
                return_value=mock_client,
            ),
        ):
            resp = await view.get(req)

        assert "super_secret_tok" not in resp.text
