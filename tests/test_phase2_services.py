"""
Unit tests for Phase 2 Culiplan HA services (tasks 1376, 1378, 1379).

Tests use mocked API clients; no real HTTP calls are made.
Syntax-verified + mocked unit tests (Python 3.9 compatible).
"""

from __future__ import annotations

from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_hass(entry_id: str = "entry1") -> MagicMock:
    hass = MagicMock()
    hass.data = {
        "culiplan": {
            entry_id: {
                "client": AsyncMock(),
            }
        }
    }
    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    return hass


def _registered_handler(hass: MagicMock, service_name: str) -> Any:  # type: ignore[name-defined]
    """Return the handler registered for the given service name.

    Service-registration order changed across feature waves; locate by name
    instead of relying on a positional index in
    ``hass.services.async_register.call_args_list``.
    """
    for call in hass.services.async_register.call_args_list:
        # async_register(DOMAIN, name, handler, schema=...)
        if call.args[1] == service_name:
            return call.args[2]
    raise AssertionError(f"Service {service_name!r} was never registered")


# ─── Test: _find_entry_id ─────────────────────────────────────────────────────


def test_find_entry_id_returns_first_key():
    from custom_components.culiplan.services import _find_entry_id

    hass = MagicMock()
    hass.data = {"culiplan": {"entry_abc": {}, "entry_xyz": {}}}
    result = _find_entry_id(hass)
    assert result == "entry_abc"


def test_find_entry_id_returns_none_when_empty():
    from custom_components.culiplan.services import _find_entry_id

    hass = MagicMock()
    hass.data = {"culiplan": {}}
    result = _find_entry_id(hass)
    assert result is None


def test_find_entry_id_returns_none_when_domain_missing():
    from custom_components.culiplan.services import _find_entry_id

    hass = MagicMock()
    hass.data = {}
    result = _find_entry_id(hass)
    assert result is None


# ─── Test: async_register_phase2_services ────────────────────────────────────


def test_register_phase2_services_registers_all_three():
    from custom_components.culiplan.services import (
        async_register_phase2_services,
        SERVICE_PANTRY_DECREMENT,
        SERVICE_PANTRY_EXPIRING,
        SERVICE_SCALE_TONIGHT_SERVINGS,
    )

    hass = _make_hass()
    async_register_phase2_services(hass)

    calls = [c.args[1] for c in hass.services.async_register.call_args_list]
    assert SERVICE_PANTRY_DECREMENT in calls
    assert SERVICE_PANTRY_EXPIRING in calls
    assert SERVICE_SCALE_TONIGHT_SERVINGS in calls


def test_register_phase2_services_idempotent():
    """Services should NOT be re-registered if already present."""
    from custom_components.culiplan.services import async_register_phase2_services

    hass = _make_hass()
    hass.services.has_service.return_value = True  # already registered

    async_register_phase2_services(hass)
    hass.services.async_register.assert_not_called()


# ─── Test: pantry_decrement service handler ────────────────────────────────────


@pytest.mark.asyncio
async def test_pantry_decrement_success():
    """Successful decrement calls the API and resolves any repair issue."""
    from custom_components.culiplan.services import (
        async_register_phase2_services,
    )

    hass = _make_hass()
    client = hass.data["culiplan"]["entry1"]["client"]
    client.async_post = AsyncMock(
        return_value={
            "success": True,
            "pantryItemId": "item123",
            "decremented": 1.0,
            "remaining": 0,
        }
    )

    # Capture the handler function
    async_register_phase2_services(hass)
    from custom_components.culiplan.services import SERVICE_PANTRY_DECREMENT

    handler = _registered_handler(hass, SERVICE_PANTRY_DECREMENT)

    call_data = MagicMock()
    call_data.data = {"barcode": "1234567890123", "qty": 1.0}

    with patch("custom_components.culiplan.services.ir") as mock_ir:
        await handler(call_data)
        # Repair for this barcode should be resolved on success
        mock_ir.async_delete_issue.assert_called_once()

    client.async_post.assert_called_once_with(
        "/api/ha/pantry/decrement",
        {"barcode": "1234567890123", "qty": 1.0},
    )


@pytest.mark.asyncio
async def test_pantry_decrement_barcode_not_found_creates_repair():
    """404 response should create a Repairs issue."""
    from custom_components.culiplan.services import (
        async_register_phase2_services,
        PantryItemNotFoundError,
    )

    hass = _make_hass()
    client = hass.data["culiplan"]["entry1"]["client"]
    client.async_post = AsyncMock(
        side_effect=Exception('404 {"error":"PANTRY_ITEM_NOT_FOUND","barcode":"999"}')
    )

    async_register_phase2_services(hass)
    from custom_components.culiplan.services import SERVICE_PANTRY_DECREMENT

    handler = _registered_handler(hass, SERVICE_PANTRY_DECREMENT)

    call_data = MagicMock()
    call_data.data = {"barcode": "999", "qty": 1.0}

    with patch("custom_components.culiplan.services.ir") as mock_ir:
        with pytest.raises(PantryItemNotFoundError):
            await handler(call_data)
        # Repairs issue must be created (task-1376 AC#2)
        mock_ir.async_create_issue.assert_called_once()
        issue_kwargs = mock_ir.async_create_issue.call_args[1]
        assert "barcode_not_found" in issue_kwargs["issue_id"]


# ─── Test: pantry_expiring_items service handler ─────────────────────────────


