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
    async_setup,
    async_unload_entry,
)
from custom_components.culiplan.const import DOMAIN, _read_manifest_version


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


class _FakeResourceCollection:
    """Mirrors homeassistant.components.lovelace.resources.ResourceStorageCollection.

    The parts of the real contract that matter here — and that the original
    implementation got wrong, which is how it shipped a bug that grew one
    reporter's instance to 1398 resource rows:

      * ``async_items()`` is a SYNC ``@callback`` returning ``list(data.values())``.
        Awaiting it raises ``TypeError``.
      * ``async_load()`` takes NO arguments. Calling ``async_load(True)`` raises
        ``TypeError``.
      * ``async_load()`` does not itself set ``.loaded``; ``_async_ensure_loaded``
        does, and every public mutator calls it.
      * Stored items are dicts carrying ``id`` / ``url`` / ``type``.
    """

    def __init__(self, stored=None, *, load_error: Exception | None = None) -> None:
        self._stored = list(stored or [])
        self.data: dict[str, dict] = {}
        self.loaded = False
        self.load_error = load_error
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self._counter = 0

    async def async_load(self) -> None:
        if self.load_error is not None:
            raise self.load_error
        for item in self._stored:
            self.data[item["id"]] = item

    async def async_get_info(self) -> dict[str, int]:
        if not self.loaded:
            await self.async_load()
            self.loaded = True
        return {"resources": len(self.data)}

    def async_items(self) -> list[dict]:
        """Sync, exactly like the real @callback."""
        return list(self.data.values())

    async def async_create_item(self, data: dict) -> dict:
        await self.async_get_info()
        self._counter += 1
        item = {
            "id": f"gen{self._counter}",
            "url": data["url"],
            "type": data["res_type"],
        }
        self.data[item["id"]] = item
        self.created.append(item)
        return item

    async def async_delete_item(self, item_id: str) -> None:
        await self.async_get_info()
        self.data.pop(item_id, None)
        self.deleted.append(item_id)


def _hass_with(collection) -> MagicMock:
    lovelace = MagicMock()
    lovelace.resources = collection
    hass = MagicMock()
    hass.data = {"lovelace": lovelace}
    return hass


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
    from custom_components.culiplan import _LOVELACE_RESOURCES

    collection = _FakeResourceCollection()
    await _async_register_lovelace_resources(_hass_with(collection))

    assert len(collection.created) == len(_LOVELACE_RESOURCES)
    assert {c["url"] for c in collection.created} == {
        r["url"] for r in _LOVELACE_RESOURCES
    }


@pytest.mark.asyncio
async def test_lovelace_resources_urls_are_self_served():
    """Cards must be served from the integration's own static path.

    /hacsfiles/culiplan/... only exists for HACS *plugin* repos. HACS installs
    an integration by copying custom_components/<domain>/ alone, so those URLs
    404'd on every dashboard load.
    """
    from custom_components.culiplan import _LOVELACE_RESOURCES

    for resource in _LOVELACE_RESOURCES:
        assert resource["url"].startswith("/culiplan_static/cards/"), resource["url"]


@pytest.mark.asyncio
async def test_lovelace_resource_files_exist_on_disk():
    """Every registered URL must map to a file shipped inside the package."""
    from pathlib import Path

    import custom_components.culiplan as init_mod
    from custom_components.culiplan import _LOVELACE_RESOURCES

    frontend = Path(init_mod.__file__).parent / "frontend"
    for resource in _LOVELACE_RESOURCES:
        rel = resource["url"].removeprefix("/culiplan_static/")
        assert (frontend / rel).is_file(), f"missing bundle for {resource['url']}"


