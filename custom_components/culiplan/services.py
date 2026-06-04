"""
Culiplan HA services — merged AI dispatcher chain + pantry/household automations.

AI services (tasks 1388, 1389):
    culiplan.suggest_meal              — 3-mode AI meal suggestion
    culiplan.fill_shopping_list        — 3-mode AI shopping list fill

Pantry / household services (tasks 1376, 1378, 1379):
    culiplan.pantry_decrement          — barcode-scan decrement (free)
    culiplan.pantry_expiring_items     — list expiring items (free)
    culiplan.scale_tonight_servings    — presence-based serving scale (PREMIUM)

Blueprint generation service (task 1400):
    culiplan.generate_blueprint        — AI-composed HA blueprint (PREMIUM for Cloud AI)

Architecture:
    - Tier rules live ONLY on the backend (§11.1.5). Premium-gated services
      receive a structured 403 → PremiumRequiredError → Repairs upsell.
    - 404 from pantry_decrement creates a barcode-not-found Repairs issue.
    - Event payloads from the backend are ID-only (§14.3).
    - For BYOK / Local AI modes the backend returns only the prompt envelope;
      the dispatcher executes the AI call locally — keys never leave HA (§13.2).
"""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    DOMAIN,
)
from .ai.debug_logger import setup_debug_log_purge
from .ai.key_store import BYOKKeyStore
from .ai.service import AIDispatchService
from .ai.types import PremiumRequiredError
from .api import CuliplanApiClient
from .repairs import async_create_premium_repair, async_resolve_premium_repair

_LOGGER = logging.getLogger(__name__)

# AI services (Sonnet-A2)
SERVICE_SUGGEST_MEAL = "suggest_meal"
SERVICE_FILL_SHOPPING_LIST = "fill_shopping_list"

# Pantry / household services (Sonnet-D)
SERVICE_PANTRY_DECREMENT = "pantry_decrement"
SERVICE_PANTRY_EXPIRING = "pantry_expiring_items"
SERVICE_SCALE_TONIGHT_SERVINGS = "scale_tonight_servings"

# Blueprint generation service (task-1400)
SERVICE_GENERATE_BLUEPRINT = "generate_blueprint"

SUGGEST_MEAL_SCHEMA = vol.Schema(
    {
        vol.Optional("constraints"): str,
        vol.Optional("meal_slot"): vol.In(["breakfast", "lunch", "dinner", "snack"]),
        vol.Optional("max_time_minutes"): vol.Coerce(int),
    }
)

FILL_SHOPPING_LIST_SCHEMA = vol.Schema(
    {
        vol.Optional("week_offset"): vol.Coerce(int),
    }
)

PANTRY_DECREMENT_SCHEMA = vol.Schema(
    {
        vol.Required("barcode"): str,
        vol.Optional("qty", default=1): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
    }
)

PANTRY_EXPIRING_SCHEMA = vol.Schema(
    {
        vol.Optional("window_hours", default=48): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=720)
        ),
    }
)

