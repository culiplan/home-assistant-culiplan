"""
Culiplan binary sensor entities — Phase 2 (tasks 1378 + 1380).

Entities registered here:
    binary_sensor.culiplan_pantry_has_expiring
        — True when any pantry item expires within the configured window.
        — task-1378 AC#1

    binary_sensor.culiplan_dinner_party_active
        — True when a dinner party is scheduled for today (status PLANNED/VOTING).
        — Attributes: guest_count, course_count, start_at, recipe_ids (IDs only, §14.3)
        — task-1380 AC#1+2+3

Both sensors update in real-time via the CuliplanCoordinator Socket.IO feed:
    pantry.item.updated / pantry.item.depleted  → re-evaluate pantry sensor
    dinner_party.updated                         → re-fetch active party via REST

task-1380 AC#4 sample automation is documented in README.md.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CuliplanApiClient
from .const import DOMAIN
from .coordinator import CuliplanCoordinator
from .helpers import _build_device_info, parse_dt

_LOGGER = logging.getLogger(__name__)

DEFAULT_EXPIRY_HOURS = 48  # match task-1378 default window


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Culiplan binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: CuliplanCoordinator = data["coordinator"]
    client: CuliplanApiClient = data["client"]

    expiry_hours: int = entry.options.get("expiry_hours", DEFAULT_EXPIRY_HOURS)

    device = _build_device_info(entry)

    async_add_entities([
        PantryHasExpiringBinarySensor(coordinator, device, expiry_hours),
        DinnerPartyActiveBinarySensor(coordinator, client, device),
    ])


# ─── Pantry expiry binary sensor ─────────────────────────────────────────────

class PantryHasExpiringBinarySensor(
    CoordinatorEntity[CuliplanCoordinator], BinarySensorEntity
):
    """
    Binary sensor: True when any pantry item expires within the configured window.

    task-1378 AC#1 — binary_sensor.culiplan_pantry_has_expiring exposed.

    State:
        on  — at least one pantry item expires within expiry_hours
        off — no items expiring

    Attributes (IDs only, §14.3):
        expiring_item_ids  — list of pantryItemId strings
        expiry_window_hours — configured window
    """

    _attr_name = "Pantry has expiring items"
    _attr_icon = "mdi:food-variant-off"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: CuliplanCoordinator,
        device: DeviceInfo,
        expiry_hours: int,
    ) -> None:
        super().__init__(coordinator)
        self._expiry_hours = expiry_hours
        self._attr_unique_id = f"{DOMAIN}_pantry_has_expiring"
        self._attr_device_info = device

    @property
    def is_on(self) -> bool:
        """Return True if any pantry item expires within the configured window."""
        return len(self._expiring_ids()) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return expiring item IDs (no names/PII, §14.3)."""
        return {
            "expiring_item_ids": self._expiring_ids(),
            "expiry_window_hours": self._expiry_hours,
        }

    def _expiring_ids(self) -> list[str]:
        now = datetime.now(tz=UTC)
        cutoff = now + timedelta(hours=self._expiry_hours)
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


# ─── Dinner party active binary sensor ──────────────────────────────────────

class DinnerPartyActiveBinarySensor(
    CoordinatorEntity[CuliplanCoordinator], BinarySensorEntity
):
    """
    Binary sensor: True when a dinner party is active today.

    task-1380 AC#2 — binary_sensor.culiplan_dinner_party_active with attributes
        {guest_count, course_count, start_at, recipe_ids}.

    task-1380 AC#3 — updates live via dinner_party.updated Socket.IO events
        (the coordinator re-fetches and calls async_set_updated_data).

    State:
        on  — at least one dinner party is PLANNED or VOTING for today
        off — no active dinner party today

    Attributes:
        party_id     — dinner party ID (for REST re-fetch)
        guest_count  — number of invited guests
        course_count — number of dinner courses
        start_at     — ISO datetime string (date + time field)
        recipe_ids   — list of recipe IDs across all courses (IDs only, §14.3)
    """

    _attr_name = "Dinner party active"
    _attr_icon = "mdi:silverware-fork-knife"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        coordinator: CuliplanCoordinator,
        client: CuliplanApiClient,
        device: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_dinner_party_active"
        self._attr_device_info = device
        # Cache the last fetched active-party data from REST endpoint
        self._active_party: dict[str, Any] | None = None

    @property
    def is_on(self) -> bool:
        """Return True if a dinner party is active today."""
        if self._active_party is not None:
            return bool(self._active_party.get("is_active", False))
        # Fall back to coordinator data: check dinner_parties list
        return self._has_active_party_from_coordinator()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return dinner party attributes (task-1380 AC#2)."""
        if self._active_party and self._active_party.get("is_active"):
            attrs = self._active_party.get("attributes") or {}
            return {
                "party_id": self._active_party.get("party_id"),
                "guest_count": attrs.get("guest_count", 0),
                "course_count": attrs.get("course_count", 0),
                "start_at": attrs.get("start_at"),
                "recipe_ids": attrs.get("recipe_ids", []),
            }
        return {
            "party_id": None,
            "guest_count": 0,
            "course_count": 0,
            "start_at": None,
            "recipe_ids": [],
        }

    def _has_active_party_from_coordinator(self) -> bool:
        """Check coordinator data for today's dinner parties (fallback path)."""
        now = datetime.now(tz=UTC)
        today_str = now.date().isoformat()
        for party in (self.coordinator.data or {}).get("dinner_parties", []):
            if party.get("archived"):
                continue
            status = party.get("status", "")
            if status not in ("PLANNED", "VOTING"):
                continue
            party_date = party.get("date", "")
            if party_date and party_date[:10] == today_str:
                return True
        return False

    async def async_update(self) -> None:
        """Fetch fresh active-party data from the REST endpoint.

        Called by HA scheduler and after coordinator data updates.
        task-1380 AC#3 — live update on dinner_party.updated events.
        """
        try:
            self._active_party = await self._client.async_get("/api/ha/dinner-party/active")
        except Exception as err:
            _LOGGER.warning("[culiplan] Could not fetch active dinner party: %s", err)
            # Keep the last known state on transient failures
