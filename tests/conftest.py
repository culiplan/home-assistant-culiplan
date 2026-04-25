"""pytest configuration for pytest-homeassistant-custom-component."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
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
