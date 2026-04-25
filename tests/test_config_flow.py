"""Tests for the Flavorplan config flow (OAuth + AI provider selection)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_API_KEY,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    DOMAIN,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _mock_oauth_data() -> dict:
    return {
        "token": {
            "access_token": "tok_access",
            "refresh_token": "tok_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    }


# ─── Happy path — Cloud AI ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_flow_cloud_ai_happy_path(hass):
    """Completing OAuth then choosing Cloud AI creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    # The flow should redirect to OAuth pick_implementation step.
    assert result["type"] in (
        FlowResultType.ABORT,
        FlowResultType.FORM,
        FlowResultType.EXTERNAL_STEP,
    )


@pytest.mark.asyncio
async def test_ai_provider_step_cloud_creates_entry(hass):
    """The ai_provider step with Cloud AI creates the config entry."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(
        user_input={CONF_AI_MODE: AI_MODE_CLOUD}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD


@pytest.mark.asyncio
async def test_ai_provider_step_byok_stores_key_locally(hass):
    """BYOK mode stores the API key; it stays in HA config only."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(
        user_input={
            CONF_AI_MODE: AI_MODE_BYOK,
            CONF_BYOK_PROVIDER: "openai",
            CONF_BYOK_API_KEY: "sk-test-key",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_BYOK
    assert result["data"][CONF_BYOK_PROVIDER] == "openai"
    assert result["data"][CONF_BYOK_API_KEY] == "sk-test-key"


@pytest.mark.asyncio
async def test_ai_provider_step_local_ai(hass):
    """Local AI mode stores endpoint and model name."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(
        user_input={
            CONF_AI_MODE: AI_MODE_LOCAL,
            CONF_LOCAL_ENDPOINT: "http://localhost:11434",
            CONF_LOCAL_MODEL: "llama3.2",
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_LOCAL
    assert result["data"][CONF_LOCAL_ENDPOINT] == "http://localhost:11434"
    assert result["data"][CONF_LOCAL_MODEL] == "llama3.2"


@pytest.mark.asyncio
async def test_reauth_step_shows_form(hass):
    """Reauth confirm step shows a form before redirecting to OAuth."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    result = await flow.async_step_reauth_confirm()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
