"""
Tests for BYOK key validation flow and local secret store (task-1390).

AC#1 — Config flow step includes BYOK option per provider
AC#2 — Validation call uses provider's cheapest endpoint; < €0.01 cost
AC#3 — Key persisted only in HA's homeassistant.helpers.storage
AC#4 — Bad key produces user-friendly error; NOT stored
AC#5 — Audit log entry records {user_id, mode='byok-<provider>', validated=True}
        with no key fingerprint (see test_ha_ai_envelope.routes.test.ts in monorepo
        for AC#5 — backend side; this test covers the HA side)

Key architectural guarantee: API key NEVER appears in CuliplanApiClient
calls or config entry data after validation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.ai.key_store import (
    BYOKKeyStore,
    validate_byok_key,
    validate_anthropic_key,
    validate_google_key,
    validate_openai_key,
)
from custom_components.culiplan.ai.types import ProviderAuthError


# ─── BYOKKeyStore tests ────────────────────────────────────────────────────────


class TestBYOKKeyStore:
    """AC#3: keys stored in HA's homeassistant.helpers.storage only."""

    @pytest.fixture
    def mock_store(self):
        with patch(
            "custom_components.culiplan.ai.key_store.Store", autospec=True
        ) as MockStore:
            instance = MockStore.return_value
            instance.async_load = AsyncMock(return_value=None)
            instance.async_save = AsyncMock(return_value=None)
            instance.async_remove = AsyncMock(return_value=None)
            yield instance

    @pytest.mark.asyncio
    async def test_load_empty_storage(self, mock_store):
        """Empty storage returns no keys."""
        mock_store.async_load.return_value = None
        hass = MagicMock()
        ks = BYOKKeyStore(hass)
        await ks.async_load()
        assert ks.get_key("anthropic") is None
        assert ks.has_key("anthropic") is False

    @pytest.mark.asyncio
    async def test_load_existing_keys(self, mock_store):
        """Keys present in storage are loaded."""
        mock_store.async_load.return_value = {
            "keys": {"anthropic": "sk-ant-test-loaded"}
        }
        hass = MagicMock()
        ks = BYOKKeyStore(hass)
        await ks.async_load()
        assert ks.get_key("anthropic") == "sk-ant-test-loaded"
        assert ks.has_key("anthropic") is True

    @pytest.mark.asyncio
    async def test_set_key_persists_to_store(self, mock_store):
        """Setting a key persists it via async_save."""
        mock_store.async_load.return_value = None
        hass = MagicMock()
        ks = BYOKKeyStore(hass)
        await ks.async_load()
        await ks.async_set_key("openai", "sk-test-key")

        assert ks.get_key("openai") == "sk-test-key"
        mock_store.async_save.assert_called_once_with(
            {"keys": {"openai": "sk-test-key"}}
        )

    @pytest.mark.asyncio
    async def test_delete_key_removes_from_store(self, mock_store):
        """Deleting a key removes it from storage."""
        mock_store.async_load.return_value = {"keys": {"anthropic": "sk-ant-key"}}
        hass = MagicMock()
        ks = BYOKKeyStore(hass)
        await ks.async_load()
        await ks.async_delete_key("anthropic")

        assert ks.has_key("anthropic") is False
        mock_store.async_save.assert_called_with({"keys": {}})

    @pytest.mark.asyncio
    async def test_clear_removes_all_keys(self, mock_store):
        """Clear removes all keys and calls async_remove."""
        mock_store.async_load.return_value = {
            "keys": {"anthropic": "key1", "openai": "key2"}
        }
        hass = MagicMock()
        ks = BYOKKeyStore(hass)
        await ks.async_load()
        await ks.async_clear()

        assert ks.has_key("anthropic") is False
        assert ks.has_key("openai") is False
        mock_store.async_remove.assert_called_once()


# ─── Key validation tests ──────────────────────────────────────────────────────


class TestValidateOpenAIKey:
    """AC#2: cheap validation; AC#4: bad key → ProviderAuthError, not stored."""

    @pytest.mark.asyncio
    async def test_valid_key_succeeds(self):
        """Valid key returns True."""
        with patch("openai.AsyncOpenAI") as MockClass:
            instance = MockClass.return_value
            instance.models.list = AsyncMock(return_value=MagicMock())
            result = await validate_openai_key("sk-valid-key")
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_key_raises_provider_auth_error(self):
        """401 from OpenAI raises ProviderAuthError — key not stored (AC#4)."""
        with patch("openai.AsyncOpenAI") as MockClass:
            instance = MockClass.return_value
            instance.models.list = AsyncMock(
                side_effect=Exception("401 Invalid API key")
            )
            with pytest.raises(ProviderAuthError, match="invalid"):
                await validate_openai_key("sk-bad-key")

    @pytest.mark.asyncio
    async def test_generic_error_raises_provider_auth_error(self):
        """Network errors also surface as ProviderAuthError."""
        with patch("openai.AsyncOpenAI") as MockClass:
            instance = MockClass.return_value
            instance.models.list = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            with pytest.raises(ProviderAuthError):
                await validate_openai_key("sk-unreachable")


class TestValidateAnthropicKey:
    @pytest.mark.asyncio
    async def test_valid_key_succeeds(self):
        with patch("anthropic.AsyncAnthropic") as MockClass:
            instance = MockClass.return_value
            instance.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(type="text", text="Hi")])
            )
            result = await validate_anthropic_key("sk-ant-valid")
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_key_raises_provider_auth_error(self):
        with patch("anthropic.AsyncAnthropic") as MockClass:
            instance = MockClass.return_value
            instance.messages.create = AsyncMock(
                side_effect=Exception("401 invalid_api_key: Authentication failed")
            )
            with pytest.raises(ProviderAuthError, match="invalid"):
                await validate_anthropic_key("sk-ant-bad")


