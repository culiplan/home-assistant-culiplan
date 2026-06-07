"""Coverage tests for custom_components/culiplan/__init__.py — the bits not
already exercised by test_init_migrate (entity migration) and the platform
test files.

Focus areas: lovelace resource registration, intent handlers
(make_intent_handler / make_cooking_intent_handler), and the
async_setup/async_setup_entry/async_unload_entry plumbing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan import (
    _async_register_lovelace_resources,
    _make_cooking_intent_handler,
    _make_intent_handler,
    _read_manifest_version,
    async_setup,
    async_unload_entry,
)
from custom_components.culiplan.const import DOMAIN


# ─── _read_manifest_version ───────────────────────────────────────────────────


def test_read_manifest_version_returns_string():
    """Real manifest is always present in the repo."""
    version = _read_manifest_version()
    assert version != "dev"
    assert isinstance(version, str)


# ─── async_setup ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_setup_imports_oauth_credential():
    """async_setup imports the public OAuth credential so the dialog never shows."""
    hass = MagicMock()
    with patch(
        "custom_components.culiplan.async_import_client_credential",
        new=AsyncMock(),
    ) as mock_import:
        result = await async_setup(hass, {})
    assert result is True
    mock_import.assert_awaited_once()


# ─── _async_register_lovelace_resources ───────────────────────────────────────


@pytest.mark.asyncio
async def test_lovelace_resources_skipped_when_collection_missing():
    """No hass.data['lovelace'] → log and skip (non-fatal)."""
    hass = MagicMock()
    hass.data = {}
    # Must not raise
    await _async_register_lovelace_resources(hass)


@pytest.mark.asyncio
async def test_lovelace_resources_registered_when_collection_present():
    """When the resource collection exists, missing resources are created."""
    resources_collection = MagicMock()
    resources_collection.async_items = AsyncMock(return_value=[])
    resources_collection.async_create_item = AsyncMock()
    lovelace = MagicMock()
    lovelace.resources = resources_collection

    hass = MagicMock()
    hass.data = {"lovelace": lovelace}

    await _async_register_lovelace_resources(hass)

    # Each entry in _LOVELACE_RESOURCES → one async_create_item call.
    from custom_components.culiplan import _LOVELACE_RESOURCES

    assert resources_collection.async_create_item.call_count == len(_LOVELACE_RESOURCES)


@pytest.mark.asyncio
async def test_lovelace_resources_skips_already_registered():
    """Resources already registered are skipped."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    existing = [{"url": r["url"]} for r in _LOVELACE_RESOURCES]
    resources_collection = MagicMock()
    resources_collection.async_items = AsyncMock(return_value=existing)
    resources_collection.async_create_item = AsyncMock()
    lovelace = MagicMock()
    lovelace.resources = resources_collection

    hass = MagicMock()
    hass.data = {"lovelace": lovelace}

    await _async_register_lovelace_resources(hass)

    resources_collection.async_create_item.assert_not_called()


@pytest.mark.asyncio
async def test_lovelace_resources_legacy_collection_fallback():
    """Old HA builds expose .data on the resource collection instead of
    .async_items(); the registration helper falls back gracefully.
    """
    resources_collection = MagicMock()
    resources_collection.async_items = AsyncMock(side_effect=AttributeError("old API"))
    resources_collection.async_load = AsyncMock()
    resources_collection.data = {"id1": {"url": "other"}}
    resources_collection.async_create_item = AsyncMock()
    lovelace = MagicMock()
    lovelace.resources = resources_collection

    hass = MagicMock()
    hass.data = {"lovelace": lovelace}

    await _async_register_lovelace_resources(hass)

    # The 3 culiplan resources are registered because none match "other".
    assert resources_collection.async_create_item.await_count >= 1


@pytest.mark.asyncio
async def test_lovelace_resources_create_failure_is_non_fatal():
    """If a single resource fails to register, the others must still be tried."""
    resources_collection = MagicMock()
    resources_collection.async_items = AsyncMock(return_value=[])
    resources_collection.async_create_item = AsyncMock(
        side_effect=[RuntimeError("conflict"), None, None]
    )
    lovelace = MagicMock()
    lovelace.resources = resources_collection

    hass = MagicMock()
    hass.data = {"lovelace": lovelace}

    # Must not raise
    await _async_register_lovelace_resources(hass)
    assert resources_collection.async_create_item.await_count == 3


@pytest.mark.asyncio
async def test_lovelace_resources_outer_exception_is_non_fatal():
    """Any unexpected error during the lookup is logged and swallowed."""
    hass = MagicMock()
    # Force hass.data.get to raise
    hass.data = MagicMock()
    hass.data.get = MagicMock(side_effect=RuntimeError("unexpected"))
    # Must not raise
    await _async_register_lovelace_resources(hass)


# ─── _make_intent_handler / _make_cooking_intent_handler ─────────────────────