@pytest.mark.asyncio
async def test_pantry_expiring_fires_ha_event():
    """Service should fire a HA event with item IDs (§14.3)."""
    from custom_components.culiplan.services import async_register_phase2_services

    hass = _make_hass()
    client = hass.data["culiplan"]["entry1"]["client"]
    # The service hits CuliplanApiClient._get directly (see services._call_pantry_expiring).
    client._get = AsyncMock(
        return_value={
            "windowHours": 48,
            "count": 2,
            "items": [
                {
                    "pantryItemId": "item-1",
                    "stockIds": ["s1"],
                    "earliestExpiryAt": "2026-04-27T00:00:00Z",
                },
                {
                    "pantryItemId": "item-2",
                    "stockIds": ["s2"],
                    "earliestExpiryAt": "2026-04-26T12:00:00Z",
                },
            ],
        }
    )

    async_register_phase2_services(hass)
    from custom_components.culiplan.services import SERVICE_PANTRY_EXPIRING

    handler = _registered_handler(hass, SERVICE_PANTRY_EXPIRING)

    call_data = MagicMock()
    call_data.data = {"window_hours": 48}

    await handler(call_data)

    # Event should be fired with ID-only payload
    hass.bus.async_fire.assert_called_once()
    fired_event, fired_data = hass.bus.async_fire.call_args[0]
    assert fired_event == "culiplan_pantry_expiring_result"
    assert fired_data["count"] == 2
    assert "item-1" in fired_data["item_ids"]
    assert "item-2" in fired_data["item_ids"]
    # No names or PII in the event payload (§14.3)
    assert "name" not in str(fired_data)


# ─── Test: scale_tonight_servings service handler ─────────────────────────────


@pytest.mark.asyncio
async def test_scale_tonight_servings_success():
    """Premium users should be able to scale servings successfully."""
    from custom_components.culiplan.services import async_register_phase2_services

    hass = _make_hass()
    client = hass.data["culiplan"]["entry1"]["client"]
    client.async_post = AsyncMock(
        return_value={
            "success": True,
            "presentCount": 3,
            "slotsUpdated": 2,
            "date": "2026-04-25",
            "mealPlanIds": ["mp1", "mp2"],
        }
    )

    async_register_phase2_services(hass)
    from custom_components.culiplan.services import SERVICE_SCALE_TONIGHT_SERVINGS

    handler = _registered_handler(hass, SERVICE_SCALE_TONIGHT_SERVINGS)

    call_data = MagicMock()
    call_data.data = {"present_count": 3}

    await handler(call_data)
    client.async_post.assert_called_once_with(
        "/api/ha/servings/scale",
        {"present_count": 3},
    )


@pytest.mark.asyncio
async def test_scale_tonight_servings_premium_required_creates_repair():
    """403 premium_required should create a Repairs upsell issue."""
    from custom_components.culiplan.services import (
        async_register_phase2_services,
        PremiumRequiredError,
    )

    hass = _make_hass()
    client = hass.data["culiplan"]["entry1"]["client"]
    # api.py now raises PremiumRequiredError directly on 403 premium_required
    # responses (task-1416). The legacy "string-parse the exception message"
    # path is gone; the API layer hands a typed error up the stack.
    client.async_post = AsyncMock(
        side_effect=PremiumRequiredError(
            feature="household.presence_scaling",
            upgrade_url="https://culiplan.com/premium?source=ha",
        )
    )

    async_register_phase2_services(hass)
    from custom_components.culiplan.services import SERVICE_SCALE_TONIGHT_SERVINGS

    handler = _registered_handler(hass, SERVICE_SCALE_TONIGHT_SERVINGS)

    call_data = MagicMock()
    call_data.data = {"present_count": 2}

    # The premium repair issue is now created via repairs.py, which calls
    # homeassistant.helpers.issue_registry directly. Patch at the source.
    with patch(
        "custom_components.culiplan.repairs.ir.async_create_issue"
    ) as mock_create:
        with pytest.raises(PremiumRequiredError):
            await handler(call_data)
        # Repairs upsell issue must be created (task-1379 AC#1)
        mock_create.assert_called_once()
        issue_kwargs = mock_create.call_args[1]
        assert "premium_required" in issue_kwargs["issue_id"]


# ─── Test: error type constructors ────────────────────────────────────────────


def test_pantry_item_not_found_error_message():
    from custom_components.culiplan.services import PantryItemNotFoundError

    err = PantryItemNotFoundError("0000001234567")
    # str() returns the translation_key in test (no translation cache);
    # check the structured fields the renderer uses instead.
    assert err.barcode == "0000001234567"
    assert err.translation_key == "pantry_item_not_found"
    assert err.translation_placeholders["barcode"] == "0000001234567"


def test_insufficient_stock_error_message():
    from custom_components.culiplan.services import InsufficientStockError

    err = InsufficientStockError("item123", 0.5, 2.0)
    assert err.pantry_item_id == "item123"
    assert err.translation_key == "insufficient_stock"
    assert err.translation_placeholders["item_id"] == "item123"


def test_premium_required_error_message():
    from custom_components.culiplan.services import PremiumRequiredError

    err = PremiumRequiredError(
        "household.presence_scaling", "https://culiplan.com/premium"
    )
    assert "premium_scaling" in err.feature.replace(".", "_") or "presence" in str(err)
    assert err.upgrade_url == "https://culiplan.com/premium"