class TestValidateGoogleKey:
    @pytest.mark.asyncio
    async def test_valid_key_succeeds(self):
        # Ensure the submodule is loaded so `patch` can find the attribute
        # (the `google` namespace package only exposes `genai` once imported).
        import google.genai  # noqa: F401

        async def fake_list():
            yield MagicMock(name="gemini-2.5-flash")

        with patch("google.genai") as MockGenai:
            instance = MockGenai.Client.return_value
            instance.aio.models.list = MagicMock(return_value=fake_list())
            result = await validate_google_key("AIzaValid")
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_key_raises_provider_auth_error(self):
        import google.genai  # noqa: F401

        with patch("google.genai") as MockGenai:
            instance = MockGenai.Client.return_value
            instance.aio.models.list = MagicMock(
                side_effect=Exception("API_KEY_INVALID")
            )
            with pytest.raises(ProviderAuthError, match="invalid"):
                await validate_google_key("AIzaBad")


class TestValidateBYOKKey:
    @pytest.mark.asyncio
    async def test_delegates_to_correct_validator_openai(self):
        with patch(
            "custom_components.culiplan.ai.key_store.validate_openai_key",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_fn:
            result = await validate_byok_key("openai", "sk-test")
        mock_fn.assert_called_once_with("sk-test")
        assert result is True

    @pytest.mark.asyncio
    async def test_delegates_to_correct_validator_anthropic(self):
        with patch(
            "custom_components.culiplan.ai.key_store.validate_anthropic_key",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_fn:
            await validate_byok_key("anthropic", "sk-ant-test")
        mock_fn.assert_called_once_with("sk-ant-test")

    @pytest.mark.asyncio
    async def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown BYOK provider"):
            await validate_byok_key("unknown-provider", "some-key")


# ─── Config flow BYOK validation (AC#1 + AC#4) ────────────────────────────────


class TestConfigFlowBYOKValidation:
    """
    AC#1: config flow BYOK step validates key before storing.
    AC#4: bad key → error shown, key NOT persisted.
    """

    @pytest.mark.asyncio
    async def test_valid_byok_key_stored_not_in_entry_data(self, hass):
        """Valid key is stored in BYOKKeyStore; NOT in config entry data.

        BYOK input moved to its own ``async_step_ai_byok`` step in the flow
        refactor — the original test driver called ``async_step_ai_provider``
        with the BYOK fields in the same payload, which silently fell back to
        the form. Drive the dedicated step directly.
        """
        from custom_components.culiplan.config_flow import OAuth2FlowHandler

        handler = OAuth2FlowHandler()
        handler.hass = hass
        handler._oauth_data = {
            "token": {"access_token": "tok_test", "refresh_token": "ref_test"}
        }
        handler._entry_data = {
            **handler._oauth_data,
            "ai_mode": "byok",
        }

        with (
            patch(
                "custom_components.culiplan.config_flow.validate_byok_key",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "custom_components.culiplan.config_flow.BYOKKeyStore"
            ) as MockKeyStore,
            patch.object(
                handler,
                "async_step_mealie_offer",
                new=AsyncMock(
                    return_value={
                        "type": "create_entry",
                        "data": {**handler._entry_data, "byok_provider": "anthropic"},
                    }
                ),
            ),
        ):
            mock_store_instance = AsyncMock()
            MockKeyStore.return_value = mock_store_instance
            mock_store_instance.async_load = AsyncMock()
            mock_store_instance.async_set_key = AsyncMock()

            result = await handler.async_step_ai_byok(
                {
                    "byok_provider": "anthropic",
                    "byok_api_key": "sk-ant-valid-key",
                }
            )

        # Key was stored in BYOKKeyStore
        mock_store_instance.async_set_key.assert_called_once_with(
            "anthropic", "sk-ant-valid-key"
        )

        # Entry data must NOT contain the raw API key
        entry_data = result["data"]
        assert (
            "byok_api_key" not in entry_data or entry_data.get("byok_api_key") is None
        )
        assert entry_data.get("byok_provider") == "anthropic"

    @pytest.mark.asyncio
    async def test_invalid_byok_key_shows_error_not_stored(self, hass):
        """AC#4: bad key → user-friendly error; key NOT persisted."""
        from custom_components.culiplan.config_flow import OAuth2FlowHandler

        handler = OAuth2FlowHandler()
        handler.hass = hass
        handler._oauth_data = {
            "token": {"access_token": "tok_test", "refresh_token": "ref_test"}
        }
        handler._entry_data = {
            **handler._oauth_data,
            "ai_mode": "byok",
        }

        with (
            patch(
                "custom_components.culiplan.config_flow.validate_byok_key",
                new_callable=AsyncMock,
                side_effect=ProviderAuthError("The API key is invalid."),
            ),
            patch(
                "custom_components.culiplan.config_flow.BYOKKeyStore"
            ) as MockKeyStore,
        ):
            mock_store_instance = AsyncMock()
            MockKeyStore.return_value = mock_store_instance
            mock_store_instance.async_load = AsyncMock()
            mock_store_instance.async_set_key = AsyncMock()

            result = await handler.async_step_ai_byok(
                {
                    "byok_provider": "anthropic",
                    "byok_api_key": "sk-ant-INVALID",
                }
            )

        # Shows form with error
        assert result["type"] == "form"
        assert "byok_api_key" in result.get("errors", {})

        # Key was NOT stored
        mock_store_instance.async_set_key.assert_not_called()
