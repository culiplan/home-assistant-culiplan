"""pytest configuration for pytest-homeassistant-custom-component.

This file sets up the test environment for the Culiplan HA integration:

1. **pytest plugin registration.** We register
   `pytest_homeassistant_custom_component` so HA's test fixtures
   (`hass`, `hass_storage`, `aioclient_mock`, …) are available to
   every test module.

2. **Async fixture resolution.** The `hass` fixture upstream is an
   async generator. pytest-asyncio in `Mode.STRICT` does NOT
   transparently resolve async fixtures consumed by sync fixtures,
   which is exactly what `enable_custom_integrations` does
   (`def enable_custom_integrations(hass: HomeAssistant) -> None: …`).
   When the autouse wrapper triggered that fixture, `hass` arrived
   as a coroutine and `hass.data.pop(...)` raised
   `AttributeError: 'async_generator' object has no attribute 'data'`
   — the exact symptom that broke all three Tests matrix lanes
   (HA 2024.10 / 2025.1 / 2026.6) on 2026-06-04.

   Fix: pyproject.toml sets `asyncio_mode = "auto"` in
   `[tool.pytest.ini_options]`. That flips pytest-asyncio into auto
   mode for the whole repo, so async fixtures are awaited
   transparently regardless of which fixture chain consumed them.
   With that one config change, the legacy autouse wrapper below
   works again on every HA + Python version in the matrix without
   any try/except shims.

3. **Custom-integration discovery.** The autouse fixture below
   transitively pulls in `enable_custom_integrations`, which clears
   the cached `DATA_CUSTOM_COMPONENTS` dict on the test hass so the
   integration under test is reloaded for each test case.

4. **No skip list any more.** The earlier ``_BROKEN_TEST_IDS`` set
   was removed in v0.13.0 once every test had been brought back to
   green. The hard floor in ``pyproject.toml`` (``fail_under = 95``)
   now stands without exceptions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


# ─── Fixture: enable custom integrations for every test ──────────────────────


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Autouse wrapper so tests don't have to declare the fixture by hand.

    Depends transitively on the upstream `hass` async-generator fixture;
    the `asyncio_mode = "auto"` setting in pyproject.toml is what makes
    that resolution work across all matrix lanes.
    """
    yield


# ─── Shared API mock ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_api_client():
    client = AsyncMock()
    client.async_get_user.return_value = {"id": "user1", "name": "Test User"}
    client.async_get_meal_plans.return_value = [
        {
            "id": "mp1",
            "name": "This Week",
            "slots": [
                {
                    "id": "slot1",
                    "date": "2026-04-28T18:00:00Z",
                    "title": "Pasta Carbonara",
                    "recipeId": "rec1",
                    "servings": 4,
                    "course": "dinner",
                }
            ],
        }
    ]
    client.async_get_shopping_lists.return_value = [
        {
            "id": "sl1",
            "name": "Weekly Shop",
            "items": [
                {"id": "item1", "name": "Pasta", "completed": False},
                {"id": "item2", "name": "Eggs", "completed": True},
            ],
        }
    ]
    client.async_get_pantry_items.return_value = [
        {"id": "p1", "name": "Milk", "expiresAt": "2026-04-27T00:00:00Z"},
        {"id": "p2", "name": "Cheese", "expiresAt": "2026-05-10T00:00:00Z"},
    ]
    client._access_token = "tok_test"
    return client


@pytest.fixture
def mock_config_entry(hass):
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.culiplan.const import DOMAIN, AI_MODE_CLOUD, CONF_AI_MODE

    entry = MagicMock()
    entry.domain = DOMAIN
    entry.entry_id = "test_entry_id"
    entry.data = {
        "token": {
            "access_token": "tok_test",
            "refresh_token": "ref_test",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
        CONF_AI_MODE: AI_MODE_CLOUD,
    }
    entry.options = {}
    entry.state = ConfigEntryState.LOADED
    entry.async_on_unload = MagicMock(return_value=lambda: None)
    return entry
