"""
Unit tests for Phase 2 binary sensor entities (tasks 1378 + 1380).

Tests use mocked coordinators; no real HTTP or Socket.IO calls are made.
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_coordinator(pantry_items=None, dinner_parties=None):
    coordinator = MagicMock()
    coordinator.data = {
        "meal_plans": [],
        "shopping_lists": [],
        "pantry_items": pantry_items or [],
        "dinner_parties": dinner_parties or [],
    }
    coordinator.last_update_success = True
    return coordinator


def _make_device():
    device = MagicMock()
    return device


def _make_entry(entry_id: str = "test_entry_id"):
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


# ─── PantryHasExpiringBinarySensor ────────────────────────────────────────────


class TestPantryHasExpiringBinarySensor:
    """task-1378 AC#1 — binary_sensor.culiplan_pantry_has_expiring"""

    def _make_sensor(self, pantry_items=None, expiry_hours=48):
        from custom_components.culiplan.binary_sensor import (
            PantryHasExpiringBinarySensor,
        )

        coordinator = _make_coordinator(pantry_items=pantry_items)
        device = _make_device()
        entry = _make_entry()
        sensor = PantryHasExpiringBinarySensor(coordinator, device, entry, expiry_hours)
        return sensor

    def test_unique_id(self):
        sensor = self._make_sensor()
        # v0.13.0: per-entry unique_id to avoid multi-account collision.
        assert sensor.unique_id == "test_entry_id_pantry_has_expiring"

    def test_is_off_when_no_items(self):
        sensor = self._make_sensor(pantry_items=[])
        assert sensor.is_on is False

    def test_is_off_when_no_expiry_field(self):
        sensor = self._make_sensor(
            pantry_items=[
                {"id": "item1", "name": "Milk"},  # no expiresAt
            ]
        )
        assert sensor.is_on is False

    def test_is_on_when_item_expires_within_window(self):
        soon = (datetime.now(tz=UTC) + timedelta(hours=24)).isoformat()
        sensor = self._make_sensor(
            pantry_items=[
                {"id": "item1", "name": "Milk", "expiresAt": soon},
            ]
        )
        assert sensor.is_on is True

    def test_is_off_when_item_expires_outside_window(self):
        later = (datetime.now(tz=UTC) + timedelta(days=10)).isoformat()
        sensor = self._make_sensor(
            pantry_items=[
                {"id": "item1", "name": "Milk", "expiresAt": later},
            ],
            expiry_hours=48,
        )
        assert sensor.is_on is False

    def test_extra_state_attributes_ids_only(self):
        """Attributes must contain item IDs, not names (§14.3)."""
        soon = (datetime.now(tz=UTC) + timedelta(hours=12)).isoformat()
        sensor = self._make_sensor(
            pantry_items=[
                {"id": "item-abc", "name": "Sensitive Item Name", "expiresAt": soon},
            ]
        )
        attrs = sensor.extra_state_attributes
        assert "item-abc" in attrs["expiring_item_ids"]
        # Names must NOT appear in attributes (§14.3 PII check)
        assert "Sensitive Item Name" not in str(attrs)

    def test_extra_state_attributes_expiry_window(self):
        sensor = self._make_sensor(expiry_hours=72)
        attrs = sensor.extra_state_attributes
        assert attrs["expiry_window_hours"] == 72


# ─── DinnerPartyActiveBinarySensor ────────────────────────────────────────────


