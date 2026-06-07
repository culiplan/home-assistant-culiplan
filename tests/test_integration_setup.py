"""Full setup/unload integration test using MockConfigEntry.

These tests stand the integration up end-to-end against the real HA test
fixtures, exercising async_setup_entry → coordinator first refresh →
platform forwards → unload. Hits a large amount of __init__.py,
coordinator.py and the platform async_setup_entry methods that pure unit
tests skip.

Skipped when the ``hass_frontend`` package is not installed (CI's
pytest-homeassistant-custom-component virtualenv ships the slim HA core
without the prebuilt frontend assets). The HA dependency `frontend`
imports `hass_frontend` at setup time and refuses to start without it,
so the integration's `async_setup_entry` never runs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    import hass_frontend  # noqa: F401

    _HAS_FRONTEND = True
except ImportError:
    _HAS_FRONTEND = False

pytestmark = pytest.mark.skipif(
    not _HAS_FRONTEND,
    reason="hass_frontend not installed; integration setup test requires it",
)

from custom_components.culiplan.const import (
    AI_MODE_CLOUD,
    CONF_AI_MODE,
    DOMAIN,
    OAUTH_CLIENT_ID,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)


@pytest.fixture
async def _setup_credential(hass):
    """Register the Culiplan public OAuth credential so async_setup_entry
    can resolve the implementation HA needs to build the OAuth2Session.
    """
    from homeassistant.components.application_credentials import (
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential(client_id=OAUTH_CLIENT_ID, client_secret=""),
    )


@pytest.fixture
def mock_async_check_latest():
    """Block the GitHub release poll from hitting the network during setup."""
    with patch(
        "custom_components.culiplan.updater.async_check_latest",
        new=AsyncMock(return_value=None),
    ):
        yield


@pytest.fixture
def mock_api_responses():
    """Return canned REST responses for every endpoint the coordinator hits."""

    class _FakeClient:
        def __init__(self, *_args, **_kwargs):
            self._access_token = "tok"

        async def async_get_meal_plans(self):
            return [{"id": "current", "name": "Meal Plan", "slots": []}]

        async def async_get_shopping_lists(self):
            return [{"id": "default", "name": "Shopping List", "items": []}]

        async def async_get_pantry_items(self):
            return []

        async def async_get_energy_today(self):
            return {"date": "2026-06-07", "estimated_kwh": 0.0, "slots": []}

        async def async_get(self, _path):
            return []

    with patch(
        "custom_components.culiplan.CuliplanApiClient",
        side_effect=lambda *a, **k: _FakeClient(),
    ):
        yield


@pytest.mark.asyncio
async def test_full_setup_and_unload(
    hass, _setup_credential, mock_async_check_latest, mock_api_responses
):
    """async_setup_entry → platforms forward → async_unload_entry round-trip.

    Patches the OAuth2Session token-ensure call so the test never tries
    to hit the real Culiplan token endpoint; the rest of the setup
    pipeline runs unmocked.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Culiplan",
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "tok_access",
                "refresh_token": "tok_refresh",
                "expires_at": 9999999999,
                "expires_in": 3600,
            },
            CONF_AI_MODE: AI_MODE_CLOUD,
        },
        version=2,  # already on the per-entry unique_id scheme
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session"
            ".async_ensure_token_valid",
            new=AsyncMock(),
        ),
        # Block the socketio client from actually opening a real connection;
        # we only care that the integration sets up cleanly + tears down.
        patch(
            "custom_components.culiplan.coordinator.socketio.AsyncClient",
            return_value=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Setup populated hass.data with the coordinator + client.
        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]
        data = hass.data[DOMAIN][entry.entry_id]
        assert "coordinator" in data
        assert "client" in data

        # The Culiplan service set is registered.
        assert hass.services.has_service(DOMAIN, "suggest_meal")
        assert hass.services.has_service(DOMAIN, "fill_shopping_list")

        # Unload removes everything cleanly.
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        # The entry's data slot is gone but DOMAIN may still hold the bookkeeping dict.
        assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_setup_triggers_v1_migration(
    hass, _setup_credential, mock_async_check_latest, mock_api_responses
):
    """A v1 entry triggers async_migrate_entry on setup; entry ends on v2."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Culiplan",
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "tok_access",
                "refresh_token": "tok_refresh",
                "expires_at": 9999999999,
                "expires_in": 3600,
            },
            CONF_AI_MODE: AI_MODE_CLOUD,
        },
        version=1,  # legacy schema
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session"
            ".async_ensure_token_valid",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.culiplan.coordinator.socketio.AsyncClient",
            return_value=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.version == 2
