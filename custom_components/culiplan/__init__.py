"""The Flavorplan integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow, intent

# ─── Lovelace resource auto-registration (task-1408) ─────────────────────────
#
# HACS installs the integration at <config>/custom_components/culiplan/.
# The Lovelace JS resources are served from the wwwroot under the HACS-
# standard path /hacsfiles/culiplan/<filename>.
#
# Decision on unload: resources are NOT auto-removed when the integration
# is unloaded/reloaded. Removing them would break dashboards that the user
# has customised to use these cards. The manual fallback path in
# lovelace/README.md remains valid and unchanged.
#
_LOVELACE_RESOURCES: tuple[dict[str, str], ...] = (
    {
        "url": "/hacsfiles/culiplan/lovelace/cards/dist/kitchen-dashboard.js",
        "res_type": "module",
    },
    {
        "url": "/hacsfiles/culiplan/lovelace/cards/dist/pantry-tracker.js",
        "res_type": "module",
    },
    {
        "url": "/hacsfiles/culiplan/lovelace/cards/dist/cooking-mode.js",
        "res_type": "module",
    },
)

from .api import FlavorplanApiClient
from .const import DOMAIN, PLATFORMS
from .coordinator import FlavorplanCoordinator
from .cooking_services import (
    async_register_cooking_services,
    async_unregister_cooking_services,
)
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

_INTENTS_DIR = Path(__file__).parent / "intents"

_INTENT_TO_TOOL: dict[str, str] = {
    "FlavorplanWhatsDinnerTonight": "whats_for_dinner",
    "FlavorplanGetWeekMeals": "get_week_meals",
    "FlavorplanGetShoppingList": "get_shopping_list",
    "FlavorplanAddToShoppingList": "add_to_shopping_list",
    "FlavorplanWhatsInPantry": "whats_in_pantry",
    "FlavorplanWhatsExpiringSoon": "get_expiring_pantry",
}

# Cooking-mode intents that map directly to HA services (task-1397).
# These call the local service rather than the remote voice-tool endpoint.
_COOKING_INTENT_TO_SERVICE: dict[str, str] = {
    "FlavorplanNextCookingStep": "advance_cooking_step",
    "FlavorplanSetRecipeTimer": "set_recipe_timer",
    "FlavorplanCancelRecipeTimer": "cancel_recipe_timer",
}


async def _async_register_lovelace_resources(hass: HomeAssistant) -> None:
    """
    Register Flavorplan Lovelace card resources idempotently (task-1408).

    Uses HA's internal Lovelace ResourceStorageCollection when available.
    Falls back gracefully if the Lovelace component is not yet loaded or
    if the storage collection API has changed (e.g. dev HA builds).

    Idempotency: checks whether a resource with the same URL is already
    registered before calling async_create_item — safe to call on every
    integration reload.

    Unload behaviour: resources are intentionally NOT removed on
    integration unload/reload (see _LOVELACE_RESOURCES comment above).
    """
    try:
        # HA exposes the Lovelace component lazily; load it to ensure the
        # resource collection is initialised.
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            # Not yet initialised — try to obtain via component loader.
            lovelace_component = hass.components.lovelace
            # Accessing .resources may raise AttributeError on older HA versions.
            resource_collection = getattr(
                lovelace_component, "resources", None
            ) or getattr(lovelace, "resources", None)
        else:
            resource_collection = getattr(lovelace, "resources", None)

        if resource_collection is None:
            _LOGGER.debug(
                "[culiplan] Lovelace resource collection not available — "
                "skipping auto-registration. Use lovelace/README.md for manual setup."
            )
            return

        # Build a set of already-registered URLs for O(1) lookup.
        try:
            existing_items = await resource_collection.async_items()
        except (AttributeError, TypeError):
            # Some HA builds use .async_load() then .data
            try:
                await resource_collection.async_load(True)
                existing_items = list(resource_collection.data.values())
            except Exception:
                existing_items = []

        existing_urls: set[str] = {
            item.get("url", "") for item in existing_items if isinstance(item, dict)
        }

        for resource in _LOVELACE_RESOURCES:
            url = resource["url"]
            if url in existing_urls:
                _LOGGER.debug("[culiplan] Lovelace resource already registered: %s", url)
                continue
            try:
                await resource_collection.async_create_item(
                    {"url": url, "res_type": resource["res_type"]}
                )
                _LOGGER.info("[culiplan] Registered Lovelace resource: %s", url)
            except Exception as err:
                _LOGGER.warning(
                    "[culiplan] Could not register Lovelace resource %s: %s", url, err
                )

    except Exception as err:
        # Non-fatal: if resource registration fails the integration still works.
        # The manual fallback in lovelace/README.md covers this case.
        _LOGGER.warning(
            "[culiplan] Lovelace resource auto-registration failed (non-fatal): %s. "
            "Use the manual steps in lovelace/README.md instead.",
            err,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flavorplan from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    await session.async_ensure_token_valid()

    client = FlavorplanApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        access_token=session.token["access_token"],
    )

    coordinator = FlavorplanCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )

    _register_intents(hass, entry)
    async_register_services(hass)
    async_register_cooking_services(hass)
    await _async_register_lovelace_resources(hass)
    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(lambda: async_unregister_services(hass))
    entry.async_on_unload(lambda: async_unregister_cooking_services(hass))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        async_unregister_services(hass)
    return unload_ok


# ─── Assist intent registration ──────────────────────────────────────────────


def _register_intents(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Flavorplan Assist intents for the HA language."""
    lang = hass.config.language.split("-")[0].lower()
    if lang not in ("en", "nl", "de", "fr", "es"):
        lang = "en"

    intents_file = _INTENTS_DIR / f"{lang}.yaml"
    if not intents_file.exists():
        intents_file = _INTENTS_DIR / "en.yaml"

    try:
        data = yaml.safe_load(intents_file.read_text(encoding="utf-8"))
    except Exception as err:
        _LOGGER.error("Failed to load Flavorplan intents YAML: %s", err)
        return

    intents_data = data.get("intents", {})
    for intent_name in intents_data:
        # Cooking-mode intents are handled by local HA service calls.
        if intent_name in _COOKING_INTENT_TO_SERVICE:
            handler = _make_cooking_intent_handler(intent_name, entry)
        else:
            handler = _make_intent_handler(intent_name, entry)
        # async_register is idempotent (overwrites on reload).
        intent.async_register(hass, handler)

    _LOGGER.debug(
        "Registered %d Flavorplan Assist intents (lang=%s)",
        len(intents_data),
        lang,
    )