class TestDinnerPartyActiveBinarySensor:
    """task-1380 AC#1+2+3 — binary_sensor.culiplan_dinner_party_active"""

    def _make_sensor(self, coordinator=None):
        from custom_components.culiplan.binary_sensor import (
            DinnerPartyActiveBinarySensor,
        )

        if coordinator is None:
            coordinator = _make_coordinator()
        client = AsyncMock()
        device = _make_device()
        entry = _make_entry()
        sensor = DinnerPartyActiveBinarySensor(coordinator, client, device, entry)
        return sensor

    def test_unique_id(self):
        sensor = self._make_sensor()
        # v0.13.0: per-entry unique_id to avoid multi-account collision.
        assert sensor.unique_id == "test_entry_id_dinner_party_active"

    def test_is_off_by_default_no_active_party(self):
        """No REST data yet, no coordinator data → should be off."""
        sensor = self._make_sensor()
        assert sensor.is_on is False

    def test_is_on_when_rest_data_active(self):
        sensor = self._make_sensor()
        sensor._active_party = {
            "is_active": True,
            "party_id": "party123",
            "updated_at": "2026-04-25T18:00:00Z",
            "attributes": {
                "guest_count": 6,
                "course_count": 3,
                "start_at": "2026-04-25T19:00:00",
                "recipe_ids": ["rec1", "rec2", "rec3"],
            },
        }
        assert sensor.is_on is True

    def test_is_off_when_rest_data_inactive(self):
        sensor = self._make_sensor()
        sensor._active_party = {
            "is_active": False,
            "party_id": None,
            "attributes": None,
        }
        assert sensor.is_on is False

    def test_extra_state_attributes_with_active_party(self):
        """task-1380 AC#2 — attributes must include all four fields."""
        sensor = self._make_sensor()
        sensor._active_party = {
            "is_active": True,
            "party_id": "party123",
            "updated_at": "2026-04-25T18:00:00Z",
            "attributes": {
                "guest_count": 8,
                "course_count": 4,
                "start_at": "2026-04-25T19:30:00",
                "recipe_ids": ["r1", "r2", "r3", "r4"],
            },
        }
        attrs = sensor.extra_state_attributes
        assert attrs["party_id"] == "party123"
        assert attrs["guest_count"] == 8
        assert attrs["course_count"] == 4
        assert attrs["start_at"] == "2026-04-25T19:30:00"
        assert attrs["recipe_ids"] == ["r1", "r2", "r3", "r4"]

    def test_extra_state_attributes_empty_when_inactive(self):
        sensor = self._make_sensor()
        sensor._active_party = {
            "is_active": False,
            "party_id": None,
            "attributes": None,
        }
        attrs = sensor.extra_state_attributes
        assert attrs["party_id"] is None
        assert attrs["guest_count"] == 0
        assert attrs["recipe_ids"] == []

    def test_recipe_ids_are_ids_only(self):
        """recipe_ids must be opaque IDs, not recipe titles (§14.3)."""
        sensor = self._make_sensor()
        sensor._active_party = {
            "is_active": True,
            "party_id": "p1",
            "attributes": {
                "guest_count": 2,
                "course_count": 1,
                "start_at": "2026-04-25T18:00:00",
                "recipe_ids": ["uuid-abc-123"],
            },
        }
        attrs = sensor.extra_state_attributes
        # IDs should look like UUIDs / opaque strings, not names
        for rid in attrs["recipe_ids"]:
            assert " " not in rid  # No spaces in IDs

    @pytest.mark.asyncio
    async def test_async_update_fetches_rest_endpoint(self):
        """task-1380 AC#3 — async_update calls the REST endpoint."""
        sensor = self._make_sensor()
        sensor._client.async_get = AsyncMock(
            return_value={
                "is_active": True,
                "party_id": "party999",
                "attributes": {
                    "guest_count": 4,
                    "course_count": 2,
                    "start_at": "2026-04-25T20:00:00",
                    "recipe_ids": [],
                },
            }
        )
        await sensor.async_update()
        sensor._client.async_get.assert_called_once_with("/api/ha/dinner-party/active")
        assert sensor._active_party["party_id"] == "party999"

    @pytest.mark.asyncio
    async def test_async_update_handles_api_error_gracefully(self):
        """On transient API error, last known state is preserved."""
        sensor = self._make_sensor()
        sensor._active_party = {"is_active": True, "party_id": "last-known"}
        sensor._client.async_get = AsyncMock(side_effect=Exception("Network error"))

        await sensor.async_update()  # Should not raise
        # Last known state preserved
        assert sensor._active_party["party_id"] == "last-known"

    def test_fallback_to_coordinator_data(self):
        """When _active_party is None, fall back to coordinator dinner_parties data."""
        today = datetime.now(tz=UTC).date().isoformat()
        coordinator = _make_coordinator(
            dinner_parties=[
                {
                    "id": "dp1",
                    "date": today,
                    "status": "PLANNED",
                    "archived": False,
                }
            ]
        )
        sensor = self._make_sensor(coordinator=coordinator)
        # No REST data yet
        assert sensor._active_party is None
        assert sensor.is_on is True
