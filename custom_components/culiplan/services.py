"""
Flavorplan HA services — Phase 2 Pantry & Dinner Party Automations.

Phase 2 tasks implemented here:
    flavorplan.pantry_decrement          — task-1376: barcode-scan decrement
    flavorplan.pantry_expiring_items     — task-1378: list expiring pantry items
    flavorplan.scale_tonight_servings    — task-1379: presence-based serving scale (PREMIUM)

Design notes:
    - All services call the backend REST API via FlavorplanApiClient.
    - 404 from pantry_decrement surfaces as a HA Repairs issue (task-1376 AC#2).
    - scale_tonight_servings is gated: free users receive a 403 from the backend
      which is translated into a PremiumRequiredError and a Repairs upsell
      (task-1379 AC#1). No tier logic lives in the integration (§11.1.5).
    - Event payloads from the backend are ID-only (§14.3); the coordinator
      re-fetches detail via REST when it receives a pantry.item.updated event.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from .api import FlavorplanApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ─── Service names ─────────────────────────────────────────────────────────────

SERVICE_PANTRY_DECREMENT = "pantry_decrement"
SERVICE_PANTRY_EXPIRING = "pantry_expiring_items"
SERVICE_SCALE_TONIGHT_SERVINGS = "scale_tonight_servings"

# ─── Service schemas ───────────────────────────────────────────────────────────

PANTRY_DECREMENT_SCHEMA = vol.Schema({
    vol.Required("barcode"): str,
    vol.Optional("qty", default=1): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
})

PANTRY_EXPIRING_SCHEMA = vol.Schema({
    vol.Optional("window_hours", default=48): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
})

SCALE_TONIGHT_SERVINGS_SCHEMA = vol.Schema({
    vol.Required("present_count"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional("plan_date"): str,  # YYYY-MM-DD; defaults to today on backend
})


# ─── Error types ───────────────────────────────────────────────────────────────

class PantryItemNotFoundError(HomeAssistantError):
    """Raised when a barcode is not found in the user's pantry."""

    def __init__(self, barcode: str) -> None:
        self.barcode = barcode
        super().__init__(
            f"No pantry item with barcode '{barcode}' found. "
            "Add the item to your pantry in Flavorplan first."
        )


class InsufficientStockError(HomeAssistantError):
    """Raised when a pantry item has insufficient stock for the requested decrement."""

    def __init__(self, pantry_item_id: str, available: float, requested: float) -> None:
        self.pantry_item_id = pantry_item_id
        super().__init__(
            f"Not enough stock (item={pantry_item_id}): "
            f"requested {requested}, available {available}."
        )


class PremiumRequiredError(HomeAssistantError):
    """Raised when a premium-gated feature is invoked by a free-tier user.

    The Repairs UI handler catches this and creates a Repairs issue with
    an upgrade deep-link.
    """

    def __init__(self, feature: str, upgrade_url: str) -> None:
        self.feature = feature
        self.upgrade_url = upgrade_url
        super().__init__(
            f"'{feature}' requires Flavorplan Premium. Upgrade at: {upgrade_url}"
        )


# ─── Repairs helpers ───────────────────────────────────────────────────────────

_REPAIR_UPGRADE_URL = "https://culiplan.com/premium?source=ha"


def _create_barcode_not_found_repair(hass: HomeAssistant, barcode: str) -> None:
    """Create a HA Repairs issue when a barcode is not found in the pantry."""
    ir.async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=f"pantry_barcode_not_found_{barcode}",
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="pantry_barcode_not_found",
        translation_placeholders={"barcode": barcode},
        learn_more_url="https://culiplan.com/pantry",
    )


def _resolve_barcode_repair(hass: HomeAssistant, barcode: str) -> None:
    """Remove the barcode-not-found Repairs issue for a given barcode."""
    ir.async_delete_issue(hass, DOMAIN, f"pantry_barcode_not_found_{barcode}")


