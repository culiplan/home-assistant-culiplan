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


def _set_config_entry_compat(flow, entry) -> None:
    """Cross-HA-version setter for OptionsFlow.config_entry.

    HA 2026.6+ promoted ``config_entry`` to a property that resolves
    through ``hass.config_entries.async_get_known_entry(
    self._config_entry_id)``, so the entry MUST be registered with hass.
    HA 2024.10 (the CI floor) keeps ``config_entry`` as a plain attribute.
    """
    flow._config_entry_id = getattr(entry, "entry_id", "test_entry_id")  # type: ignore[attr-defined]
    flow.handler = getattr(entry, "entry_id", "test_entry_id")
    try:
        flow.config_entry = entry
    except AttributeError:
        pass


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
            # The preview screen renders `sampleTitles` from the backend
            # payload (was `unparsedIngredientSamples` in earlier shape).
            "sampleTitles": ["For the sauce:", "Garnish:"],
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
    # The mealie_offer step now skips the form entirely if HA has no
    # Mealie integration configured (commit 1e5c0… — no point asking the
    # user to import from nowhere). Pretend a Mealie entry exists so the
    # flow goes through the import wizard.
    original_async_entries = hass.config_entries.async_entries

    def _async_entries_with_mealie(domain: str | None = None):  # type: ignore[no-untyped-def]
        if domain == "mealie":
            return [MagicMock()]
        return original_async_entries(domain) if domain else original_async_entries()

    hass.config_entries.async_entries = _async_entries_with_mealie
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
    """Valid credentials trigger a dry-run and show the preview step.

    ``_call_migrate_preview`` was moved off the flow class to module scope
    (no per-flow state to encapsulate); patch it there.
    """
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    with patch(
        "custom_components.culiplan.config_flow._call_migrate_preview",
        new=AsyncMock(return_value=_make_preview_response()["preview"]),
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

    # ``_call_migrate_start`` is now a module-level coroutine returning the
    # raw backend payload dict (no separate progress poller — the backend
    # finishes inline for the synchronous mealie import). The progress step
    # forwards to mealie_done with the job_id, which creates the entry
    # immediately (no intermediate form).
    with patch(
        "custom_components.culiplan.config_flow._call_migrate_start",
        new=AsyncMock(return_value={"jobId": "job-abc-789", "errors": 0}),
    ):
        result = await flow.async_step_mealie_progress()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MEALIE_JOB_ID] == "job-abc-789"
    assert CONF_MEALIE_IMPORT_AT in result["data"]
    # Credentials stripped before persisting (§6.6)
    assert CONF_MEALIE_TOKEN not in result["data"]
    assert CONF_MEALIE_URL not in result["data"]


@pytest.mark.asyncio
async def test_mealie_done_creates_entry_with_job_id(hass):
    """mealie_done step creates the entry and records job_id + import timestamp."""
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    # Done step reads from `_entry_data` (job_id + import_at are written by
    # the progress step before forwarding here); the legacy
    # `flow._mealie_job_id` attribute is gone.
    flow._entry_data[CONF_MEALIE_JOB_ID] = "job-xyz-321"
    flow._entry_data[CONF_MEALIE_IMPORT_AT] = int(time.time())
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


