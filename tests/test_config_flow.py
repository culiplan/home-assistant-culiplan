"""Tests for the Culiplan config flow (OAuth-only setup, reauth, reconfigure)."""

from __future__ import annotations


import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_FIRST_WEEK_HINT,
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


# ─── v0.16.0: OAuth is the whole setup ────────────────────────────────────────


def _no_mealie(hass):
    original = hass.config_entries.async_entries

    def _entries(domain: str | None = None):  # type: ignore[no-untyped-def]
        if domain == "mealie":
            return []
        return original(domain) if domain else original()

    hass.config_entries.async_entries = _entries


@pytest.mark.asyncio
async def test_oauth_without_mealie_creates_entry_immediately(hass):
    """No Mealie in HA: OAuth completion creates the entry, no extra step."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    _no_mealie(hass)
    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    with patch.object(
        flow, "_fetch_culiplan_account_id", new=AsyncMock(return_value=None)
    ):
        result = await flow.async_oauth_create_entry(_mock_oauth_data())

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Culiplan"
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD
    assert result["data"][CONF_FIRST_WEEK_HINT] is True
    assert result["data"]["token"]["access_token"] == "tok_access"


@pytest.mark.asyncio
async def test_initial_flow_has_no_ai_provider_steps():
    """The AI mode choice lives only in the options flow (Configure)."""
    from custom_components.culiplan.config_flow import (
        MealieOptionsFlow,
        OAuth2FlowHandler,
    )

    for removed in (
        "async_step_ai_provider",
        "async_step_ai_byok",
        "async_step_ai_local",
        "async_step_local_endpoint_remote_warning",
    ):
        assert not hasattr(OAuth2FlowHandler, removed), removed
    for kept in (
        "async_step_advanced_ai",
        "async_step_advanced_ai_byok",
        "async_step_advanced_ai_local",
    ):
        assert hasattr(MealieOptionsFlow, kept), kept


@pytest.mark.asyncio
async def test_reconfigure_keeps_existing_data_and_adds_no_hint(hass):
    """Reconfigure/reauth keep the user's AI settings and never opt in to the hint."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.culiplan.config_flow import OAuth2FlowHandler
    from custom_components.culiplan.const import CONF_BYOK_PROVIDER, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="account-A",
        data={
            "token": {"access_token": "old"},
            CONF_AI_MODE: AI_MODE_BYOK,
            CONF_BYOK_PROVIDER: "openai",
        },
    )
    entry.add_to_hass(hass)

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": FlowResultType.ABORT, "reason": "reconfigure_successful"}
    )

    await flow._async_finish_reconfigure(
        {"token": {"access_token": "new"}}, "account-A"
    )

    merged = flow.async_update_reload_and_abort.call_args[1]["data"]
    assert merged[CONF_AI_MODE] == AI_MODE_BYOK
    assert merged[CONF_BYOK_PROVIDER] == "openai"
    assert merged["token"]["access_token"] == "new"
    assert CONF_FIRST_WEEK_HINT not in merged


@pytest.mark.asyncio
async def test_options_flow_shows_ai_mode_saved_in_options(hass):
    """After switching AI mode in Configure, the form shows the saved mode."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.culiplan.config_flow import MealieOptionsFlow
    from custom_components.culiplan.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AI_MODE: AI_MODE_CLOUD},
        options={CONF_AI_MODE: AI_MODE_LOCAL},
    )
    entry.add_to_hass(hass)
    flow = MealieOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    try:
        flow.config_entry = entry
    except (AttributeError, RuntimeError):
        pass

    result = await flow.async_step_init()
    assert result["description_placeholders"]["current_ai_mode"] == AI_MODE_LOCAL

    form = await flow.async_step_advanced_ai()
    key = next(iter(form["data_schema"].schema))
    assert key.default() == AI_MODE_LOCAL


def test_oauth_step_description_has_redirect_tip():
    """The OAuth (auth) step explains what to do if HA isn't reopened."""
    import json
    from pathlib import Path

    root = Path(__file__).parent.parent / "custom_components" / "culiplan"
    for rel in ("strings.json", "translations/en.json"):
        auth = json.loads((root / rel).read_text())["config"]["step"]["auth"]
        assert "external URL" in auth["description"]
        assert "My Home Assistant" in auth["description"]
    for lang in ("de", "es", "fr", "nl"):
        data = json.loads((root / "translations" / f"{lang}.json").read_text())
        assert "My Home Assistant" in data["config"]["step"]["auth"]["description"]


@pytest.mark.asyncio
async def test_reauth_step_shows_form(hass):
    """Reauth confirm step shows a form before redirecting to OAuth."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    result = await flow.async_step_reauth_confirm()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