def _create_premium_repair(hass: HomeAssistant, feature: str, upgrade_url: str) -> None:
    """Create a Repairs upsell issue for a premium-gated feature."""
    safe_feature = feature.replace(".", "_").replace("/", "_").replace(" ", "_")
    ir.async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=f"premium_required_{safe_feature}",
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="premium_required",
        translation_placeholders={
            "feature": feature,
            "upgrade_url": upgrade_url,
        },
        learn_more_url=upgrade_url,
    )


# ─── API helpers ──────────────────────────────────────────────────────────────

async def _call_pantry_decrement(
    client: FlavorplanApiClient,
    barcode: str,
    qty: float,
) -> dict[str, Any]:
    """Call POST /api/ha/pantry/decrement and translate structured errors."""
    try:
        return await client.async_post(
            "/api/ha/pantry/decrement",
            {"barcode": barcode, "qty": qty},
        )
    except Exception as exc:
        exc_str = str(exc)
        if "404" in exc_str or "PANTRY_ITEM_NOT_FOUND" in exc_str:
            raise PantryItemNotFoundError(barcode) from exc
        if "422" in exc_str or "INSUFFICIENT_STOCK" in exc_str:
            # Try to extract available qty from structured error body
            available = 0.0
            try:
                import json as _json
                if "{" in exc_str:
                    body = _json.loads(exc_str[exc_str.index("{"):])
                    available = float(body.get("available", 0))
            except (ValueError, KeyError):
                pass
            raise InsufficientStockError(barcode, available, qty) from exc
        if "403" in exc_str or "premium_required" in exc_str:
            upgrade_url = _REPAIR_UPGRADE_URL
            try:
                import json as _json
                if "{" in exc_str:
                    body = _json.loads(exc_str[exc_str.index("{"):])
                    upgrade_url = body.get("upgradeUrl", upgrade_url)
            except (ValueError, KeyError):
                pass
            raise PremiumRequiredError(feature="household.presence_scaling", upgrade_url=upgrade_url) from exc
        raise HomeAssistantError(f"Pantry decrement failed: {exc_str}") from exc


async def _call_pantry_expiring(
    client: FlavorplanApiClient,
    window_hours: int,
) -> dict[str, Any]:
    """Call GET /api/ha/pantry/expiring?window_hours=N."""
    try:
        return await client.async_get(f"/api/ha/pantry/expiring?window_hours={window_hours}")
    except Exception as exc:
        raise HomeAssistantError(f"Pantry expiring fetch failed: {exc}") from exc


async def _call_scale_servings(
    client: FlavorplanApiClient,
    present_count: int,
    plan_date: str | None,
) -> dict[str, Any]:
    """Call POST /api/ha/servings/scale."""
    payload: dict[str, Any] = {"present_count": present_count}
    if plan_date:
        payload["plan_date"] = plan_date
    try:
        return await client.async_post("/api/ha/servings/scale", payload)
    except Exception as exc:
        exc_str = str(exc)
        if "403" in exc_str or "premium_required" in exc_str:
            upgrade_url = _REPAIR_UPGRADE_URL
            try:
                import json as _json
                if "{" in exc_str:
                    body = _json.loads(exc_str[exc_str.index("{"):])
                    upgrade_url = body.get("upgradeUrl", upgrade_url)
            except (ValueError, KeyError):
                pass
            raise PremiumRequiredError(
                feature="household.presence_scaling",
                upgrade_url=upgrade_url,
            ) from exc
        if "404" in exc_str or "NO_MEAL_PLAN" in exc_str:
            raise HomeAssistantError(
                "No meal plan found for the requested date. "
                "Make sure you have a meal planned in Flavorplan."
            ) from exc
        raise HomeAssistantError(f"Scale servings failed: {exc_str}") from exc


# ─── Service registration ──────────────────────────────────────────────────────

