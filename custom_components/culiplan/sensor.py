"""Sensor entities for the Culiplan integration (task-1368, task-1399)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CuliplanCoordinator
from .helpers import _build_device_info, parse_dt

_LOGGER = logging.getLogger(__name__)

DEFAULT_EXPIRY_DAYS = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Culiplan sensor entities."""
    coordinator: CuliplanCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    expiry_days: int = entry.options.get("expiry_days", DEFAULT_EXPIRY_DAYS)
    device = _build_device_info(entry)
    async_add_entities(
        [
            MealsPlanedThisWeekSensor(coordinator, device),
            ShoppingItemsCountSensor(coordinator, device),
            ExpiringPantrySensor(coordinator, device, expiry_days),
            PlannedKwhTodaySensor(coordinator, device),
        ]
    )


class _CuliplanSensor(CoordinatorEntity[CuliplanCoordinator], SensorEntity):
    """Base class that binds sensors to the shared device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CuliplanCoordinator, device: DeviceInfo) -> None:
        super().__init__(coordinator)
        self._attr_device_info = device


class MealsPlanedThisWeekSensor(_CuliplanSensor):
    """Number of meals planned in the current ISO week."""

    _attr_translation_key = "meals_planned_this_week"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "meals"

    def __init__(self, coordinator: CuliplanCoordinator, device: DeviceInfo) -> None:
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


class ShoppingItemsCountSensor(_CuliplanSensor):
    """Total unchecked items across all shopping lists."""

    _attr_translation_key = "shopping_items"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(self, coordinator: CuliplanCoordinator, device: DeviceInfo) -> None:
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


class ExpiringPantrySensor(_CuliplanSensor):
    """Number of pantry items expiring within the configured window."""

    _attr_translation_key = "expiring_pantry_items"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(
        self,
        coordinator: CuliplanCoordinator,
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


class PlannedKwhTodaySensor(_CuliplanSensor):
    """Estimated kWh for today's planned recipes — task-1399 (Phase 3 Tier 3).

    Exposes the sum of estimated energy consumption across all meal plan
    slots for the current day. Values are derived from recipe cooking-method
    tags + cook times; no native wattage or oven-temperature data is used.

    HA Energy dashboard integration:
      Add this sensor as a 'home appliance' in the HA Energy dashboard.
      HA will multiply kWh × your configured energy tariff to compute cost.
      See lovelace/dashboards/energy-meal-cost.yaml for a sample dashboard.

    Polling:
      Refreshed via the coordinator's existing refetch cadence (never faster
      than every 5 minutes). Also refreshed immediately when a meal_plan.updated
      WebSocket event is received.
    """

    _attr_translation_key = "planned_kwh_today"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: CuliplanCoordinator, device: DeviceInfo) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{DOMAIN}_planned_kwh_today"

    @property
    def native_value(self) -> float:
        """Return today's total estimated kWh from the coordinator cache."""
        energy_data = (self.coordinator.data or {}).get("energy_today")
        if not energy_data:
            return 0.0
        try:
            return float(energy_data.get("estimated_kwh", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-slot breakdown and metadata (IDs only — no PII, §14.3)."""
        energy_data = (self.coordinator.data or {}).get("energy_today", {})
        if not energy_data:
            return {}
        return {
            "date": energy_data.get("date"),
            "slot_count": energy_data.get("slot_count", 0),
            # Expose recipe IDs for linking but not titles (§14.3 ID-only rule).
            "recipe_ids": [
                slot["recipeId"]
                for slot in energy_data.get("slots", [])
                if slot.get("recipeId")
            ],
        }
