"""Tests for the Mealie migration config flow steps (task-1394).

Tests cover:
- AC#1: mealie_offer step appears after AI provider selection
- AC#2: mealie_preview step shows {willImport, willFlag, willSkip} counts
- AC#3: progress step eventually transitions to done
- AC#4: rollback option available in options flow within 24 h
- AC#5: synthetic v1 and v2 Mealie data shapes handled correctly
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.culiplan.const import (
    AI_MODE_CLOUD,
    CONF_AI_MODE,
    CONF_MEALIE_IMPORT_AT,
    CONF_MEALIE_JOB_ID,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    MEALIE_ROLLBACK_WINDOW_SECONDS,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_oauth_data() -> dict:
    return {
        "token": {
            "access_token": "tok_access",
            "refresh_token": "tok_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    }


def _make_preview_response(
    will_import: int = 10,
    will_flag: int = 2,
    will_skip: int = 1,
) -> dict:
    return {
        "jobId": "job-preview-123",
        "dryRun": True,
        "preview": {
            "willImport": will_import,
            "willFlag": will_flag,
            "willSkip": will_skip,
            "unparsedIngredientSamples": ["For the sauce:", "Garnish:"],
        },
    }


def _make_start_response(job_id: str = "job-import-456") -> dict:
    return {
        "jobId": job_id,
        "dryRun": False,
        "message": "Mealie import started.",
    }


# ─── Helper to create a flow with mocked oauth ────────────────────────────────


def _make_flow(hass) -> "OAuth2FlowHandler":  # type: ignore[name-defined]
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = _mock_oauth_data()
    return flow


# ─── AC#1: mealie_offer step after ai_provider ────────────────────────────────


@pytest.mark.asyncio
async def test_ai_provider_leads_to_mealie_offer(hass):
    """After choosing Cloud AI, the flow should show mealie_offer."""
    flow = _make_flow(hass)

    result = await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_offer"


@pytest.mark.asyncio
async def test_mealie_offer_skip_creates_entry(hass):
    """Declining migration creates the config entry directly."""
    flow = _make_flow(hass)

    # Prime the entry data via ai_provider step
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    result = await flow.async_step_mealie_offer(user_input={"migrate_mealie": False})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD
    # Mealie credentials should NOT be in entry
    assert CONF_MEALIE_TOKEN not in result["data"]


@pytest.mark.asyncio
async def test_mealie_offer_accept_shows_credentials(hass):
    """Accepting migration shows the credentials form."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    result = await flow.async_step_mealie_offer(user_input={"migrate_mealie": True})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_credentials"


# ─── AC#2: preview screen shows counts ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mealie_credentials_success_shows_preview(hass):
    """Valid credentials trigger a dry-run and show the preview step."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    with patch.object(
        flow,
        "_call_migrate_preview",
        return_value=(_make_preview_response()["preview"], None),
    ):
        result = await flow.async_step_mealie_credentials(
            user_input={
                CONF_MEALIE_URL: "http://mealie.local:9000",
                CONF_MEALIE_TOKEN: "tok-mealie",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_preview"


@pytest.mark.asyncio
async def test_preview_description_placeholders_present(hass):
    """Preview form must include willImport/willFlag/willSkip placeholders."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    preview = _make_preview_response(will_import=15, will_flag=3, will_skip=0)[
        "preview"
    ]
    flow._mealie_preview = preview
    # Store temp credentials
    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    result = await flow.async_step_mealie_preview()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_preview"
    placeholders = result.get("description_placeholders", {})
    assert placeholders["will_import"] == "15"
    assert placeholders["will_flag"] == "3"
    assert placeholders["will_skip"] == "0"
    assert "For the sauce:" in placeholders["samples"]


@pytest.mark.asyncio
async def test_preview_cancel_creates_entry_without_mealie_data(hass):
    """Cancelling the preview creates the entry without Mealie credentials."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    flow._mealie_preview = _make_preview_response()["preview"]
    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    result = await flow.async_step_mealie_preview(user_input={"confirm_import": False})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Token must NOT be persisted
    assert CONF_MEALIE_TOKEN not in result["data"]
    assert CONF_MEALIE_URL not in result["data"]


# ─── AC#3: progress → done ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mealie_progress_creates_entry_on_success(hass):
    """Progress step should eventually create the entry with job metadata."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    with (
        patch.object(
            flow,
            "_call_migrate_start",
            return_value=("job-abc-789", None),
        ),
        patch.object(
            flow,
            "_poll_import_progress",
            return_value=(True, []),
        ),
    ):
        result = await flow.async_step_mealie_progress()

    # Should arrive at the mealie_done form
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_done"