@pytest.mark.asyncio
async def test_lovelace_resources_skips_already_registered():
    """Resources already registered are skipped."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    stored = [
        {"id": f"e{i}", "url": r["url"], "type": "module"}
        for i, r in enumerate(_LOVELACE_RESOURCES)
    ]
    collection = _FakeResourceCollection(stored)
    await _async_register_lovelace_resources(_hass_with(collection))

    assert collection.created == []
    assert collection.deleted == []


@pytest.mark.asyncio
async def test_lovelace_resources_do_not_accumulate_across_restarts():
    """Regression: repeated setups must not append a new row every time.

    The original code awaited the sync ``async_items()`` and then called
    ``async_load(True)``; both raised TypeError and the bare ``except`` left
    "existing" empty, so every startup registered three more rows with fresh
    UUIDs. 466 restarts → 1398 resources.
    """
    from custom_components.culiplan import _LOVELACE_RESOURCES

    collection = _FakeResourceCollection()
    hass = _hass_with(collection)

    for _ in range(5):
        await _async_register_lovelace_resources(hass)

    assert len(collection.data) == len(_LOVELACE_RESOURCES)
    assert len(collection.created) == len(_LOVELACE_RESOURCES)


@pytest.mark.asyncio
async def test_lovelace_resources_fail_closed_when_existing_unreadable():
    """If the existing set cannot be read, register nothing.

    Assuming "nothing is registered" is what produced the duplicate pile-up,
    so an unreadable collection must skip rather than guess.
    """
    collection = _FakeResourceCollection(load_error=RuntimeError("storage on fire"))
    await _async_register_lovelace_resources(_hass_with(collection))

    assert collection.created == []
    assert collection.deleted == []


@pytest.mark.asyncio
async def test_lovelace_resources_never_awaits_async_items():
    """async_items() is a sync @callback — awaiting it must not happen.

    A collection whose async_items() is sync-only (the real shape) still
    produces a correct read; if the code awaited it, the TypeError would trip
    the fail-closed path and create nothing.
    """
    from custom_components.culiplan import _LOVELACE_RESOURCES

    collection = _FakeResourceCollection()
    await _async_register_lovelace_resources(_hass_with(collection))
    assert len(collection.created) == len(_LOVELACE_RESOURCES)


@pytest.mark.asyncio
async def test_lovelace_resources_removes_stale_hacsfiles_rows():
    """Dead /hacsfiles/culiplan/... rows from earlier versions are cleaned up."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    stale = [
        {
            "id": f"old{i}",
            "url": f"/hacsfiles/culiplan/lovelace/cards/dist/{name}.js",
            "type": "module",
        }
        for i, name in enumerate(
            ["kitchen-dashboard", "pantry-tracker", "cooking-mode"]
        )
    ]
    keep = {"id": "mine", "url": "/local/my-own-card.js", "type": "module"}
    collection = _FakeResourceCollection([*stale, keep])

    await _async_register_lovelace_resources(_hass_with(collection))

    assert set(collection.deleted) == {"old0", "old1", "old2"}
    # The user's unrelated resource is untouched...
    assert "mine" in collection.data
    # ...and the three current URLs are now registered exactly once each.
    assert len(collection.created) == len(_LOVELACE_RESOURCES)
    urls = [item["url"] for item in collection.data.values()]
    for resource in _LOVELACE_RESOURCES:
        assert urls.count(resource["url"]) == 1


@pytest.mark.asyncio
async def test_lovelace_resources_collapses_existing_duplicates():
    """An instance that already piled up duplicates is repaired to one row each."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    target = _LOVELACE_RESOURCES[0]["url"]
    stored = [{"id": f"dup{i}", "url": target, "type": "module"} for i in range(20)]
    collection = _FakeResourceCollection(stored)

    await _async_register_lovelace_resources(_hass_with(collection))

    remaining = [i for i in collection.data.values() if i["url"] == target]
    assert len(remaining) == 1
    assert len(collection.deleted) == 19


@pytest.mark.asyncio
async def test_lovelace_resources_create_failure_is_non_fatal():
    """If a single resource fails to register, the others must still be tried."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    collection = _FakeResourceCollection()
    attempted: list[str] = []
    real_create = collection.async_create_item

    async def _flaky(data):
        attempted.append(data["url"])
        if len(attempted) == 1:
            raise RuntimeError("conflict")
        return await real_create(data)

    collection.async_create_item = _flaky

    # Must not raise
    await _async_register_lovelace_resources(_hass_with(collection))
    assert len(attempted) == len(_LOVELACE_RESOURCES)


