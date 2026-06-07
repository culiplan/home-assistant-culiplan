"""Tests for task-1626: default Cloud AI + Advanced AI in OptionsFlow.

Acceptance criteria:
- #1 New installs land on Mealie offer immediately after OAuth (no AI mode prompt).
- #2 Cloud AI is the implicit default and gets stored in entry.data.
- #3 OptionsFlow exposes AI mode + provider config under an "Advanced AI settings" menu.
- #4 Reconfiguration via OptionsFlow does not require integration removal.
- #5 Tests cover both first-run-default and OptionsFlow-reconfigure paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_ADVANCED_AI,
    CONF_AI_MODE,
    CONF_BYOK_API_KEY,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
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


def _make_flow(hass) -> "OAuth2FlowHandler":  # type: ignore[name-defined]
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()
    return flow


# ─── AC#1 + AC#2: First run skips AI step, defaults to Cloud AI ───────────────


@pytest.mark.asyncio
async def test_oauth_create_entry_skips_ai_step(hass):
    """OAuth completion should skip the AI step and go directly to mealie_offer.

    task-1626 AC#1: new installs land on Mealie offer immediately after OAuth
    when Mealie is configured; without it the offer step short-circuits to
    entry creation (mealie_offer self-skips when no mealie config_entry).
    """
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    # Pretend the user has a Mealie integration so mealie_offer renders.
    original = hass.config_entries.async_entries

    def _entries(domain: str | None = None):  # type: ignore[no-untyped-def]
        if domain == "mealie":
            return [MagicMock()]
        return original(domain) if domain else original()

    hass.config_entries.async_entries = _entries

    # Short-circuit the network probe — pytest-socket would otherwise
    # spawn a `_run_safe_shutdown_loop` daemon thread that leaks across
    # the test boundary and trips HA's verify_cleanup fixture.
    from unittest.mock import patch, AsyncMock as _AsyncMock

    with patch.object(
        flow, "_fetch_culiplan_account_id", new=_AsyncMock(return_value=None)
    ):
        result = await flow.async_oauth_create_entry(_mock_oauth_data())

    # Must land on mealie_offer, NOT ai_provider
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_offer"


@pytest.mark.asyncio
async def test_first_run_defaults_to_cloud_ai_in_entry_data(hass):
    """Cloud AI must be the implicit default stored in entry.data.

    task-1626 AC#2: Cloud AI is stored automatically, no user input required.
    """
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    from unittest.mock import patch, AsyncMock as _AsyncMock

    with patch.object(
        flow, "_fetch_culiplan_account_id", new=_AsyncMock(return_value=None)
    ):
        await flow.async_oauth_create_entry(_mock_oauth_data())

    # _entry_data must have CONF_AI_MODE = AI_MODE_CLOUD already set
    assert flow._entry_data.get(CONF_AI_MODE) == AI_MODE_CLOUD


@pytest.mark.asyncio
async def test_first_run_skipping_mealie_creates_cloud_entry(hass):
    """Full first-run: OAuth → skip Mealie → entry with Cloud AI.

    task-1626 AC#2: Cloud AI ends up in the created config entry.
    """
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    from unittest.mock import patch, AsyncMock as _AsyncMock

    # Simulate OAuth completion (mock the network probe).
    with patch.object(
        flow, "_fetch_culiplan_account_id", new=_AsyncMock(return_value=None)
    ):
        await flow.async_oauth_create_entry(_mock_oauth_data())

    # User skips Mealie migration
    result = await flow.async_step_mealie_offer(user_input={"migrate_mealie": False})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD


# ─── AC#3 + AC#4: OptionsFlow exposes Advanced AI settings ───────────────────


@pytest.mark.asyncio
async def test_options_flow_init_shows_advanced_ai_toggle(hass):
    """OptionsFlow init step must show the Advanced AI settings toggle.

    task-1626 AC#3.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    # The schema must contain the advanced_ai toggle
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert any(CONF_ADVANCED_AI in k for k in schema_keys)


