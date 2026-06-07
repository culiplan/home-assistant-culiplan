"""Additional config-flow coverage focused on the OptionsFlow Advanced AI
sub-flow and the self-updater wizard reachable from the Options form.

The Mealie offer / import wizard is covered by test_mealie_config_flow.py;
this file covers the rest.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.data_entry_flow import FlowResultType


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_options_flow(hass, entry_data: dict | None = None, options: dict | None = None):
    from custom_components.culiplan.config_flow import MealieOptionsFlow

    entry = MagicMock()
    entry.data = entry_data or {}
    entry.options = options or {}
    flow = MealieOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass
    return flow


# ─── Advanced AI sub-flow ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_advanced_ai_toggle_routes_to_advanced_ai_step(hass):
    """Submitting Advanced AI toggle moves into async_step_advanced_ai."""
    from custom_components.culiplan.config_flow import CONF_ADVANCED_AI

    flow = _make_options_flow(hass, entry_data={"ai_mode": "cloud"})
    with patch(
        "custom_components.culiplan.config_flow.probe_local_ai_endpoints",
        new=AsyncMock(return_value=[]),
    ):
        result = await flow.async_step_init(user_input={CONF_ADVANCED_AI: True})

    # Lands on the advanced_ai form (next sub-step)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai"


@pytest.mark.asyncio
async def test_advanced_ai_cloud_creates_entry_immediately(hass):
    """Cloud AI submission commits — no further sub-steps."""
    from custom_components.culiplan.config_flow import AI_MODE_CLOUD, CONF_AI_MODE

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {"expiry_days": 3, "expiry_hours": 48, "debug_ai": False}
    result = await flow.async_step_advanced_ai(
        user_input={CONF_AI_MODE: AI_MODE_CLOUD}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_CLOUD


@pytest.mark.asyncio
async def test_advanced_ai_byok_routes_to_byok_step(hass):
    """BYOK selection moves into the advanced_ai_byok step."""
    from custom_components.culiplan.config_flow import AI_MODE_BYOK, CONF_AI_MODE

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    result = await flow.async_step_advanced_ai(
        user_input={CONF_AI_MODE: AI_MODE_BYOK}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai_byok"


@pytest.mark.asyncio
async def test_advanced_ai_local_routes_to_local_step(hass):
    """Local AI selection moves into the advanced_ai_local step."""
    from custom_components.culiplan.config_flow import AI_MODE_LOCAL, CONF_AI_MODE

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    flow._detected_endpoints = []
    result = await flow.async_step_advanced_ai(
        user_input={CONF_AI_MODE: AI_MODE_LOCAL}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai_local"


# ─── Update wizard ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_step_up_to_date(hass):
    """If the manifest matches the latest release, abort with up_to_date."""
    from custom_components.culiplan.config_flow import _MANIFEST_VERSION
    from custom_components.culiplan.updater import LatestRelease

    flow = _make_options_flow(hass)
    release = LatestRelease(
        version=_MANIFEST_VERSION,
        zipball_url="https://example.test/z.zip",
        html_url="https://example.test/r",
        notes="",
    )
    with patch(
        "custom_components.culiplan.config_flow.async_check_latest",
        new=AsyncMock(return_value=release),
    ):
        result = await flow.async_step_update()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "up_to_date"


@pytest.mark.asyncio
async def test_update_step_check_failed(hass):
    """If GitHub is unreachable, abort with update_check_failed."""
    flow = _make_options_flow(hass)
    with patch(
        "custom_components.culiplan.config_flow.async_check_latest",
        new=AsyncMock(return_value=None),
    ):
        result = await flow.async_step_update()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "update_check_failed"


@pytest.mark.asyncio
async def test_update_step_newer_version_shows_form(hass):
    """A newer version shows the confirmation form with version metadata."""
    from custom_components.culiplan.updater import LatestRelease

    flow = _make_options_flow(hass)
    release = LatestRelease(
        version="99.99.99",
        zipball_url="https://example.test/z.zip",
        html_url="https://example.test/r",
        notes="Massive update",
    )
    with patch(
        "custom_components.culiplan.config_flow.async_check_latest",
        new=AsyncMock(return_value=release),
    ):
        result = await flow.async_step_update()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "update"
    assert "99.99.99" in str(result.get("description_placeholders", {}).get("latest"))


@pytest.mark.asyncio
async def test_update_step_user_declines(hass):
    """If the user submits confirm=False, abort with no_action."""
    flow = _make_options_flow(hass)
    result = await flow.async_step_update(user_input={"confirm": False})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_action"


@pytest.mark.asyncio
async def test_update_step_no_pending_release_aborts(hass):
    """If the user submits confirm=True but no pending release is stashed,
    abort with update_check_failed (defensive guard).
    """
    flow = _make_options_flow(hass)
    flow._pending_update = None
    result = await flow.async_step_update(user_input={"confirm": True})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "update_check_failed"


@pytest.mark.asyncio
async def test_update_step_perform_update_failure_re_shows_form(hass):
    """A failure during async_perform_update re-shows the form with the error."""
    from custom_components.culiplan.updater import LatestRelease

    flow = _make_options_flow(hass)
    flow._pending_update = LatestRelease(
        version="99.99.99",
        zipball_url="https://example.test/z.zip",
        html_url="https://example.test/r",
        notes="",
    )
    with patch(
        "custom_components.culiplan.config_flow.async_perform_update",
        new=AsyncMock(side_effect=RuntimeError("zipfile broken")),
    ):
        result = await flow.async_step_update(user_input={"confirm": True})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "update"
    assert "base" in result.get("errors", {})


@pytest.mark.asyncio
async def test_update_step_success_starts_restart(hass):
    """A successful update schedules a delayed HA restart and aborts."""
    from custom_components.culiplan.updater import LatestRelease

    flow = _make_options_flow(hass)
    flow._pending_update = LatestRelease(
        version="99.99.99",
        zipball_url="https://example.test/z.zip",
        html_url="https://example.test/r",
        notes="",
    )
    with patch(
        "custom_components.culiplan.config_flow.async_perform_update",
        new=AsyncMock(),
    ):
        # async_create_task schedules a background _restart() coroutine that
        # sleeps 2s before calling homeassistant.restart. Patch the create_task
        # helper so we don't actually wait or fire the restart in the test.
        with patch.object(flow.hass, "async_create_task") as create_task:
            result = await flow.async_step_update(user_input={"confirm": True})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "update_started"
    create_task.assert_called_once()


# ─── _parse_local_endpoint ───────────────────────────────────────────────────


class TestParseLocalEndpoint:
    """The helper turns user-typed endpoints into (host, port)."""

    def _parse(self, endpoint):
        from custom_components.culiplan.config_flow import _parse_local_endpoint

        return _parse_local_endpoint(endpoint)

    def test_full_url(self):
        assert self._parse("http://localhost:11434") == ("localhost", "11434")

    def test_host_port_no_scheme(self):
        assert self._parse("localhost:11434") == ("localhost", "11434")

    def test_with_path(self):
        assert self._parse("http://192.168.1.50:11434/v1") == ("192.168.1.50", "11434")

    def test_no_port_raises(self):
        from custom_components.culiplan.config_flow import _parse_local_endpoint

        with pytest.raises(ValueError):
            _parse_local_endpoint("http://localhost")


# ─── async_step_ai_local (config flow) ───────────────────────────────────────


def _make_oauth_flow(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = {"token": {"access_token": "tok"}}
    flow._entry_data = {**flow._oauth_data, "ai_mode": "local"}
    flow._detected_endpoints = []
    return flow


@pytest.mark.asyncio
async def test_ai_local_step_shows_form_when_no_input(hass):
    flow = _make_oauth_flow(hass)
    result = await flow.async_step_ai_local()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "ai_local"


@pytest.mark.asyncio
async def test_ai_local_step_unreachable_endpoint_shows_error(hass):
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_oauth_flow(hass)
    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        new=AsyncMock(return_value=None),
    ):
        result = await flow.async_step_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "http://192.168.1.50:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert CONF_LOCAL_ENDPOINT in result.get("errors", {})


@pytest.mark.asyncio
async def test_ai_local_step_invalid_endpoint_format_error(hass):
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_oauth_flow(hass)
    result = await flow.async_step_ai_local(
        user_input={CONF_LOCAL_ENDPOINT: "http://no-port", CONF_LOCAL_MODEL: ""}
    )
    assert result["type"] == FlowResultType.FORM
    assert "errors" in result


@pytest.mark.asyncio
async def test_ai_local_step_remote_endpoint_triggers_warning(hass):
    """A non-loopback endpoint diverts to async_step_local_endpoint_remote_warning."""
    from custom_components.culiplan.ai.local_ai import LocalAIEndpoint
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_oauth_flow(hass)
    probed = LocalAIEndpoint(
        host="192.168.1.50", port=11434, provider="ollama", available_models=["llama3.2"]
    )
    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        new=AsyncMock(return_value=probed),
    ):
        result = await flow.async_step_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "http://192.168.1.50:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )
    # Routed into the remote-warning step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local_endpoint_remote_warning"


@pytest.mark.asyncio
async def test_local_endpoint_remote_warning_confirm_continues(hass):
    """Confirming the warning continues to the mealie offer."""
    flow = _make_oauth_flow(hass)
    flow._entry_data["local_endpoint"] = "http://192.168.1.50:11434"

    # mealie_offer self-skips without a Mealie entry → returns CREATE_ENTRY.
    result = await flow.async_step_local_endpoint_remote_warning(
        user_input={"confirm_remote": True}
    )
    # mealie_offer skipped because no Mealie entries → entry created.
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_local_endpoint_remote_warning_form_shown_with_no_input(hass):
    """Without user input, the warning step shows its form."""
    flow = _make_oauth_flow(hass)
    flow._entry_data["local_endpoint"] = "http://192.168.1.50:11434"
    result = await flow.async_step_local_endpoint_remote_warning()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local_endpoint_remote_warning"


# ─── async_step_ai_byok validation (defaults / error paths) ──────────────────


@pytest.mark.asyncio
async def test_ai_byok_step_missing_key_shows_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_oauth_flow(hass)
    result = await flow.async_step_ai_byok(
        user_input={CONF_BYOK_PROVIDER: "openai", CONF_BYOK_API_KEY: ""}
    )
    assert result["type"] == FlowResultType.FORM
    assert "errors" in result
    assert CONF_BYOK_API_KEY in result["errors"]


@pytest.mark.asyncio
async def test_ai_byok_step_missing_provider_shows_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_oauth_flow(hass)
    result = await flow.async_step_ai_byok(
        user_input={CONF_BYOK_PROVIDER: "", CONF_BYOK_API_KEY: "sk-test"}
    )
    assert result["type"] == FlowResultType.FORM
    assert CONF_BYOK_PROVIDER in result.get("errors", {})


@pytest.mark.asyncio
async def test_ai_byok_step_unexpected_error_shows_base_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_oauth_flow(hass)
    with patch(
        "custom_components.culiplan.config_flow.validate_byok_key",
        new=AsyncMock(side_effect=RuntimeError("unexpected")),
    ):
        result = await flow.async_step_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-test",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert "base" in result.get("errors", {})


# ─── async_step_reauth ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_step_reauth_routes_to_confirm(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    result = await flow.async_step_reauth()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


# ─── async_step_advanced_ai_byok / advanced_ai_local (Options flow) ──────────


@pytest.mark.asyncio
async def test_advanced_ai_byok_valid_creates_entry(hass):
    """A valid BYOK key in the Options flow commits."""
    from custom_components.culiplan.const import (
        AI_MODE_BYOK,
        CONF_AI_MODE,
        CONF_BYOK_API_KEY,
        CONF_BYOK_PROVIDER,
    )

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {"expiry_days": 3, "expiry_hours": 48, "debug_ai": False}
    with (
        patch(
            "custom_components.culiplan.config_flow.validate_byok_key",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.culiplan.config_flow.BYOKKeyStore"
        ) as MockKeyStore,
    ):
        store = MagicMock()
        store.async_load = AsyncMock()
        store.async_set_key = AsyncMock()
        MockKeyStore.return_value = store
        result = await flow.async_step_advanced_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-test",
            }
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_BYOK
    assert result["data"][CONF_BYOK_PROVIDER] == "openai"
    assert CONF_BYOK_API_KEY not in result["data"]


@pytest.mark.asyncio
async def test_advanced_ai_byok_invalid_shows_error(hass):
    from custom_components.culiplan.ai.types import ProviderAuthError
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    with patch(
        "custom_components.culiplan.config_flow.validate_byok_key",
        new=AsyncMock(side_effect=ProviderAuthError("bad key")),
    ):
        result = await flow.async_step_advanced_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-bad",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert CONF_BYOK_API_KEY in result.get("errors", {})


@pytest.mark.asyncio
async def test_advanced_ai_local_loopback_commits_immediately(hass):
    """A loopback local endpoint commits without the remote-warning step."""
    from custom_components.culiplan.ai.local_ai import LocalAIEndpoint
    from custom_components.culiplan.const import (
        AI_MODE_LOCAL,
        CONF_AI_MODE,
        CONF_LOCAL_ENDPOINT,
        CONF_LOCAL_MODEL,
    )

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {"expiry_days": 3, "expiry_hours": 48, "debug_ai": False}
    flow._detected_endpoints = []
    probed = LocalAIEndpoint(
        host="localhost", port=11434, provider="ollama", available_models=["llama3.2"]
    )
    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        new=AsyncMock(return_value=probed),
    ):
        result = await flow.async_step_advanced_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "http://localhost:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_LOCAL


@pytest.mark.asyncio
async def test_advanced_ai_local_remote_routes_to_warning(hass):
    from custom_components.culiplan.ai.local_ai import LocalAIEndpoint
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    flow._detected_endpoints = []
    probed = LocalAIEndpoint(
        host="192.168.1.50", port=11434, provider="ollama", available_models=["llama3.2"]
    )
    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        new=AsyncMock(return_value=probed),
    ):
        result = await flow.async_step_advanced_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "http://192.168.1.50:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced_ai_local_remote_warning"


@pytest.mark.asyncio
async def test_advanced_ai_local_invalid_endpoint_shows_error(hass):
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    result = await flow.async_step_advanced_ai_local(
        user_input={CONF_LOCAL_ENDPOINT: "http://no-port", CONF_LOCAL_MODEL: ""}
    )
    assert result["type"] == FlowResultType.FORM
    assert CONF_LOCAL_ENDPOINT in result.get("errors", {})


@pytest.mark.asyncio
async def test_advanced_ai_local_unreachable_shows_error(hass):
    from custom_components.culiplan.const import CONF_LOCAL_ENDPOINT, CONF_LOCAL_MODEL

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    flow._detected_endpoints = []
    with patch(
        "custom_components.culiplan.config_flow.probe_custom_endpoint",
        new=AsyncMock(return_value=None),
    ):
        result = await flow.async_step_advanced_ai_local(
            user_input={
                CONF_LOCAL_ENDPOINT: "http://localhost:11434",
                CONF_LOCAL_MODEL: "llama3.2",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert CONF_LOCAL_ENDPOINT in result.get("errors", {})


@pytest.mark.asyncio
async def test_advanced_ai_local_remote_warning_confirm_commits(hass):
    from custom_components.culiplan.const import (
        AI_MODE_LOCAL,
        CONF_AI_MODE,
        CONF_LOCAL_ENDPOINT,
    )

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {
        CONF_LOCAL_ENDPOINT: "http://192.168.1.50:11434",
    }
    result = await flow.async_step_advanced_ai_local_remote_warning(
        user_input={"confirmed": True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AI_MODE] == AI_MODE_LOCAL


# ─── Reconfigure path (Gold rule `reconfiguration-flow`) ─────────────────────


@pytest.mark.asyncio
async def test_reconfigure_wrong_account_aborts(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    existing = MagicMock()
    existing.unique_id = "account-A"
    existing.data = {}
    hass.config_entries.async_get_entry = MagicMock(return_value=existing)
    flow.context = {"entry_id": "e1"}

    result = await flow._async_finish_reconfigure(
        data={"token": {"access_token": "tok"}},
        culiplan_account_id="account-B",
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


@pytest.mark.asyncio
async def test_reconfigure_matching_account_updates_entry(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    existing = MagicMock()
    existing.unique_id = "account-A"
    existing.data = {"ai_mode": "byok"}
    hass.config_entries.async_get_entry = MagicMock(return_value=existing)
    # async_update_reload_and_abort returns a dict — patch it via flow attr
    flow.context = {"entry_id": "e1", "user_id": "ha-user-1"}
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": FlowResultType.ABORT, "reason": "reauth_successful"}
    )
    flow.async_set_unique_id = AsyncMock()

    result = await flow._async_finish_reconfigure(
        data={"token": {"access_token": "tok2"}},
        culiplan_account_id="account-A",
    )
    assert result["type"] == FlowResultType.ABORT
    flow.async_update_reload_and_abort.assert_called_once()


@pytest.mark.asyncio
async def test_reconfigure_falls_back_to_new_entry_when_existing_missing(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    flow.context = {"entry_id": "missing"}
    flow.async_set_unique_id = AsyncMock()

    # mealie_offer self-skips → create_entry
    result = await flow._async_finish_reconfigure(
        data={"token": {"access_token": "tok"}},
        culiplan_account_id=None,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_async_step_reconfigure_delegates_to_user(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow.async_step_user = AsyncMock(
        return_value={"type": FlowResultType.FORM, "step_id": "pick_implementation"}
    )
    result = await flow.async_step_reconfigure()
    assert result["step_id"] == "pick_implementation"


# ─── _call_migrate_preview / _call_migrate_start ─────────────────────────────


@pytest.mark.asyncio
async def test_call_migrate_preview_returns_json(hass):
    from custom_components.culiplan.config_flow import _call_migrate_preview

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={"willImport": 5})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=session,
    ):
        result = await _call_migrate_preview(
            hass,
            {"access_token": "tok"},
            "http://mealie.local",
            "tok-mealie",
        )
    assert result == {"willImport": 5}


@pytest.mark.asyncio
async def test_call_migrate_start_returns_json(hass):
    from custom_components.culiplan.config_flow import _call_migrate_start

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={"jobId": "j1", "errors": 0})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=session,
    ):
        result = await _call_migrate_start(
            hass,
            {"access_token": "tok"},
            "http://mealie.local",
            "tok-mealie",
        )
    assert result["jobId"] == "j1"


# ─── _fetch_culiplan_account_id ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_culiplan_account_id_happy_path(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={"id": "user-42"})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=session,
    ):
        result = await flow._fetch_culiplan_account_id(
            {"token": {"access_token": "tok"}}
        )
    assert result == "user-42"


@pytest.mark.asyncio
async def test_fetch_culiplan_account_id_no_token_returns_none(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    result = await flow._fetch_culiplan_account_id({})
    assert result is None


@pytest.mark.asyncio
async def test_fetch_culiplan_account_id_non_200_returns_none(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    resp = MagicMock()
    resp.status = 503
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=session,
    ):
        result = await flow._fetch_culiplan_account_id(
            {"token": {"access_token": "tok"}}
        )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_culiplan_account_id_network_error_returns_none(hass):
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass
    session = MagicMock()
    session.get = MagicMock(side_effect=RuntimeError("boom"))
    with patch(
        "custom_components.culiplan.config_flow.aiohttp_client.async_get_clientsession",
        return_value=session,
    ):
        result = await flow._fetch_culiplan_account_id(
            {"token": {"access_token": "tok"}}
        )
    assert result is None


# ─── More Options/BYOK form rendering ────────────────────────────────────────


@pytest.mark.asyncio
async def test_advanced_ai_byok_missing_provider_shows_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    result = await flow.async_step_advanced_ai_byok(
        user_input={CONF_BYOK_PROVIDER: "", CONF_BYOK_API_KEY: "sk-test"}
    )
    assert result["type"] == FlowResultType.FORM
    assert CONF_BYOK_PROVIDER in result.get("errors", {})


@pytest.mark.asyncio
async def test_advanced_ai_byok_missing_key_shows_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    result = await flow.async_step_advanced_ai_byok(
        user_input={CONF_BYOK_PROVIDER: "openai", CONF_BYOK_API_KEY: ""}
    )
    assert result["type"] == FlowResultType.FORM
    assert CONF_BYOK_API_KEY in result.get("errors", {})


@pytest.mark.asyncio
async def test_advanced_ai_byok_unexpected_error_base_error(hass):
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = _make_options_flow(hass)
    flow._advanced_ai_data = {}
    with patch(
        "custom_components.culiplan.config_flow.validate_byok_key",
        new=AsyncMock(side_effect=RuntimeError("unexpected")),
    ):
        result = await flow.async_step_advanced_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-test",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert "base" in result.get("errors", {})


# ─── ai_byok step (initial config flow) extra coverage ───────────────────────


@pytest.mark.asyncio
async def test_ai_byok_invalid_key_shows_form_error(hass):
    from custom_components.culiplan.ai.types import ProviderAuthError
    from custom_components.culiplan.config_flow import OAuth2FlowHandler
    from custom_components.culiplan.const import CONF_BYOK_API_KEY, CONF_BYOK_PROVIDER

    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow._oauth_data = {"token": {"access_token": "tok"}}
    flow._entry_data = {**flow._oauth_data, "ai_mode": "byok"}

    with patch(
        "custom_components.culiplan.config_flow.validate_byok_key",
        new=AsyncMock(side_effect=ProviderAuthError("nope")),
    ):
        result = await flow.async_step_ai_byok(
            user_input={
                CONF_BYOK_PROVIDER: "openai",
                CONF_BYOK_API_KEY: "sk-bad",
            }
        )
    assert result["type"] == FlowResultType.FORM
    assert CONF_BYOK_API_KEY in result.get("errors", {})


# ─── async_step_pick_implementation (ensures credential is imported) ─────────


@pytest.mark.asyncio
async def test_async_step_user_imports_credential(hass):
    """async_step_user re-ensures the credential is registered before OAuth."""
    from custom_components.culiplan.config_flow import OAuth2FlowHandler

    flow = OAuth2FlowHandler()
    flow.hass = hass

    with (
        patch(
            "homeassistant.components.application_credentials.async_import_client_credential",
            new=AsyncMock(),
        ) as imp,
        # super().async_step_user is the OAuth2 base — stub it out so we
        # don't try to launch a real redirect.
        patch.object(
            type(flow).__mro__[1],
            "async_step_user",
            new=AsyncMock(
                return_value={"type": FlowResultType.FORM, "step_id": "pick_implementation"}
            ),
        ),
    ):
        result = await flow.async_step_user()
    imp.assert_awaited_once()
    assert result["step_id"] == "pick_implementation"