SCALE_TONIGHT_SERVINGS_SCHEMA = vol.Schema(
    {
        vol.Required("present_count"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional("plan_date"): str,
    }
)

GENERATE_BLUEPRINT_SCHEMA = vol.Schema(
    {
        vol.Required("prompt"): vol.All(str, vol.Length(min=5, max=2000)),
        vol.Optional("available_entities"): vol.All(
            list,
            vol.Length(max=100),
            [str],
        ),
        vol.Optional("install", default=False): bool,
    }
)


# PremiumRequiredError is imported from .ai.types (task-1416: moved to shared
# module so both api.py and services.py can use it without circular imports).


class PantryItemNotFoundError(HomeAssistantError):
    """Raised when a barcode is not found in the user's pantry."""

    def __init__(self, barcode: str) -> None:
        self.barcode = barcode
        super().__init__(
            f"No pantry item with barcode '{barcode}' found. "
            "Add the item to your pantry in Culiplan first."
        )


class InsufficientStockError(HomeAssistantError):
    """Raised when a pantry item has insufficient stock."""

    def __init__(self, pantry_item_id: str, available: float, requested: float) -> None:
        self.pantry_item_id = pantry_item_id
        super().__init__(
            f"Not enough stock (item={pantry_item_id}): "
            f"requested {requested}, available {available}."
        )


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
    """Remove the barcode-not-found Repairs issue."""
    ir.async_delete_issue(hass, DOMAIN, f"pantry_barcode_not_found_{barcode}")


async def _run_cloud_intent(
    client: CuliplanApiClient,
    intent: str,
    params: dict[str, Any],
) -> str:
    """Execute a Cloud AI intent via the Culiplan backend."""
    try:
        result = await client.async_call_voice_tool(intent, params)
        return result.get("speakable") or result.get("message") or "Done."
    except PremiumRequiredError:
        # Already typed — re-raise directly so the caller can create the
        # Repairs upsell issue (task-1416: no string parsing needed).
        raise
    except Exception as exc:
        raise HomeAssistantError(f"Culiplan AI request failed: {exc}") from exc


def _build_dispatch_mode(ai_mode: str, entry_config: dict[str, Any]) -> str:
    """Map the flat ai_mode + config entry options to the compound dispatcher key.

    The dispatcher factory (dispatchers.create_dispatcher) accepts only compound
    strings: "byok-openai", "byok-anthropic", "byok-gemini", "local-ollama",
    "local-lmstudio".  Config entry data stores just "byok" or "local" together
    with provider/endpoint fields.  This function resolves the compound key so
    AIDispatchService never receives the bare flat strings.
    """
    if ai_mode == AI_MODE_BYOK:
        provider = entry_config.get(CONF_BYOK_PROVIDER, "openai")
        # BYOK_PROVIDERS uses "google" but the dispatcher key is "byok-gemini"
        dispatcher_provider = "gemini" if provider == "google" else provider
        return f"byok-{dispatcher_provider}"
    if ai_mode == AI_MODE_LOCAL:
        endpoint = entry_config.get(CONF_LOCAL_ENDPOINT, "")
        # Derive from port: LM Studio uses 1234, Ollama uses 11434 (default).
        try:
            from urllib.parse import urlparse as _urlparse

            port = _urlparse(
                endpoint if "://" in endpoint else f"http://{endpoint}"
            ).port
            return "local-lmstudio" if port == 1234 else "local-ollama"
        except Exception:  # noqa: BLE001
            return "local-ollama"
    # Cloud mode — not handled by this function but return as-is for safety
    return ai_mode


async def _run_byok_or_local_intent(
    hass: HomeAssistant,
    entry_data: dict[str, Any],
    entry_config: dict[str, Any],
    client: CuliplanApiClient,
    intent: str,
    params: dict[str, Any],
) -> str:
    """Execute a BYOK or Local AI intent."""
    ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)
    api_key = ""
    base_url = None
    debug = entry_data.get("options", {}).get("debug_ai", False)
    config_dir: str | None = getattr(hass.config, "config_dir", None)

    # task-1410: when debug mode is active, register the hourly purge job so
    # that prompt log files are automatically removed after 24h.
    if debug and config_dir:
        setup_debug_log_purge(hass)

    if ai_mode == AI_MODE_BYOK:
        provider = entry_config.get(CONF_BYOK_PROVIDER, "")
        key_store = BYOKKeyStore(hass)
        await key_store.async_load()
        api_key = key_store.get_key(provider) or ""
        if not api_key:
            raise HomeAssistantError(
                f"No BYOK key found for provider '{provider}'. "
                "Please reconfigure the Culiplan integration."
            )
    elif ai_mode == AI_MODE_LOCAL:
        endpoint = entry_config.get(CONF_LOCAL_ENDPOINT, "")
        base_url = _ensure_v1_path(endpoint) if endpoint else None
        api_key = "local"

    # Build the compound mode string that the dispatcher factory expects
    # (e.g. "byok-openai", "local-ollama") rather than the bare "byok"/"local".
    dispatch_mode = _build_dispatch_mode(ai_mode, entry_config)

    service = AIDispatchService(
        mode=dispatch_mode,
        culiplan_client=client,
        api_key=api_key,
        base_url=base_url,
        debug=debug,
        config_dir=config_dir,
    )

    result = await service.run_intent(intent, params)
    return result.text or "I couldn't generate a response. Please try again."