def _make_options_flow(entry_data: dict, hass) -> "MealieOptionsFlow":  # type: ignore[name-defined]
    """Construct MealieOptionsFlow with a real registered MockConfigEntry.

    HA 2026.6+ resolves ``config_entry`` through the manager via
    ``self._config_entry_id`` so the entry must be registered with hass.
    HA 2024.10 (the CI floor) still works with the legacy attribute path.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.culiplan.config_flow import MealieOptionsFlow
    from custom_components.culiplan.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, options={})
    entry.add_to_hass(hass)
    flow = MealieOptionsFlow()
    flow.hass = hass
    _set_config_entry_compat(flow, entry)
    return flow


@pytest.mark.asyncio
async def test_options_flow_rollback_visible_within_24h(hass):
    """Rollback option should be shown when import is within 24 h."""
    flow = _make_options_flow(
        {
            CONF_MEALIE_JOB_ID: "job-123",
            CONF_MEALIE_IMPORT_AT: int(time.time()) - 3600,  # 1 hour ago
        },
        hass,
    )

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "true"


@pytest.mark.asyncio
async def test_options_flow_rollback_hidden_after_24h(hass):
    """Rollback option should NOT be available after 24 h."""
    flow = _make_options_flow(
        {
            CONF_MEALIE_JOB_ID: "job-123",
            CONF_MEALIE_IMPORT_AT: int(time.time())
            - MEALIE_ROLLBACK_WINDOW_SECONDS
            - 100,
        },
        hass,
    )

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "false"


@pytest.mark.asyncio
async def test_options_flow_no_import_at_shows_no_rollback(hass):
    """No import timestamp means no rollback option."""
    flow = _make_options_flow({}, hass)

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    placeholders = result.get("description_placeholders", {})
    assert placeholders.get("rollback_available") == "false"


@pytest.mark.asyncio
async def test_rollback_calls_delete_endpoint(hass):
    """Rollback step calls DELETE /api/migrate/mealie/rollback."""
    flow = _make_options_flow(
        {
            CONF_MEALIE_JOB_ID: "job-123",
            CONF_MEALIE_IMPORT_AT: int(time.time()) - 60,
            "access_token": "tok_access",
        },
        hass,
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=mock_response)

    # The rollback step uses HA's shared aiohttp session via
    # aiohttp_client.async_get_clientsession.
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        result = await flow.async_step_mealie_rollback()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "rollback_complete"
    mock_session.delete.assert_called_once()


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

    with patch(
        "custom_components.culiplan.config_flow._call_migrate_preview",
        new=AsyncMock(return_value=v1_preview),
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

    with patch(
        "custom_components.culiplan.config_flow._call_migrate_preview",
        new=AsyncMock(return_value=v2_preview),
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
    """Connection error during dry-run shows the credentials form with error.

    ``aiohttp.ClientConnectionError`` is mapped to a field-level error on
    the mealie_url field (so the user fixes the URL); a bare exception
    falls back to ``base`` with the generic ``unknown`` key.
    """
    import aiohttp as _aiohttp

    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    with patch(
        "custom_components.culiplan.config_flow._call_migrate_preview",
        new=AsyncMock(side_effect=_aiohttp.ClientConnectionError("unreachable")),
    ):
        result = await flow.async_step_mealie_credentials(
            user_input={
                CONF_MEALIE_URL: "http://unreachable.local:9000",
                CONF_MEALIE_TOKEN: "bad-tok",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "mealie_credentials"
    errors = result.get("errors", {})
    assert errors.get(CONF_MEALIE_URL) == "mealie_unreachable"


@pytest.mark.asyncio
async def test_start_error_falls_through_to_done(hass):
    """If the migration start fails, flow creates the entry without Mealie data.

    On start failure the flow no longer renders an intermediate done form
    — it strips the in-flight Mealie credentials and creates the entry
    so the user isn't stuck mid-wizard. This matches the §6.6 §"never
    persist credentials" rule even on failure.
    """
    flow = _make_flow(hass)
    await flow.async_step_ai_provider(user_input={CONF_AI_MODE: AI_MODE_CLOUD})

    flow._entry_data[CONF_MEALIE_URL] = "http://mealie.local:9000"
    flow._entry_data[CONF_MEALIE_TOKEN] = "tok-mealie"

    with patch(
        "custom_components.culiplan.config_flow._call_migrate_start",
        new=AsyncMock(side_effect=Exception("simulated start failure")),
    ):
        result = await flow.async_step_mealie_progress()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Credentials must NOT be persisted (§6.6)
    assert CONF_MEALIE_TOKEN not in result["data"]
    assert CONF_MEALIE_URL not in result["data"]


# ─── B2 regression: rollback must not raise TypeError ────────────────────────


@pytest.mark.asyncio
async def test_rollback_no_type_error_on_network_failure(hass):
    """async_step_mealie_rollback must not raise TypeError (B2 from E2E review).

    Previously, CuliplanApiClient(self.hass, self._config_entry) was called
    with the wrong signature — it raised TypeError before any network call
    was made, causing the rollback to silently abort with 'rollback_failed'
    even though nothing was attempted. The line was removed; this test
    confirms the path degrades gracefully when the DELETE itself fails.
    """
    flow = _make_options_flow(
        {
            CONF_MEALIE_JOB_ID: "job-rollback-test",
            CONF_MEALIE_IMPORT_AT: int(time.time()) - 60,
            "access_token": "tok_access",
        },
        hass,
    )

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=Exception("simulated network error")
    )
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=mock_resp)

    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        # Must not raise TypeError; should abort with "rollback_failed"
        result = await flow.async_step_mealie_rollback()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "rollback_failed"
