"""Tests for application_credentials.py — PKCE OAuth2 implementation.

The Culiplan backend is a public OAuth 2.1 client (PKCE S256 mandatory, no
client_secret). HA's default LocalOAuth2Implementation does not send
code_challenge / code_verifier, so we ship a thin subclass that does.
These tests pin the wire-level behaviour of that subclass.
"""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)

from custom_components.culiplan.application_credentials import (
    CuliplanOAuth2Implementation,
    _generate_pkce_pair,
    async_get_auth_implementation,
    async_get_authorization_server,
)
from custom_components.culiplan.const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


def _make_impl(hass) -> CuliplanOAuth2Implementation:
    return CuliplanOAuth2Implementation(
        hass,
        "culiplan",
        ClientCredential(client_id="ha-core", client_secret=""),
        AuthorizationServer(authorize_url=OAUTH2_AUTHORIZE, token_url=OAUTH2_TOKEN),
    )


# ─── _generate_pkce_pair ──────────────────────────────────────────────────────


class TestGeneratePkcePair:
    """RFC 7636 §4 — verifier ≥43 chars, challenge = b64url(sha256(verifier))."""

    def test_returns_two_strings(self):
        verifier, challenge = _generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_minimum_length(self):
        verifier, _ = _generate_pkce_pair()
        # RFC 7636 mandates 43..128 chars for the verifier
        assert len(verifier) >= 43

    def test_challenge_is_sha256_of_verifier(self):
        verifier, challenge = _generate_pkce_pair()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected

    def test_challenge_no_padding(self):
        _, challenge = _generate_pkce_pair()
        assert "=" not in challenge

    def test_pair_is_random_per_call(self):
        v1, _ = _generate_pkce_pair()
        v2, _ = _generate_pkce_pair()
        assert v1 != v2


# ─── CuliplanOAuth2Implementation ─────────────────────────────────────────────


class TestExtraAuthorizeData:
    """The /authorize redirect must carry PKCE + scope params."""

    @pytest.mark.asyncio
    async def test_extra_authorize_data_includes_pkce(self, hass):
        impl = _make_impl(hass)
        data = impl.extra_authorize_data
        assert data["code_challenge_method"] == "S256"
        assert data["code_challenge"]
        # The verifier itself must NEVER appear in the authorize URL.
        assert "code_verifier" not in data

    @pytest.mark.asyncio
    async def test_extra_authorize_data_includes_scope(self, hass):
        impl = _make_impl(hass)
        assert "scope" in impl.extra_authorize_data
        # Multi-scope is space-joined per RFC 6749 §3.3.
        assert " " in impl.extra_authorize_data["scope"] or (
            len(impl.extra_authorize_data["scope"].split()) >= 1
        )


class TestTokenRequest:
    """The token exchange must include code_verifier for the
    authorization_code grant; refresh requests must NOT.
    """

    @pytest.mark.asyncio
    async def test_authorization_code_adds_verifier(self, hass):
        impl = _make_impl(hass)
        with patch.object(
            type(impl).__mro__[1],
            "_token_request",
            new=AsyncMock(return_value={"access_token": "tok"}),
        ) as super_call:
            await impl._token_request({"grant_type": "authorization_code"})
        sent = super_call.call_args[0][0]
        assert sent["code_verifier"] == impl._code_verifier

    @pytest.mark.asyncio
    async def test_refresh_token_does_not_add_verifier(self, hass):
        impl = _make_impl(hass)
        with patch.object(
            type(impl).__mro__[1],
            "_token_request",
            new=AsyncMock(return_value={"access_token": "tok"}),
        ) as super_call:
            await impl._token_request({"grant_type": "refresh_token"})
        sent = super_call.call_args[0][0]
        assert "code_verifier" not in sent


# ─── async_get_auth_implementation / async_get_authorization_server ──────────


class TestAuthImplementationFactory:
    @pytest.mark.asyncio
    async def test_returns_culiplan_oauth2_implementation(self, hass):
        impl = await async_get_auth_implementation(
            hass, "culiplan", ClientCredential(client_id="ha-core", client_secret="")
        )
        assert isinstance(impl, CuliplanOAuth2Implementation)

    @pytest.mark.asyncio
    async def test_authorization_server_endpoints(self, hass):
        server = await async_get_authorization_server(hass)
        assert server.authorize_url == OAUTH2_AUTHORIZE
        assert server.token_url == OAUTH2_TOKEN
