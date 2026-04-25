"""Conversation (Assist) integration — registers Flavorplan voice intents."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .api import FlavorplanApiClient
from .const import DOMAIN

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
    """Register Flavorplan intents with the HA conversation agent."""
    lang = hass.config.language.split("-")[0].lower()
    if lang not in ("en", "nl", "de", "fr", "es"):
        lang = "en"

    intents_file = _INTENTS_DIR / f"{lang}.yaml"
    if not intents_file.exists():
        _LOGGER.warning(
            "No intents file for language '%s', falling back to 'en'", lang
        )
        intents_file = _INTENTS_DIR / "en.yaml"

    try:
        intents_data = yaml.safe_load(intents_file.read_text(encoding="utf-8"))
    except Exception as err:
        _LOGGER.error("Failed to load intents YAML: %s", err)
        return False

    for intent_name in intents_data.get("intents", {}):
        intent.async_register(
            hass,
            FlavorplanIntentHandler(hass, intent_name, entry),
        )

    _LOGGER.debug(
        "Registered %d Flavorplan Assist intents for language '%s'",
        len(intents_data.get("intents", {})),
        lang,
    )
    return True


class FlavorplanIntentHandler(intent.IntentHandler):
    """Handle a single Flavorplan Assist intent by proxying to the backend."""

    intent_type: str
    slot_schema = None  # Accept any slots; backend validates.

    def __init__(
        self,
        hass: HomeAssistant,
        intent_name: str,
        entry: ConfigEntry,
    ) -> None:
        self.intent_type = intent_name
        self._entry = entry
        self._hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Forward the intent to the Flavorplan voice API."""
        tool_name = _INTENT_TO_TOOL.get(self.intent_type)
        if not tool_name:
            _LOGGER.warning("No tool mapping for intent %s", self.intent_type)
            return intent_obj.create_response()

        data = hass_data = self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if not hass_data:
            return _error_response(intent_obj, "Flavorplan is not connected.")

        client: FlavorplanApiClient = hass_data["client"]
        slots: dict[str, Any] = {
            k: v.get("value") for k, v in intent_obj.slots.items()
        }

        try:
            result = await client.async_call_voice_tool(tool_name, slots)
            text = result.get("speakable") or result.get("message") or "Done."
        except Exception as err:
            _LOGGER.error("Voice tool '%s' failed: %s", tool_name, err)
            text = "Sorry, Flavorplan couldn't complete that request."

        response = intent_obj.create_response()
        response.async_set_speech(text)
        return response


def _error_response(intent_obj: intent.Intent, message: str) -> intent.IntentResponse:
    response = intent_obj.create_response()
    response.async_set_speech(message)
    return response