@pytest.mark.asyncio
async def test_lovelace_resources_delete_failure_is_non_fatal():
    """A failed stale-row delete must not stop the rest of registration."""
    from custom_components.culiplan import _LOVELACE_RESOURCES

    collection = _FakeResourceCollection(
        [
            {
                "id": "old0",
                "url": "/hacsfiles/culiplan/lovelace/cards/dist/cooking-mode.js",
                "type": "module",
            }
        ]
    )

    async def _boom(item_id):
        raise RuntimeError("cannot delete")

    collection.async_delete_item = _boom

    # Must not raise, and the current resources still get registered.
    await _async_register_lovelace_resources(_hass_with(collection))
    assert len(collection.created) == len(_LOVELACE_RESOURCES)


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
    """The standard intent handler runs the tool on /voice/execute and speaks
    the backend's speakableResponse."""
    entry = MagicMock()
    entry.entry_id = "e1"

    handler = _make_intent_handler("CuliplanWhatsDinnerTonight", entry)
    assert handler.intent_type == "CuliplanWhatsDinnerTonight"

    client = MagicMock()
    client.async_execute_voice_tool = AsyncMock(
        return_value={
            "success": True,
            "speakableResponse": "Tonight you're cooking pasta.",
        }
    )
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"client": client}}}
    hass.config.language = "en"

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.language = "en"
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    response = await handler.async_handle(intent_obj)
    assert response is not None
    client.async_execute_voice_tool.assert_awaited_once_with(
        "whats_for_dinner", {}, language="en"
    )
    response.async_set_speech.assert_called_once_with("Tonight you're cooking pasta.")


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
        patch(
            "custom_components.culiplan._async_sync_custom_sentences",
            new=AsyncMock(),
        ) as sync_sentences,
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
    # Assist sentences are installed into custom_sentences/ on every setup.
    sync_sentences.assert_awaited_once_with(hass)


def _token_refresh_error(status: int):
    """Build the aiohttp error HA's OAuth2Session raises on a token failure."""
    import aiohttp

    return aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=status,
        message="Bad Request" if status == 400 else "Server Error",
    )


@pytest.mark.parametrize(
    ("status", "expected_exc_name"),
    [
        (400, "ConfigEntryAuthFailed"),  # refresh token gone → reauth prompt
        (401, "ConfigEntryAuthFailed"),
        (503, "ConfigEntryNotReady"),  # transient backend outage → retry
    ],
)
@pytest.mark.asyncio
async def test_async_setup_entry_token_refresh_failure_maps_to_ha_exception(
    status, expected_exc_name
):
    """A failed token refresh at setup raises the right config-entry exception.

    4xx means the refresh token no longer exists server-side (e.g. wiped
    Redis) — only reauth can recover, so HA must show the reauthentication
    repair instead of silently retrying setup forever.
    """
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

    from custom_components.culiplan import async_setup_entry

    expected_exc = {
        "ConfigEntryAuthFailed": ConfigEntryAuthFailed,
        "ConfigEntryNotReady": ConfigEntryNotReady,
    }[expected_exc_name]

    hass = MagicMock()
    hass.data = {}

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"token": {"access_token": "tok"}, "ai_mode": "cloud"}

    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock(
        side_effect=_token_refresh_error(status)
    )

    with (
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow"
            ".async_get_config_entry_implementation",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow.OAuth2Session",
            return_value=session,
        ),
        pytest.raises(expected_exc),
    ):
        await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_token_refresh_network_error_is_transient():
    """Network-level failure reaching the token endpoint → ConfigEntryNotReady."""
    import aiohttp

    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.culiplan import async_setup_entry

    hass = MagicMock()
    hass.data = {}

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"token": {"access_token": "tok"}, "ai_mode": "cloud"}

    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock(
        side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("boom"))
    )

    with (
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow"
            ".async_get_config_entry_implementation",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "custom_components.culiplan.config_entry_oauth2_flow.OAuth2Session",
            return_value=session,
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)


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