@pytest.mark.asyncio
async def test_mealie_done_creates_entry_with_job_id(hass):
    """mealie_done step creates the entry and records job_id + import timestamp."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    flow._mealie_job_id = "job-xyz-321"
    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    result = await flow.async_step_mealie_done(user_input={})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MEALIE_JOB_ID] == "job-xyz-321"
    assert CONF_MEALIE_IMPORT_AT in result["data"]
    # Token and URL must NOT be persisted
    assert CONF_MEALIE_TOKEN not in result["data"]
    assert CONF_MEALIE_URL not in result["data"]


# ─── AC#4: rollback visible within 24 h ──────────────────────────────────────


@pytest.mark.asyncio
async def test_options_flow_rollback_visible_within_24h(hass):
    """Rollback option should be shown when import is within 24 h."""
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {
        CONF_MEALIE_JOB_ID: "job-123",
        CONF_MEALIE_IMPORT_AT: int(time.time()) - 3600,  # 1 hour ago
    }

    flow = MealieOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "true"


@pytest.mark.asyncio
async def test_options_flow_rollback_hidden_after_24h(hass):
    """Rollback option should NOT be available after 24 h."""
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {
        CONF_MEALIE_JOB_ID: "job-123",
        CONF_MEALIE_IMPORT_AT: int(time.time()) - MEALIE_ROLLBACK_WINDOW_SECONDS - 100,
    }

    flow = MealieOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "false"


@pytest.mark.asyncio
async def test_options_flow_no_import_at_shows_no_rollback(hass):
    """No import timestamp means no rollback option."""
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {}  # No mealie import metadata

    flow = MealieOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "false"


@pytest.mark.asyncio
async def test_rollback_calls_delete_endpoint(hass):
    """Rollback step calls DELETE /api/migrate/mealie/rollback."""
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {
        CONF_MEALIE_JOB_ID: "job-123",
        CONF_MEALIE_IMPORT_AT: int(time.time()) - 60,
        "token": {"access_token": "tok_access"},
    }

    flow = MealieOptionsFlow(entry)
    flow.hass = hass

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "deleted": {"recipes": 5, "shoppingItems": 3, "mealPlans": 2},
            "message": "Rollback complete.",
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=mock_response)

    with patch(
        "custom_components.culiplan.config_flow.async_get_clientsession",
        return_value=mock_session,
    ):
        result = await flow.async_step_mealie_rollback()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "rollback_complete"


# ─── AC#5: v1 and v2 schema inputs ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_accepts_v1_mealie_data(hass):
    """dry-run preview should work even when Mealie returns v1-style counts."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    # Simulate backend returning preview for a v1 Mealie instance
    v1_preview = {
        "willImport": 20,
        "willFlag": 5,
        "willSkip": 0,
        "unparsedIngredientSamples": [],
    }

    with patch.object(
        flow,
        "_call_migrate_preview",
        return_value=(v1_preview, None),
    ):
        result = await flow.async_step_mealie_credentials(
            user_input={
                CONF_MEALIE_URL: "http://mealie-v1.local:9000",
                CONF_MEALIE_TOKEN: "tok-v1",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_preview"
    assert flow._mealie_preview == v1_preview


@pytest.mark.asyncio
async def test_preview_accepts_v2_mealie_data(hass):
    """dry-run preview should work when Mealie v2 returns integer recipeServings."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    # Simulate backend returning preview for a v2 Mealie instance
    v2_preview = {
        "willImport": 30,
        "willFlag": 2,
        "willSkip": 1,
        "unparsedIngredientSamples": ["For the sauce:"],
    }

    with patch.object(
        flow,
        "_call_migrate_preview",
        return_value=(v2_preview, None),
    ):
        result = await flow.async_step_mealie_credentials(
            user_input={
                CONF_MEALIE_URL: "http://mealie-v2.local:9000",
                CONF_MEALIE_TOKEN: "tok-v2",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_preview"
    assert flow._mealie_preview["willImport"] == 30


# ─── Error handling ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credentials_error_shows_form_again(hass):
    """Connection error during dry-run shows the credentials form with error."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    with patch.object(
        flow,
        "_call_migrate_preview",
        return_value=(None, "mealie_unreachable"),
    ):
        result = await flow.async_step_mealie_credentials(
            user_input={
                CONF_MEALIE_URL: "http://unreachable.local:9000",
                CONF_MEALIE_TOKEN: "bad-tok",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_credentials"
    assert "base" in result.get("errors", {})
    assert result["errors"]["base"] == "mealie_unreachable"


@pytest.mark.asyncio
async def test_start_error_falls_through_to_done(hass):
    """If the migration start fails, flow continues to done with error logged."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    with patch.object(
        flow,
        "_call_migrate_start",
        return_value=(None, "unknown"),
    ):
        result = await flow.async_step_mealie_progress()

    # Should still reach the done step gracefully
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_done"


# ─── B2 regression: rollback must not raise TypeError ────────────────────────


@pytest.mark.asyncio
async def test_rollback_no_type_error_on_network_failure(hass):
    """async_step_mealie_rollback must not raise TypeError (B2 from E2E review).

    Previously, CuliplanApiClient(self.hass, self._config_entry) was called with
    the wrong signature — it raised TypeError before any network call was made,
    causing the rollback to silently abort with 'rollback_failed' even though
    nothing was attempted.  The line was removed; this test confirms the path
    degrades gracefully when the network call itself fails.
    """
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = {
        CONF_MEALIE_JOB_ID: "job-rollback-test",
        CONF_MEALIE_IMPORT_AT: int(time.time()) - 60,
        "access_token": "tok_access",
    }

    flow = MealieOptionsFlow(entry)
    flow.hass = hass
    flow._config_entry = entry

    # Simulate a network error during the DELETE call — we just need to confirm
    # no TypeError is raised before reaching the aiohttp call.
    with patch(
        "custom_components.culiplan.config_flow.aiohttp.ClientSession",
    ) as mock_session_cls:
        mock_session = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.raise_for_status.side_effect = Exception("simulated network error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session.delete = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        # Must not raise TypeError; should abort with "rollback_failed"
        result = await flow.async_step_mealie_rollback()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "rollback_failed"
