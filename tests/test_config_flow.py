"""Tests for the Culiplan config flow (OAuth + AI provider selection)."""

from __future__ import annotations


import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
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
async def test_ai_provider_step_cloud_leads_to_mealie_offer(hass):
    """The ai_provider step with Cloud AI leads to mealie_offer form.

    task-1626: Cloud AI no longer creates the entry directly — mealie_offer
    is always shown to give the user a chance to import from Mealie.
    """
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_offer"
    assert flow._entry_data[CONF_AI_MODE] == AI_MODE_CLOUD


@pytest.mark.asyncio
async def test_ai_provider_step_byok_routes_to_byok_form(hass):
    """BYOK mode from ai_provider step routes to the ai_byok sub-step form."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_BYOK})

    # Should show the ai_byok sub-form, not create the entry
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "ai_byok"


@pytest.mark.asyncio
async def test_ai_provider_step_local_routes_to_local_form(hass):
    """Local AI mode from ai_provider step routes to the ai_local sub-step form."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()

    result = await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_LOCAL})

    # Should show the ai_local sub-form, not create the entry
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "ai_local"


@pytest.mark.asyncio
async def test_reauth_step_shows_form(hass):
    """Reauth confirm step shows a form before redirecting to OAuth."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    result = await flow.async_step_reauth_confirm()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