# ─── Intent handler additional paths (v0.13.0) ───────────────────────────────


@pytest.mark.asyncio
async def test_intent_handler_unknown_intent_returns_apology():
    """An intent name not in _INTENT_TO_TOOL returns a friendly speech."""
    entry = MagicMock()
    entry.entry_id = "e1"
    handler = _make_intent_handler("CuliplanUnknown", entry)
    client = MagicMock()
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"client": client}}}

    intent_obj = MagicMock()
    intent_obj.hass = hass
    intent_obj.slots = {}
    intent_obj.create_response = MagicMock(return_value=MagicMock())

    # Must not raise
    await handler.async_handle(intent_obj)


@pytest.mark.asyncio
async def test_cooking_intent_handler_returns_expected_speech_per_service():
    """Each cooking intent's service maps to its own spoken response."""
    entry = MagicMock()
    entry.entry_id = "e1"
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    for intent_name in (
        "CuliplanNextCookingStep",
        "CuliplanSetRecipeTimer",
        "CuliplanCancelRecipeTimer",
    ):
        handler = _make_cooking_intent_handler(intent_name, entry)
        intent_obj = MagicMock()
        intent_obj.hass = hass
        intent_obj.slots = (
            {"label": {"value": "pasta"}}
            if intent_name != "CuliplanNextCookingStep"
            else {}
        )
        intent_obj.create_response = MagicMock(return_value=MagicMock())
        # Must not raise — each intent has a friendly spoken response.
        await handler.async_handle(intent_obj)


@pytest.mark.asyncio
async def test_register_intents_loads_lang_fallback_file(tmp_path):
    """Unknown lang falls through to en.yaml and the load runs in the executor."""
    from custom_components.culiplan import _register_intents

    hass = MagicMock()
    # German is supported, but pretend the .yaml file is missing so the fallback runs.
    hass.config.language = "de"
    hass.async_add_executor_job = AsyncMock(return_value={"intents": {}})

    with patch("custom_components.culiplan._INTENTS_DIR", tmp_path):
        # The de.yaml doesn't exist in tmp_path → fallback to en.yaml.
        # en.yaml also doesn't exist, but _do_register's executor mock returns {}.
        # We just need to exercise the fallback branch without crashing.
        await _register_intents(hass, MagicMock())
    hass.async_add_executor_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload_entry_handles_panel_remove_failure():
    """The panel-removal exception block (KeyError/ValueError/ImportError) swallows."""
    from custom_components.culiplan import async_unload_entry

    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"

    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"coordinator": coordinator}}}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    # Only one Culiplan entry → panel-removal path triggers
    hass.config_entries.async_entries = MagicMock(return_value=[])

    with patch(
        "homeassistant.components.frontend.async_remove_panel",
        side_effect=KeyError("not registered"),
    ):
        # Must not raise
        result = await async_unload_entry(hass, entry)
    assert result is True


# ─── Final coverage adds ─────────────────────────────────────────────────────


def test_read_manifest_version_falls_back_on_failure(monkeypatch):
    """If the manifest JSON read fails, _read_manifest_version returns "dev"."""
    from pathlib import Path as _Path

    import custom_components.culiplan.const as const_mod

    class _BoomPath(_Path):
        def read_text(self, *_args, **_kwargs):  # type: ignore[override]
            raise OSError("disk on fire")

    def _patched(value):
        if str(value) == const_mod.__file__:
            return _BoomPath(value)
        return _Path(value)

    monkeypatch.setattr(const_mod, "_Path", _patched)
    assert const_mod._read_manifest_version() == "dev"