def async_register_phase2_services(hass: HomeAssistant) -> None:
    """Register all Phase 2 Flavorplan HA services (tasks 1376, 1378, 1379)."""

    async def handle_pantry_decrement(call: ServiceCall) -> None:
        """
        Service handler for flavorplan.pantry_decrement.

        task-1376 AC#1 — translates barcode to PantryItem via backend REST.
        task-1376 AC#2 — 404 creates a Repairs issue so user can add the item.
        task-1376 AC#4 — the backend emits pantry.item.updated via Socket.IO;
                          coordinator refreshes automatically.
        """
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Flavorplan is not configured.")

        client: FlavorplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        barcode: str = call.data["barcode"]
        qty: float = call.data["qty"]

        try:
            result = await _call_pantry_decrement(client, barcode, qty)
            # If we previously had a repair for this barcode, resolve it
            _resolve_barcode_repair(hass, barcode)
            _LOGGER.info(
                "[flavorplan] Pantry decremented: barcode=%s qty=%s item=%s",
                barcode,
                qty,
                result.get("pantryItemId"),
            )
        except PantryItemNotFoundError as exc:
            # task-1376 AC#2 — create Repairs issue
            _create_barcode_not_found_repair(hass, exc.barcode)
            raise
        except InsufficientStockError:
            # Propagate as HomeAssistantError — HA will show it in service call UI
            raise

    async def handle_pantry_expiring(call: ServiceCall) -> None:
        """
        Service handler for flavorplan.pantry_expiring_items.

        task-1378 AC#2 — returns per-item expiry attributes for automation routing.
        The result is stored as a HA event so blueprints can consume it.
        """
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Flavorplan is not configured.")

        client: FlavorplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        window_hours: int = call.data["window_hours"]

        result = await _call_pantry_expiring(client, window_hours)

        # Fire a HA event so blueprints can react (task-1378 AC#2)
        hass.bus.async_fire(
            f"{DOMAIN}_pantry_expiring_result",
            {
                "window_hours": window_hours,
                "count": result.get("count", 0),
                # item IDs only — no names or PII (§14.3)
                "item_ids": [
                    item["pantryItemId"]
                    for item in result.get("items", [])
                ],
            },
        )

        _LOGGER.info(
            "[flavorplan] Pantry expiring items fetched: %d items within %dh",
            result.get("count", 0),
            window_hours,
        )

    async def handle_scale_tonight_servings(call: ServiceCall) -> None:
        """
        Service handler for flavorplan.scale_tonight_servings.

        task-1379 AC#1 — gated by premium on the backend (403 → PremiumRequiredError).
        task-1379 AC#2 — backend records present_count and emits meal_plan.updated;
                          coordinator re-fetches automatically.
        """
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Flavorplan is not configured.")

        client: FlavorplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        present_count: int = call.data["present_count"]
        plan_date: str | None = call.data.get("plan_date")

        try:
            result = await _call_scale_servings(client, present_count, plan_date)
            _LOGGER.info(
                "[flavorplan] Servings scaled: present_count=%d slots_updated=%d date=%s",
                present_count,
                result.get("slotsUpdated", 0),
                result.get("date", "today"),
            )
        except PremiumRequiredError as exc:
            _create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise

    # ── Register all three services ────────────────────────────────────────────

    if not hass.services.has_service(DOMAIN, SERVICE_PANTRY_DECREMENT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PANTRY_DECREMENT,
            handle_pantry_decrement,
            schema=PANTRY_DECREMENT_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PANTRY_EXPIRING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PANTRY_EXPIRING,
            handle_pantry_expiring,
            schema=PANTRY_EXPIRING_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SCALE_TONIGHT_SERVINGS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SCALE_TONIGHT_SERVINGS,
            handle_scale_tonight_servings,
            schema=SCALE_TONIGHT_SERVINGS_SCHEMA,
        )


def async_unregister_phase2_services(hass: HomeAssistant) -> None:
    """Unregister Phase 2 Flavorplan HA services."""
    for svc in (SERVICE_PANTRY_DECREMENT, SERVICE_PANTRY_EXPIRING, SERVICE_SCALE_TONIGHT_SERVINGS):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)


def _find_entry_id(hass: HomeAssistant) -> str | None:
    """Return the first active Flavorplan config entry ID, or None."""
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries), None)