def _ensure_v1_path(endpoint: str) -> str:
    """Ensure the endpoint URL ends with /v1 for OpenAI-compat SDKs."""
    url = endpoint.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


async def _call_pantry_decrement(
    client: CuliplanApiClient,
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
            available = 0.0
            try:
                import json

                if "{" in exc_str:
                    body = json.loads(exc_str[exc_str.index("{") :])
                    available = float(body.get("available", 0))
            except (ValueError, KeyError):
                pass
            raise InsufficientStockError(barcode, available, qty) from exc
        raise HomeAssistantError(f"Pantry decrement failed: {exc_str}") from exc


async def _call_pantry_expiring(
    client: CuliplanApiClient,
    window_hours: int,
) -> dict[str, Any]:
    """Call GET /api/ha/pantry/expiring?window_hours=N."""
    try:
        return cast(
            dict[str, Any],
            await client._get(  # noqa: SLF001
                f"/api/ha/pantry/expiring?window_hours={window_hours}"
            ),
        )
    except Exception as exc:
        raise HomeAssistantError(f"Pantry expiring fetch failed: {exc}") from exc


async def _call_scale_servings(
    client: CuliplanApiClient,
    present_count: int,
    plan_date: str | None,
) -> dict[str, Any]:
    """Call POST /api/ha/servings/scale (premium-gated)."""
    payload: dict[str, Any] = {"present_count": present_count}
    if plan_date:
        payload["plan_date"] = plan_date
    try:
        return await client.async_post("/api/ha/servings/scale", payload)
    except PremiumRequiredError:
        # api.py now raises PremiumRequiredError directly for 403 premium_required
        # responses (task-1416: no string parsing needed).
        raise
    except HomeAssistantError:
        raise
    except Exception as exc:
        raise HomeAssistantError(f"Scale servings failed: {exc}") from exc


def async_register_services(hass: HomeAssistant) -> None:
    """Register ALL Culiplan HA services (AI + pantry/household)."""

    async def handle_suggest_meal(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        entry_data = hass.data[DOMAIN][entry_id]
        client: CuliplanApiClient = entry_data["client"]
        entries = hass.config_entries.async_entries(DOMAIN)
        entry = next((e for e in entries if e.entry_id == entry_id), None)
        entry_config = entry.data if entry else {}
        ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)
        params = {
            k: v
            for k, v in {
                "constraints": call.data.get("constraints"),
                "mealSlot": call.data.get("meal_slot"),
                "maxTimeMinutes": call.data.get("max_time_minutes"),
            }.items()
            if v is not None
        }
        try:
            if ai_mode == AI_MODE_CLOUD:
                text = await _run_cloud_intent(client, "suggest_meal", params)
            else:
                text = await _run_byok_or_local_intent(
                    hass, entry_data, entry_config, client, "suggest_meal", params
                )
        except PremiumRequiredError as exc:
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise
        async_resolve_premium_repair(hass, "ai.suggestion")
        hass.bus.async_fire(
            f"{DOMAIN}_suggest_meal_result",
            {"result": text, "mode": ai_mode},
        )
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Culiplan Meal Suggestion",
                "message": text,
                "notification_id": f"{DOMAIN}_suggest_meal",
            },
        )

    async def handle_fill_shopping_list(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        entry_data = hass.data[DOMAIN][entry_id]
        client: CuliplanApiClient = entry_data["client"]
        entries = hass.config_entries.async_entries(DOMAIN)
        entry = next((e for e in entries if e.entry_id == entry_id), None)
        entry_config = entry.data if entry else {}
        ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)
        params: dict[str, Any] = {}
        if call.data.get("week_offset") is not None:
            params["weekOffset"] = call.data["week_offset"]
        try:
            if ai_mode == AI_MODE_CLOUD:
                text = await _run_cloud_intent(client, "fill_shopping_list", params)
            else:
                text = await _run_byok_or_local_intent(
                    hass,
                    entry_data,
                    entry_config,
                    client,
                    "fill_shopping_list",
                    params,
                )
        except PremiumRequiredError as exc:
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise
        # task-1417 fix: resolve THIS feature's repair, not 'ai.suggestion'
        async_resolve_premium_repair(hass, "ai.shopping_fill")
        hass.bus.async_fire(
            f"{DOMAIN}_fill_shopping_list_result",
            {"result": text, "mode": ai_mode},
        )
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Culiplan Shopping List",
                "message": text,
                "notification_id": f"{DOMAIN}_fill_shopping_list",
            },
        )

    async def handle_pantry_decrement(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        client: CuliplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        barcode: str = call.data["barcode"]
        qty: float = call.data["qty"]
        try:
            result = await _call_pantry_decrement(client, barcode, qty)
            _resolve_barcode_repair(hass, barcode)
            _LOGGER.info(
                "[culiplan] Pantry decremented: barcode=%s qty=%s item=%s",
                barcode,
                qty,
                result.get("pantryItemId"),
            )
        except PantryItemNotFoundError as exc:
            _create_barcode_not_found_repair(hass, exc.barcode)
            raise

    async def handle_pantry_expiring(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        client: CuliplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        window_hours: int = call.data["window_hours"]
        result = await _call_pantry_expiring(client, window_hours)
        hass.bus.async_fire(
            f"{DOMAIN}_pantry_expiring_result",
            {
                "window_hours": window_hours,
                "count": result.get("count", 0),
                "item_ids": [item["pantryItemId"] for item in result.get("items", [])],
            },
        )

    async def handle_scale_tonight_servings(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        client: CuliplanApiClient = hass.data[DOMAIN][entry_id]["client"]
        present_count: int = call.data["present_count"]
        plan_date: str | None = call.data.get("plan_date")
        try:
            result = await _call_scale_servings(client, present_count, plan_date)
            async_resolve_premium_repair(hass, "household.presence_scaling")
            _LOGGER.info(
                "[culiplan] Servings scaled: present=%d slots=%d date=%s",
                present_count,
                result.get("slotsUpdated", 0),
                result.get("date", "today"),
            )
        except PremiumRequiredError as exc:
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise

    # Blueprint generation service (task-1400)
    from .blueprint_generator import handle_generate_blueprint as _handle_bp_gen

    async def handle_generate_blueprint(call: ServiceCall) -> None:
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        await _handle_bp_gen(hass, call, entry_id)

    registrations = [
        (SERVICE_SUGGEST_MEAL, handle_suggest_meal, SUGGEST_MEAL_SCHEMA),
        (
            SERVICE_FILL_SHOPPING_LIST,
            handle_fill_shopping_list,
            FILL_SHOPPING_LIST_SCHEMA,
        ),
        (SERVICE_PANTRY_DECREMENT, handle_pantry_decrement, PANTRY_DECREMENT_SCHEMA),
        (SERVICE_PANTRY_EXPIRING, handle_pantry_expiring, PANTRY_EXPIRING_SCHEMA),
        (
            SERVICE_SCALE_TONIGHT_SERVINGS,
            handle_scale_tonight_servings,
            SCALE_TONIGHT_SERVINGS_SCHEMA,
        ),
        (
            SERVICE_GENERATE_BLUEPRINT,
            handle_generate_blueprint,
            GENERATE_BLUEPRINT_SCHEMA,
        ),
    ]
    for name, handler, schema in registrations:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all Culiplan HA services."""
    for name in (
        SERVICE_SUGGEST_MEAL,
        SERVICE_FILL_SHOPPING_LIST,
        SERVICE_PANTRY_DECREMENT,
        SERVICE_PANTRY_EXPIRING,
        SERVICE_SCALE_TONIGHT_SERVINGS,
        SERVICE_GENERATE_BLUEPRINT,
    ):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)


# Backwards-compatible aliases (Sonnet-D used different names)
async_register_phase2_services = async_register_services
async_unregister_phase2_services = async_unregister_services


def _find_entry_id(hass: HomeAssistant) -> str | None:
    """Return the first active Culiplan config entry ID, or None."""
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries), None)
