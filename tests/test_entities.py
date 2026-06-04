"""Tests for calendar, todo, and sensor entities."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.culiplan.const import DOMAIN
from custom_components.culiplan.coordinator import CuliplanCoordinator
from homeassistant.helpers.device_registry import DeviceInfo


# ─── Shared coordinator fixture ──────────────────────────────────────────────


@pytest.fixture
def full_coordinator(hass, mock_api_client, mock_config_entry):
    coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
    coord.data = {
        "meal_plans": [
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
        ],
        "shopping_lists": [
            {
                "id": "sl1",
                "name": "Weekly Shop",
                "items": [
                    {"id": "item1", "name": "Pasta", "completed": False},
                    {"id": "item2", "name": "Eggs", "completed": True},
                ],
            }
        ],
        "pantry_items": [],
    }
    return coord


# ─── Calendar entity ─────────────────────────────────────────────────────────


class TestFlavorplanCalendar:

    def test_events_built_from_slot(self, full_coordinator, mock_config_entry):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        cal = FlavorplanCalendar(
            full_coordinator, full_coordinator.data["meal_plans"][0], mock_config_entry
        )
        events = cal._build_events()
        assert len(events) == 1
        e = events[0]
        assert e.summary == "Pasta Carbonara"
        assert e.start == datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc)
        # Metadata in description as JSON (not as CalendarEvent kwarg).
        meta = json.loads(e.description)
        assert meta["recipe_id"] == "rec1"
        assert meta["servings"] == 4
        assert meta["course"] == "dinner"

    def test_extra_state_attributes_exposes_next_event_meta(
        self, full_coordinator, mock_config_entry
    ):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        # Patch event to return upcoming event
        cal = FlavorplanCalendar(
            full_coordinator, full_coordinator.data["meal_plans"][0], mock_config_entry
        )
        # Force 'now' to before the event by using an old slot date
        full_coordinator.data["meal_plans"][0]["slots"][0]["date"] = (
            datetime.now(tz=timezone.utc) + timedelta(hours=1)
        ).isoformat()
        attrs = cal.extra_state_attributes
        assert "recipe_id" in attrs

    def test_no_extra_state_attrs_when_no_event(self, full_coordinator, mock_config_entry):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        full_coordinator.data["meal_plans"][0]["slots"] = []
        cal = FlavorplanCalendar(
            full_coordinator, full_coordinator.data["meal_plans"][0], mock_config_entry
        )
        assert cal.event is None
        assert cal.extra_state_attributes == {}

    @pytest.mark.asyncio
    async def test_get_events_filters_by_date_range(
        self, full_coordinator, mock_config_entry, hass
    ):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        cal = FlavorplanCalendar(
            full_coordinator, full_coordinator.data["meal_plans"][0], mock_config_entry
        )
        start = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 29, 0, 0, tzinfo=timezone.utc)
        assert len(await cal.async_get_events(hass, start, end)) == 1
        # Outside range
        assert len(
            await cal.async_get_events(
                hass,
                datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
            )
        ) == 0

    def test_device_info_present(self, full_coordinator, mock_config_entry):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        cal = FlavorplanCalendar(
            full_coordinator, full_coordinator.data["meal_plans"][0], mock_config_entry
        )
        assert cal._attr_device_info is not None
        info = cal._attr_device_info
        assert (DOMAIN, mock_config_entry.entry_id) in info["identifiers"]
        assert info["manufacturer"] == "Culiplan"
        assert info["sw_version"] is not None
        assert info["configuration_url"] == "https://culiplan.com"


# ─── Todo entity ─────────────────────────────────────────────────────────────


class TestFlavorplanShoppingList:

    def test_todo_items_mapped_correctly(self, full_coordinator, mock_config_entry):
        from custom_components.culiplan.todo import FlavorplanShoppingList
        from homeassistant.components.todo import TodoItemStatus

        entity = FlavorplanShoppingList(
            full_coordinator, full_coordinator.data["shopping_lists"][0], mock_config_entry
        )
        items = entity.todo_items
        assert len(items) == 2
        assert items[0].summary == "Pasta"
        assert items[0].status == TodoItemStatus.NEEDS_ACTION
        assert items[1].summary == "Eggs"
        assert items[1].status == TodoItemStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_create_item_calls_api_and_refreshes(
        self, full_coordinator, mock_config_entry, mock_api_client
    ):
        from custom_components.culiplan.todo import FlavorplanShoppingList
        from homeassistant.components.todo import TodoItem, TodoItemStatus

        entity = FlavorplanShoppingList(
            full_coordinator, full_coordinator.data["shopping_lists"][0], mock_config_entry
        )
        new_item = TodoItem(summary="Bread", status=TodoItemStatus.NEEDS_ACTION)

        mock_api_client.async_get_shopping_lists.return_value = [
            {**full_coordinator.data["shopping_lists"][0]}
        ]
        await entity.async_create_todo_item(new_item)
        mock_api_client.async_add_shopping_item.assert_awaited_once_with(
            "sl1", name="Bread"
        )

    def test_device_info_present(self, full_coordinator, mock_config_entry):
        from custom_components.culiplan.todo import FlavorplanShoppingList

        entity = FlavorplanShoppingList(
            full_coordinator, full_coordinator.data["shopping_lists"][0], mock_config_entry
        )
        info = entity._attr_device_info
        assert (DOMAIN, mock_config_entry.entry_id) in info["identifiers"]
        assert info["manufacturer"] == "Culiplan"
        assert info["sw_version"] is not None
        assert info["configuration_url"] == "https://culiplan.com"


# ─── Sensor trio ─────────────────────────────────────────────────────────────


class TestSensorTrio:

    @pytest.fixture
    def coordinator_with_pantry(self, hass, mock_api_client, mock_config_entry):
        import datetime as dt

        coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        slot_date = (
            datetime(
                monday.year, monday.month, monday.day, 18, 0,
                tzinfo=timezone.utc,
            )
            + dt.timedelta(days=2)
        ).isoformat()

        coord.data = {
            "meal_plans": [
                {"id": "mp1", "slots": [{"id": "s1", "date": slot_date, "title": "T"}]}
            ],
            "shopping_lists": [
                {
                    "id": "sl1",
                    "items": [
                        {"id": "i1", "completed": False},
                        {"id": "i2", "completed": False},
                        {"id": "i3", "completed": True},
                    ],
                }
            ],
            "pantry_items": [
                {"id": "p1", "expiresAt": (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()},
                {"id": "p2", "expiresAt": (datetime.now(tz=timezone.utc) + timedelta(days=10)).isoformat()},
            ],
        }
        return coord

    def _device(self, entry):
        from custom_components.culiplan.helpers import _build_device_info
        return _build_device_info(entry)

    def test_meals_this_week(self, coordinator_with_pantry, mock_config_entry):
        from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

        sensor = MealsPlanedThisWeekSensor(
            coordinator_with_pantry, self._device(mock_config_entry)
        )
        assert sensor.native_value == 1

    def test_shopping_count_excludes_completed(self, coordinator_with_pantry, mock_config_entry):
        from custom_components.culiplan.sensor import ShoppingItemsCountSensor

        sensor = ShoppingItemsCountSensor(
            coordinator_with_pantry, self._device(mock_config_entry)
        )
        assert sensor.native_value == 2

    def test_expiring_pantry_within_window(self, coordinator_with_pantry, mock_config_entry):
        from custom_components.culiplan.sensor import ExpiringPantrySensor

        sensor = ExpiringPantrySensor(
            coordinator_with_pantry, self._device(mock_config_entry), expiry_days=3
        )
        assert sensor.native_value == 1
        assert "p1" in sensor.extra_state_attributes["expiring_item_ids"]
        assert "p2" not in sensor.extra_state_attributes["expiring_item_ids"]

    def test_expiring_attributes_ids_only(self, coordinator_with_pantry, mock_config_entry):
        """Sensor attributes must not contain PII (§14.3)."""
        from custom_components.culiplan.sensor import ExpiringPantrySensor

        sensor = ExpiringPantrySensor(
            coordinator_with_pantry, self._device(mock_config_entry), expiry_days=3
        )
        assert set(sensor.extra_state_attributes) == {"expiring_item_ids", "expiry_window_days"}
