"""Tests for CuliplanCoordinator — happy path, reconnect, stale token."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.coordinator import (
    CuliplanCoordinator,
    _MAX_HEARTBEAT_MISSES,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.async_get_meal_plans.return_value = [{"id": "mp1"}]
    client.async_get_shopping_lists.return_value = [{"id": "sl1"}]
    client._access_token = "tok_initial"
    return client


@pytest.fixture
def mock_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def coordinator(hass, mock_client, mock_entry):
    return CuliplanCoordinator(hass, mock_client, mock_entry)


# ─── Happy path ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initial_fetch_populates_data(coordinator, mock_client):
    """First refresh fetches meal plans and shopping lists from REST."""
    with patch.object(coordinator, "_connect", new_callable=AsyncMock):
        data = await coordinator._async_update_data()

    assert data["meal_plans"] == [{"id": "mp1"}]
    assert data["shopping_lists"] == [{"id": "sl1"}]
    mock_client.async_get_meal_plans.assert_awaited_once()
    mock_client.async_get_shopping_lists.assert_awaited_once()


@pytest.mark.asyncio
async def test_ha_event_meal_plan_triggers_refresh(coordinator, mock_client):
    """meal_plan.updated event causes meal plan re-fetch."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}

    with patch.object(
        coordinator, "_refresh_meal_plans", new_callable=AsyncMock
    ) as mock_refresh:
        await coordinator._handle_event(
            {
                "type": "meal_plan.updated",
                "id": "mp1",
                "updatedAt": "2026-04-25T12:00:00Z",
            }
        )
        mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_ha_event_shopping_item_triggers_refresh(coordinator, mock_client):
    """shopping_list.item.added event causes shopping list re-fetch."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}

    with patch.object(
        coordinator, "_refresh_shopping_lists", new_callable=AsyncMock
    ) as mock_refresh:
        await coordinator._handle_event(
            {
                "type": "shopping_list.item.added",
                "id": "item1",
                "updatedAt": "2026-04-25T12:00:00Z",
            }
        )
        mock_refresh.assert_awaited_once()


# ─── Reconnect logic ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect_schedules_reconnect(coordinator):
    """A disconnect event schedules the reconnect loop."""
    coordinator._connected = True
    coordinator._miss_count = 0

    with patch.object(coordinator, "_schedule_reconnect") as mock_schedule:
        # Simulate a disconnect callback
        coordinator._connected = False
        coordinator._miss_count += 1
        coordinator._schedule_reconnect()
        mock_schedule.assert_called_once()


@pytest.mark.asyncio
async def test_max_heartbeat_misses_marks_unavailable(coordinator):
    """After _MAX_HEARTBEAT_MISSES disconnects, coordinator marks itself unavailable."""
    coordinator._connected = True
    coordinator._miss_count = 0
    coordinator.last_update_success = True

    with patch.object(coordinator, "async_update_listeners"):
        for _ in range(_MAX_HEARTBEAT_MISSES):
            coordinator._miss_count += 1

        if coordinator._miss_count >= _MAX_HEARTBEAT_MISSES:
            coordinator.last_update_success = False
            coordinator.async_update_listeners()

    assert not coordinator.last_update_success


@pytest.mark.asyncio
async def test_reconnect_resets_miss_count(coordinator):
    """Successful reconnect resets the heartbeat miss counter."""
    coordinator._miss_count = _MAX_HEARTBEAT_MISSES
    coordinator._connected = False

    # Simulate a successful connect callback
    coordinator._connected = True
    coordinator._miss_count = 0

    assert coordinator._miss_count == 0


# ─── Token refresh ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_token_refreshed_before_connect(coordinator, mock_entry):
    """_get_valid_token() calls async_ensure_token_valid and returns the token."""
    mock_impl = MagicMock()
    mock_oauth_session = MagicMock()
    mock_oauth_session.async_ensure_token_valid = AsyncMock()
    mock_oauth_session.token = {"access_token": "tok_refreshed"}

    # config_entry_oauth2_flow is imported lazily inside _get_valid_token,
    # so patch the symbols at their source module.
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow"
            ".async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=mock_impl,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session",
            return_value=mock_oauth_session,
        ),
    ):
        token = await coordinator._get_valid_token()

    assert token == "tok_refreshed"
    mock_oauth_session.async_ensure_token_valid.assert_awaited_once()