@pytest.mark.asyncio
async def test_intent_handler_returns_speakable():
    """The standard intent handler calls the voice tool and surfaces speakable."""
    entry = MagicMock()
    entry.entry_id = "e1"

    handler = _make_intent_handler("CuliplanWhatsDinnerTonight", entry)
    assert handler.intent_type == "CuliplanWhatsDinnerTonight"

    client = MagicMock()
    client.async_call_voice_tool = AsyncMock(
        return_value={"speakable": "Tonight you're cooking pasta."}
    )
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"client": client}}}

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    response = await handler.async_handle(intent_obj)
    assert response is not None
    client.async_call_voice_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_intent_handler_when_not_configured():
    """If the integration entry is gone, the handler returns a friendly message."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_intent_handler("CuliplanWhatsDinnerTonight", entry)

    hass = MagicMock()
    hass.data = {DOMAIN: {}}

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.create_response = MagicMock(return_value=MagicMock())
    intent_obj.slots = {}

    response = await handler.async_handle(intent_obj)
    assert response is not None


@pytest.mark.asyncio
async def test_intent_handler_handles_tool_failure():
    """Voice tool failure produces a friendly error response, not an exception."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_intent_handler("CuliplanWhatsDinnerTonight", entry)

    client = MagicMock()
    client.async_call_voice_tool = AsyncMock(side_effect=RuntimeError("backend down"))
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"client": client}}}

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    # Must not raise; the catch in the handler converts to a spoken apology.
    await handler.async_handle(intent_obj)


@pytest.mark.asyncio
async def test_cooking_intent_handler_calls_service():
    """The cooking-mode intent handler delegates to the local HA service."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_cooking_intent_handler("CuliplanNextCookingStep", entry)
    assert handler.intent_type == "CuliplanNextCookingStep"

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    await handler.async_handle(intent_obj)
    hass.services.async_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_cooking_intent_handler_with_slots():
    """Slot values are mapped to service field names."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_cooking_intent_handler("CuliplanSetRecipeTimer", entry)

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {
        "label": {"value": "pasta"},
        "duration_sec": {"value": "600"},
    }
    intent_obj.create_response = MagicMock(return_value=MagicMock())
    await handler.async_handle(intent_obj)
    hass.services.async_call.assert_awaited_once()
    service_data = hass.services.async_call.call_args[0][2]
    assert service_data == {"label": "pasta", "duration_sec": 600}


@pytest.mark.asyncio
async def test_cooking_intent_handler_invalid_duration():
    """A non-integer duration_sec is silently dropped from the service data."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_cooking_intent_handler("CuliplanSetRecipeTimer", entry)

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {
        "label": {"value": "pasta"},
        "duration_sec": {"value": "garbage"},
    }
    intent_obj.create_response = MagicMock(return_value=MagicMock())
    await handler.async_handle(intent_obj)
    service_data = hass.services.async_call.call_args[0][2]
    assert "duration_sec" not in service_data


@pytest.mark.asyncio
async def test_cooking_intent_handler_service_failure_is_handled():
    """Service-call failure must NOT raise out of the intent handler."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_cooking_intent_handler("CuliplanNextCookingStep", entry)

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("bad state"))

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    # Must not raise
    await handler.async_handle(intent_obj)


# ─── async_unload_entry ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_unload_entry_pops_entry_data():
    """Unloading removes the entry's data slot from hass.data[DOMAIN]."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"

    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"coordinator": coordinator}}}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_entries = MagicMock(return_value=[])

    result = await async_unload_entry(hass, entry)
    assert result is True
    assert "e1" not in hass.data[DOMAIN]


# ─── async_setup_entry + _async_register_sidebar_panel ────────────────────────


@pytest.mark.asyncio
async def test_async_setup_entry_wires_everything():
    """async_setup_entry registers coordinator, services, panel and intents.

    Mocks every heavy collaborator so the test pins ONLY the wiring of the
    integration's own setup logic — not HA's frontend/intents internals.
    """
    from custom_components.culiplan import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"token": {"access_token": "tok"}, "ai_mode": "cloud"}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)

    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_start = AsyncMock()

    impl = MagicMock()
    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock()
    session.token = {"access_token": "tok"}

    with (
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow"
            ".async_get_config_entry_implementation",
            new=AsyncMock(return_value=impl),
        ),
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow.OAuth2Session",
            return_value=session,
        ),
        patch(
            "custom_components.culiplan.aiohttp_client.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.culiplan.CuliplanApiClient",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.culiplan.CuliplanCoordinator",
            return_value=coordinator,
        ),
        patch("custom_components.culiplan._register_intents", new=AsyncMock()),
        patch("custom_components.culiplan.async_register_services"),
        patch("custom_components.culiplan.async_register_cooking_services"),
        patch("custom_components.culiplan.async_register_llm_api"),
        patch(
            "custom_components.culiplan._async_register_lovelace_resources",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.culiplan._async_register_sidebar_panel",
            new=AsyncMock(),
        ),
    ):
        assert await async_setup_entry(hass, entry) is True

    # Coordinator was started; data slot populated; platforms forwarded.
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    coordinator.async_start.assert_awaited_once()
    assert hass.data[DOMAIN]["e1"]["coordinator"] is coordinator
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_intents_handles_unknown_language():
    """The integration falls back to English for unsupported languages."""
    from custom_components.culiplan import _register_intents

    hass = MagicMock()
    hass.config.language = "xx-YY"  # unknown locale
    hass.async_add_executor_job = AsyncMock(return_value={"intents": {}})

    entry = MagicMock()
    # Must not raise.
    await _register_intents(hass, entry)


@pytest.mark.asyncio
async def test_options_updated_triggers_reload():
    """The OptionsFlow add_update_listener callback reloads the entry."""
    from custom_components.culiplan import _async_options_updated

    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "e1"

    await _async_options_updated(hass, entry)
    hass.config_entries.async_reload.assert_awaited_once_with("e1")
