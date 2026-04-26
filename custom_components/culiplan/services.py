"""
Flavorplan HA services (task-1388 + task-1389).

Registers:
    flavorplan.suggest_meal        — 3-mode AI meal suggestion
    flavorplan.fill_shopping_list  — 3-mode AI shopping list fill

Architecture (§13.1 three execution modes):

    Cloud AI (premium):
        → POST /api/voice/ha-assist with tool=suggest_meal
        → backend executes on Flavorplan infrastructure (Gemini/Vertex AI)
        → 403 {error: 'premium_required'} for free users → HA Repairs upsell

    BYOK (free, HA-exclusive):
        → POST /api/ai/envelope to get prompt envelope
        → dispatcher.dispatch() locally (API key in HA secrets, never leaves HA)
        → tool calls route back via FlavorplanApiClient
        → loop until final response

    Local AI (free, HA-exclusive):
        → same as BYOK but uses local endpoint (Ollama / LM Studio)
        → no outbound calls beyond LAN

All three modes use the same tool spec from the backend (single source of
truth per §13.3).  The mode-specific code lives only here and in the
dispatcher layer.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.exceptions import HomeAssistantError

from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    DOMAIN,
)
from .ai.dispatchers import create_dispatcher
from .ai.key_store import BYOKKeyStore
from .ai.service import AIDispatchService
from .api import FlavorplanApiClient
from .repairs import async_create_premium_repair, async_resolve_premium_repair

_LOGGER = logging.getLogger(__name__)

# ─── Service names ─────────────────────────────────────────────────────────────

SERVICE_SUGGEST_MEAL = "suggest_meal"
SERVICE_FILL_SHOPPING_LIST = "fill_shopping_list"

# ─── Service schemas ───────────────────────────────────────────────────────────

SUGGEST_MEAL_SCHEMA = vol.Schema({
    vol.Optional("constraints"): str,
    vol.Optional("meal_slot"): vol.In(["breakfast", "lunch", "dinner", "snack"]),
    vol.Optional("max_time_minutes"): vol.Coerce(int),
})

FILL_SHOPPING_LIST_SCHEMA = vol.Schema({
    vol.Optional("week_offset"): vol.Coerce(int),
})


# ─── Premium-required handling ─────────────────────────────────────────────────

class PremiumRequiredError(HomeAssistantError):
    """
    Raised when a premium-gated feature is invoked by a free-tier user.

    The repair UI handler (task-1395) catches this and creates a Repairs issue
    with an upgrade deep-link.
    """
    def __init__(self, feature: str, upgrade_url: str) -> None:
        self.feature = feature
        self.upgrade_url = upgrade_url
        super().__init__(
            f"'{feature}' requires Flavorplan Premium. Upgrade at: {upgrade_url}"
        )


# ─── Cloud AI path ─────────────────────────────────────────────────────────────

async def _run_cloud_intent(
    client: FlavorplanApiClient,
    intent: str,
    params: dict[str, Any],
) -> str:
    """
    Execute a Cloud AI intent via the Flavorplan backend.

    For free users, the backend returns 403 {error: 'premium_required'}.
    This function raises PremiumRequiredError which triggers the Repairs upsell.
    """
    try:
        result = await client.async_call_voice_tool(intent, params)
        return result.get("speakable") or result.get("message") or "Done."
    except Exception as exc:
        exc_str = str(exc)
        # Check for 403 premium_required response
        if "403" in exc_str or "premium_required" in exc_str:
            # Try to extract upgradeUrl from the error body
            upgrade_url = "https://culiplan.com/premium?source=ha"
            try:
                import json
                # exc might wrap the response body in its message
                if "{" in exc_str:
                    body = json.loads(exc_str[exc_str.index("{"):])
                    upgrade_url = body.get("upgradeUrl", upgrade_url)
            except (ValueError, KeyError):
                pass
            raise PremiumRequiredError(feature=intent, upgrade_url=upgrade_url) from exc
        raise HomeAssistantError(
            f"Flavorplan AI request failed: {exc_str}"
        ) from exc


# ─── BYOK / Local AI path ──────────────────────────────────────────────────────

async def _run_byok_or_local_intent(
    hass: HomeAssistant,
    entry_data: dict[str, Any],
    entry_config: dict[str, Any],
    client: FlavorplanApiClient,
    intent: str,
    params: dict[str, Any],
) -> str:
    """
    Execute a BYOK or Local AI intent.

    1. Determines mode, key (for BYOK), and endpoint (for Local).
    2. Creates AIDispatchService.
    3. Calls run_intent() which fetches the envelope and runs the multi-turn loop.
    """
    ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)
    api_key = ""
    base_url = None
    debug = entry_data.get("options", {}).get("debug_ai", False)

    if ai_mode == AI_MODE_BYOK:
        provider = entry_config.get(CONF_BYOK_PROVIDER, "")
        # Load key from HA local storage (never from config entry)
        key_store = BYOKKeyStore(hass)
        await key_store.async_load()
        api_key = key_store.get_key(provider) or ""
        if not api_key:
            raise HomeAssistantError(
                f"No BYOK key found for provider '{provider}'. "
                "Please reconfigure the Flavorplan integration."
            )
    elif ai_mode == AI_MODE_LOCAL:
        endpoint = entry_config.get(CONF_LOCAL_ENDPOINT, "")
        base_url = _ensure_v1_path(endpoint) if endpoint else None
        # Local endpoints use a placeholder key
        api_key = "local"

    service = AIDispatchService(
        mode=ai_mode,
        flavorplan_client=client,
        api_key=api_key,
        base_url=base_url,
        debug=debug,
    )

    result = await service.run_intent(intent, params)
    return result.text or "I couldn't generate a response. Please try again."


def _ensure_v1_path(endpoint: str) -> str:
    """Ensure the endpoint URL ends with /v1 for OpenAI-compat SDKs."""
    url = endpoint.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


# ─── Service registration ──────────────────────────────────────────────────────

def async_register_services(hass: HomeAssistant) -> None:
    """Register all Flavorplan HA services."""

    async def handle_suggest_meal(call: ServiceCall) -> None:
        """
        Service handler for flavorplan.suggest_meal.

        Three modes (per §13.1):
          - cloud: backend executes (premium required)
          - byok:  HA dispatches to provider using stored key
          - local: HA dispatches to local endpoint
        """
        # Find the active Flavorplan config entry
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Flavorplan is not configured.")

        entry_data = hass.data[DOMAIN][entry_id]
        client: FlavorplanApiClient = entry_data["client"]

        # Get AI mode from config entry
        from homeassistant.config_entries import ConfigEntries
        entries = hass.config_entries.async_entries(DOMAIN)
        entry = next((e for e in entries if e.entry_id == entry_id), None)
        entry_config = entry.data if entry else {}

        ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)

        params = {
            k: v for k, v in {
                "constraints":       call.data.get("constraints"),
                "mealSlot":          call.data.get("meal_slot"),
                "maxTimeMinutes":    call.data.get("max_time_minutes"),
            }.items() if v is not None
        }

        try:
            if ai_mode == AI_MODE_CLOUD:
                text = await _run_cloud_intent(client, "suggest_meal", params)
            else:
                text = await _run_byok_or_local_intent(
                    hass, entry_data, entry_config, client, "suggest_meal", params
                )
        except PremiumRequiredError as exc:
            # AC#4 (task-1388) + task-1395 AC#1: create Repairs upsell issue
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise

        # AC#4 (task-1395): auto-resolve any previous premium repair for this feature
        async_resolve_premium_repair(hass, "ai.suggestion")

        # Fire an event so automations and dashboards can react
        hass.bus.async_fire(
            f"{DOMAIN}_suggest_meal_result",
            {"result": text, "mode": ai_mode},
        )

        # Create a persistent notification for UI feedback
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Flavorplan Meal Suggestion",
                "message": text,
                "notification_id": f"{DOMAIN}_suggest_meal",
            },
        )

    async def handle_fill_shopping_list(call: ServiceCall) -> None:
        """
        Service handler for flavorplan.fill_shopping_list.

        Same 3-mode architecture as suggest_meal.
        Runs the fill_shopping_list intent which returns a summary of items added.
        """
        entry_id = _find_entry_id(hass)
        if not entry_id:
            raise HomeAssistantError("Flavorplan is not configured.")

        entry_data = hass.data[DOMAIN][entry_id]
        client: FlavorplanApiClient = entry_data["client"]

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
                    hass, entry_data, entry_config, client, "fill_shopping_list", params
                )
        except PremiumRequiredError as exc:
            # task-1395 AC#1: create Repairs upsell issue for shopping fill
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise

        # task-1395 AC#4: auto-resolve any previous premium repair for this feature
        async_resolve_premium_repair(hass, "ai.suggestion")

        hass.bus.async_fire(
            f"{DOMAIN}_fill_shopping_list_result",
            {"result": text, "mode": ai_mode},
        )

        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Flavorplan Shopping List",
                "message": text,
                "notification_id": f"{DOMAIN}_fill_shopping_list",
            },
        )

    # Register services
    if not hass.services.has_service(DOMAIN, SERVICE_SUGGEST_MEAL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SUGGEST_MEAL,
            handle_suggest_meal,
            schema=SUGGEST_MEAL_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_FILL_SHOPPING_LIST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FILL_SHOPPING_LIST,
            handle_fill_shopping_list,
            schema=FILL_SHOPPING_LIST_SCHEMA,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all Flavorplan HA services."""
    hass.services.async_remove(DOMAIN, SERVICE_SUGGEST_MEAL)
    hass.services.async_remove(DOMAIN, SERVICE_FILL_SHOPPING_LIST)


def _find_entry_id(hass: HomeAssistant) -> str | None:
    """Return the first active Flavorplan config entry ID, or None."""
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries), None)
