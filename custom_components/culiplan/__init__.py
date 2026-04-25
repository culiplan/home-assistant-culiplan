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

from .api import FlavorplanApiClient
from .const import DOMAIN, PLATFORMS
from .coordinator import FlavorplanCoordinator

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
    entry.async_on_unload(coordinator.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
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

    for intent_name in data.get("intents", {}):
        handler = _make_intent_handler(intent_name, entry)
        # async_register is idempotent (overwrites on reload).
        intent.async_register(hass, handler)

    _LOGGER.debug(
        "Registered %d Flavorplan Assist intents (lang=%s)",
        len(data.get("intents", {})),
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


def _speech(intent_obj: intent.Intent, text: str) -> intent.IntentResponse:
    response = intent_obj.create_response()
    response.async_set_speech(text)
    return response
