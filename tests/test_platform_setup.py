"""Platform-level `async_setup_entry` tests for every entity platform.

These tests pin the public contract of each platform's setup helper —
what entities it adds, given a coordinator with a particular shape —
without standing up a full HA instance.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.culiplan.const import DOMAIN


def _make_entry(entry_id: str = "e1"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.options = {}
    return entry


def _make_hass_with_coordinator(coordinator):
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {"coordinator": coordinator, "client": MagicMock()}}}
    return hass


# ─── calendar.async_setup_entry ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_setup_adds_one_per_meal_plan():
    from custom_components.culiplan.calendar import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {"meal_plans": [{"id": "p1", "name": "P1"}, {"id": "p2", "name": "P2"}]}
    hass = _make_hass_with_coordinator(coordinator)
    entry = _make_entry()
    add_entities = MagicMock()
    await async_setup_entry(hass, entry, add_entities)
    add_entities.assert_called_once()
    added = list(add_entities.call_args[0][0])
    assert len(added) == 2


@pytest.mark.asyncio
async def test_calendar_setup_no_plans_adds_nothing():
    from custom_components.culiplan.calendar import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {"meal_plans": []}
    hass = _make_hass_with_coordinator(coordinator)
    add_entities = MagicMock()
    await async_setup_entry(hass, _make_entry(), add_entities)
    added = list(add_entities.call_args[0][0])
    assert added == []


# ─── todo.async_setup_entry ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_todo_setup_adds_one_per_shopping_list():
    from custom_components.culiplan.todo import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {
        "shopping_lists": [{"id": "sl1", "name": "Weekly"}],
    }
    hass = _make_hass_with_coordinator(coordinator)
    add_entities = MagicMock()
    await async_setup_entry(hass, _make_entry(), add_entities)
    added = list(add_entities.call_args[0][0])
    assert len(added) == 1


# ─── sensor.async_setup_entry ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sensor_setup_adds_all_four():
    from custom_components.culiplan.sensor import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {}
    hass = _make_hass_with_coordinator(coordinator)
    add_entities = MagicMock()
    await async_setup_entry(hass, _make_entry(), add_entities)
    added = add_entities.call_args[0][0]
    assert len(added) == 4


# ─── binary_sensor.async_setup_entry ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_binary_sensor_setup_adds_both():
    from custom_components.culiplan.binary_sensor import async_setup_entry

    coordinator = MagicMock()
    coordinator.data = {}
    hass = _make_hass_with_coordinator(coordinator)
    add_entities = MagicMock()
    await async_setup_entry(hass, _make_entry(), add_entities)
    added = add_entities.call_args[0][0]
    assert len(added) == 2


# ─── DinnerPartyActiveBinarySensor.async_update with REST ────────────────────


@pytest.mark.asyncio
async def test_dinner_party_binary_sensor_async_update_calls_endpoint():
    from custom_components.culiplan.binary_sensor import DinnerPartyActiveBinarySensor

    coordinator = MagicMock()
    coordinator.data = {"dinner_parties": []}
    client = MagicMock()
    client.async_get = AsyncMock(
        return_value={"is_active": True, "party_id": "p1", "attributes": {}}
    )
    device = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"

    sensor = DinnerPartyActiveBinarySensor(coordinator, client, device, entry)
    await sensor.async_update()
    client.async_get.assert_awaited_once_with("/api/ha/dinner-party/active")
    assert sensor._active_party["party_id"] == "p1"


@pytest.mark.asyncio
async def test_dinner_party_binary_sensor_async_update_swallows_error():
    """REST failures must NOT raise from the entity's async_update."""
    from custom_components.culiplan.binary_sensor import DinnerPartyActiveBinarySensor

    coordinator = MagicMock()
    coordinator.data = {"dinner_parties": []}
    client = MagicMock()
    client.async_get = AsyncMock(side_effect=RuntimeError("backend down"))
    device = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"

    sensor = DinnerPartyActiveBinarySensor(coordinator, client, device, entry)
    # Must not raise — last known state preserved
    await sensor.async_update()
