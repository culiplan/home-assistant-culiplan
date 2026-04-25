"""Tier 1 sensor trio for the Flavorplan integration (task-1368)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlavorplanCoordinator
from .helpers import parse_dt

_LOGGER = logging.getLogger(__name__)

DEFAULT_EXPIRY_DAYS = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flavorplan sensor entities."""
    coordinator: FlavorplanCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    expiry_days: int = entry.options.get("expiry_days", DEFAULT_EXPIRY_DAYS)
    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Flavorplan",
        manufacturer="Flavorplan",
        model="Meal Planner",
        entry_type="service",
    )
    async_add_entities([
        MealsPlanedThisWeekSensor(coordinator, device),
        ShoppingItemsCountSensor(coordinator, device),
        ExpiringPantrySensor(coordinator, device, expiry_days),
    ])


class _FlavorplanSensor(CoordinatorEntity[FlavorplanCoordinator], SensorEntity):
    """Base class that binds sensors to the shared device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: FlavorplanCoordinator, device: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = device


class MealsPlanedThisWeekSensor(_FlavorplanSensor):
    """Number of meals planned in the current ISO week."""

    _attr_name = "Meals planned this week"
    _attr_icon = "mdi:calendar-week"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "meals"

    def __init__(self, coordinator: FlavorplanCoordinator, device: DeviceInfo) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_meals_planned_this_week"

    @property
    def native_value(self) -> int:
        now = datetime.now(tz=UTC)
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(weeks=1)
        count = 0
        for plan in (self.coordinator.data or {}).get("meal_plans", []):
            for slot in plan.get("slots", []):
                try:
                    if week_start <= parse_dt(slot["date"]) < week_end:
                        count += 1
                except (KeyError, ValueError):
                    pass
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}


class ShoppingItemsCountSensor(_FlavorplanSensor):
    """Total unchecked items across all shopping lists."""

    _attr_name = "Shopping items"
    _attr_icon = "mdi:cart"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(self, coordinator: FlavorplanCoordinator, device: DeviceInfo) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_shopping_items"

    @property
    def native_value(self) -> int:
        count = 0
        for sl in (self.coordinator.data or {}).get("shopping_lists", []):
            for item in sl.get("items", []):
                if not item.get("completed", False):
                    count += 1
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}


class ExpiringPantrySensor(_FlavorplanSensor):
    """Number of pantry items expiring within the configured window."""

    _attr_name = "Expiring pantry items"
    _attr_icon = "mdi:food-variant-off"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(
        self,
        coordinator: FlavorplanCoordinator,
        device: DeviceInfo,
        expiry_days: int,
    ) -> None:
        super().__init__(coordinator, device)
        self._expiry_days = expiry_days
        self._attr_unique_id = f"{DOMAIN}_expiring_pantry"

    @property
    def native_value(self) -> int:
        return len(self._expiring_ids())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # IDs only — no names or PII in attributes (§14.3).
        return {
            "expiring_item_ids": self._expiring_ids(),
            "expiry_window_days": self._expiry_days,
        }

    def _expiring_ids(self) -> list[str]:
        now = datetime.now(tz=UTC)
        cutoff = now + timedelta(days=self._expiry_days)
        ids: list[str] = []
        for item in (self.coordinator.data or {}).get("pantry_items", []):
            exp = item.get("expiresAt")
            if not exp:
                continue
            try:
                if now <= parse_dt(exp) <= cutoff:
                    ids.append(item["id"])
            except (KeyError, ValueError):
                pass
        return ids
