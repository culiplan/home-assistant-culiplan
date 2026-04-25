"""Tests for calendar, todo, and sensor entities."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.coordinator import FlavorplanCoordinator
from custom_components.culiplan.const import DOMAIN


# ─── Calendar entity ─────────────────────────────────────────────────────────


class TestFlavorplanCalendar:

    @pytest.fixture
    def coordinator(self, hass, mock_api_client, mock_config_entry):
        coord = FlavorplanCoordinator(hass, mock_api_client, mock_config_entry)
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
            "shopping_lists": [],
            "pantry_items": [],
        }
        return coord

    def test_calendar_event_built_from_slot(self, coordinator, hass):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        calendar = FlavorplanCalendar(coordinator, coordinator.data["meal_plans"][0])

        events = calendar._build_events()
        assert len(events) == 1
        e = events[0]
        assert e.summary == "Pasta Carbonara"
        assert e.start == datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc)
        assert e.extra_state_attributes["recipe_id"] == "rec1"
        assert e.extra_state_attributes["servings"] == 4
        assert e.extra_state_attributes["course"] == "dinner"

    def test_calendar_event_returns_none_when_empty(self, coordinator, hass):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        coordinator.data["meal_plans"][0]["slots"] = []
        calendar = FlavorplanCalendar(coordinator, coordinator.data["meal_plans"][0])
        assert calendar.event is None

    @pytest.mark.asyncio
    async def test_get_events_filters_by_date_range(self, coordinator, hass):
        from custom_components.culiplan.calendar import FlavorplanCalendar

        calendar = FlavorplanCalendar(coordinator, coordinator.data["meal_plans"][0])

        start = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 29, 0, 0, tzinfo=timezone.utc)
        events = await calendar.async_get_events(hass, start, end)
        assert len(events) == 1

        # Outside range
        events_outside = await calendar.async_get_events(
            hass,
            datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
        )
        assert len(events_outside) == 0


# ─── Todo entity ─────────────────────────────────────────────────────────────


class TestFlavorplanShoppingList:

    @pytest.fixture
    def coordinator(self, hass, mock_api_client, mock_config_entry):
        coord = FlavorplanCoordinator(hass, mock_api_client, mock_config_entry)
        coord.data = {
            "meal_plans": [],
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

    def test_todo_items_mapped_correctly(self, coordinator, hass):
        from custom_components.culiplan.todo import FlavorplanShoppingList
        from homeassistant.components.todo import TodoItemStatus

        entity = FlavorplanShoppingList(coordinator, coordinator.data["shopping_lists"][0])
        items = entity.todo_items

        assert len(items) == 2
        assert items[0].summary == "Pasta"
        assert items[0].status == TodoItemStatus.NEEDS_ACTION
        assert items[1].summary == "Eggs"
        assert items[1].status == TodoItemStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_create_todo_item_calls_api(self, coordinator, hass, mock_api_client):
        from custom_components.culiplan.todo import FlavorplanShoppingList
        from homeassistant.components.todo import TodoItem, TodoItemStatus

        entity = FlavorplanShoppingList(coordinator, coordinator.data["shopping_lists"][0])
        new_item = TodoItem(summary="Bread", status=TodoItemStatus.NEEDS_ACTION)
        await entity.async_create_todo_item(new_item)

        mock_api_client.async_add_shopping_item.assert_awaited_once_with(
            "sl1", name="Bread", quantity=None
        )


# ─── Sensor trio ─────────────────────────────────────────────────────────────


class TestSensorTrio:

    @pytest.fixture
    def coordinator_with_data(self, hass, mock_api_client, mock_config_entry):
        from datetime import timedelta

        coord = FlavorplanCoordinator(hass, mock_api_client, mock_config_entry)
        now_str = datetime.now(tz=timezone.utc).isoformat()
        # Put a slot in the current week
        import datetime as dt
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        slot_date = datetime.combine(
            monday + dt.timedelta(days=2),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).isoformat()

        coord.data = {
            "meal_plans": [
                {
                    "id": "mp1",
                    "name": "Week",
                    "slots": [{"id": "s1", "date": slot_date, "title": "Lunch"}],
                }
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
                # expires in 1 day — within the 3-day window
                {
                    "id": "p1",
                    "expiresAt": (
                        datetime.now(tz=timezone.utc) + timedelta(days=1)
                    ).isoformat(),
                },
                # expires in 10 days — outside the window
                {
                    "id": "p2",
                    "expiresAt": (
                        datetime.now(tz=timezone.utc) + timedelta(days=10)
                    ).isoformat(),
                },
            ],
        }
        return coord

    def test_meals_planned_this_week(self, coordinator_with_data, hass):
        from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

        sensor = MealsPlanedThisWeekSensor(coordinator_with_data)
        assert sensor.native_value == 1

    def test_shopping_items_count_excludes_completed(self, coordinator_with_data, hass):
        from custom_components.culiplan.sensor import ShoppingItemsCountSensor

        sensor = ShoppingItemsCountSensor(coordinator_with_data)
        assert sensor.native_value == 2  # 2 unchecked out of 3

    def test_expiring_pantry_within_window(self, coordinator_with_data, hass):
        from custom_components.culiplan.sensor import ExpiringPantrySensor

        sensor = ExpiringPantrySensor(coordinator_with_data, expiry_days=3)
        assert sensor.native_value == 1
        assert "p1" in sensor.extra_state_attributes["expiring_item_ids"]
        assert "p2" not in sensor.extra_state_attributes["expiring_item_ids"]

    def test_expiring_pantry_attributes_ids_only(self, coordinator_with_data, hass):
        """Sensor attributes must not contain PII (§14.3)."""
        from custom_components.culiplan.sensor import ExpiringPantrySensor

        sensor = ExpiringPantrySensor(coordinator_with_data, expiry_days=3)
        attrs = sensor.extra_state_attributes
        # Only IDs and window — no names or other personal data.
        assert set(attrs.keys()) == {"expiring_item_ids", "expiry_window_days"}