def _make_intent_handler(intent_name: str, entry: ConfigEntry) -> intent.IntentHandler:
    """Return an IntentHandler for a single Flavorplan intent.

    We create a fresh class per intent so that `intent_type` is a proper
    class-level attribute (HA asserts it via getattr and stores by type).
    """

    class _Handler(intent.IntentHandler):
        intent_type = intent_name

        async def async_handle(
            self, intent_obj: intent.Intent
        ) -> intent.IntentResponse:
            data = intent_obj.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not data:
                return _speech(intent_obj, "Flavorplan is not connected.")
            client: FlavorplanApiClient = data["client"]
            tool = _INTENT_TO_TOOL.get(intent_name)
            if not tool:
                return _speech(intent_obj, "That intent is not configured.")
            slots: dict[str, Any] = {
                k: v.get("value") for k, v in intent_obj.slots.items()
            }
            try:
                result = await client.async_call_voice_tool(tool, slots)
                text = result.get("speakable") or result.get("message") or "Done."
            except Exception as err:
                _LOGGER.error("Voice tool '%s' failed: %s", tool, err)
                text = "Sorry, Flavorplan couldn't complete that request."
            return _speech(intent_obj, text)

    return _Handler()


def _make_cooking_intent_handler(
    intent_name: str, entry: ConfigEntry
) -> intent.IntentHandler:
    """
    Return an IntentHandler for a cooking-mode intent that delegates to
    a local HA service call rather than the remote voice-tool endpoint.

    This keeps the session-management logic in cooking_services.py (single source
    of truth) and avoids duplicating HTTP calls from the intent layer.
    """
    service_name = _COOKING_INTENT_TO_SERVICE[intent_name]

    class _CookingHandler(intent.IntentHandler):
        intent_type = intent_name

        async def async_handle(
            self, intent_obj: intent.Intent
        ) -> intent.IntentResponse:
            slots: dict[str, Any] = {
                k: v.get("value") for k, v in intent_obj.slots.items()
            }
            # Map intent slot names to service field names
            service_data: dict[str, Any] = {}
            if "label" in slots and slots["label"]:
                service_data["label"] = slots["label"]
            if "label_or_id" in slots and slots["label_or_id"]:
                service_data["label_or_id"] = slots["label_or_id"]
            if "duration_sec" in slots and slots["duration_sec"]:
                try:
                    service_data["duration_sec"] = int(slots["duration_sec"])
                except (TypeError, ValueError):
                    pass

            try:
                await intent_obj.hass.services.async_call(
                    DOMAIN,
                    service_name,
                    service_data,
                    blocking=True,
                )
                # Map service to a friendly spoken response.
                if service_name == "advance_cooking_step":
                    text = "Moving to the next cooking step."
                elif service_name == "set_recipe_timer":
                    label = service_data.get("label", "")
                    text = f"Starting the {label} timer."
                elif service_name == "cancel_recipe_timer":
                    label = service_data.get("label_or_id", service_data.get("label", ""))
                    text = f"Cancelled the {label} timer."
                else:
                    text = "Done."
            except Exception as err:
                _LOGGER.error(
                    "Cooking intent '%s' (service %s) failed: %s",
                    intent_name,
                    service_name,
                    err,
                )
                text = f"Sorry, Flavorplan couldn't complete that cooking action."
            return _speech(intent_obj, text)

    return _CookingHandler()


def _speech(intent_obj: intent.Intent, text: str) -> intent.IntentResponse:
    response = intent_obj.create_response()
    response.async_set_speech(text)
    return response