@pytest.mark.asyncio
async def test_options_flow_advanced_ai_toggle_opens_ai_step(hass):
    """Toggling Advanced AI in OptionsFlow should open the ai mode selection form.

    task-1626 AC#3.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass

    with patch(
        "custom_components.culiplan.config_flow.probe_local_ai_endpoints",
        return_value=[],
    ):
        result = await flow.async_step_init(user_input={CONF_ADVANCED_AI: True})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai"


@pytest.mark.asyncio
async def test_options_flow_advanced_ai_switch_to_cloud(hass):
    """Advanced AI step: selecting Cloud AI commits immediately.

    task-1626 AC#4: reconfiguration without removing the integration.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_BYOK, CONF_BYOK_PROVIDER: "openai"}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass

    result = await flow.async_step_advanced_ai(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD


@pytest.mark.asyncio
async def test_options_flow_advanced_ai_byok_stores_key(hass):
    """Advanced AI BYOK step validates + stores the key, commits new mode.

    task-1626 AC#3: BYOK provider config accessible via OptionsFlow.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass
    flow._advanced_ai_data = {CONF_AI_MODE: AI_MODE_BYOK}

    with (
        patch(
            "custom_components.culiplan.config_flow.validate_byok_key",
            return_value=None,
        ),
        patch(
            "custom_components.culiplan.config_flow.BYOKKeyStore",
        ) as mock_key_store_cls,
    ):
        mock_key_store = AsyncMock()
        mock_key_store_cls.return_value = mock_key_store
        mock_key_store.async_load = AsyncMock()
        mock_key_store.async_set_key = AsyncMock()

        result = await flow.async_step_advanced_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-test",
            }
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_BYOK
    assert result["data"][CONF_BYOK_PROVIDER] == "openai"
    # Key must NOT be in options data (zero-custody §13.2)
    assert CONF_BYOK_API_KEY not in result["data"]


@pytest.mark.asyncio
async def test_options_flow_advanced_ai_byok_invalid_key_shows_error(hass):
    """Advanced AI BYOK step shows error on invalid key without committing.

    task-1626 AC#3: proper validation in OptionsFlow too.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow
    from custom_components.culiplan.ai.types import ProviderAuthError

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass
    flow._advanced_ai_data = {CONF_AI_MODE: AI_MODE_BYOK}

    with patch(
        "custom_components.culiplan.config_flow.validate_byok_key",
        side_effect=ProviderAuthError("invalid key"),
    ):
        result = await flow.async_step_advanced_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-bad",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai_byok"
    assert CONF_BYOK_API_KEY in result.get("errors", {})


@pytest.mark.asyncio
async def test_options_flow_advanced_ai_local_stores_endpoint(hass):
    """Advanced AI Local step probes, stores endpoint and model, then commits.

    task-1626 AC#3: Local AI config accessible via OptionsFlow.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass
    flow._advanced_ai_data = {CONF_AI_MODE: AI_MODE_LOCAL}
    flow._detected_endpoints = []

    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        return_value=MagicMock(),
    ):
        result = await flow.async_step_advanced_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "localhost:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_LOCAL
    assert result["data"][CONF_LOCAL_ENDPOINT] == "localhost:11434"
    assert result["data"][CONF_LOCAL_MODEL] == "llama3.2"


@pytest.mark.asyncio
async def test_options_flow_no_advanced_ai_toggle_returns_no_change(hass):
    """OptionsFlow: submitting without Advanced AI toggle saves empty options.

    task-1626 AC#4: existing entry is NOT removed on options save.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass

    result = await flow.async_step_init(user_input={CONF_ADVANCED_AI: False})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Options now always persist the pantry windows + debug + auto_update
    # toggles (previously they were saved only when changed); CONF_AI_MODE
    # is preserved unchanged because the Advanced AI sub-flow was not entered.
    assert CONF_AI_MODE not in result["data"]
    assert "auto_update" in result["data"]
    assert "expiry_days" in result["data"]
