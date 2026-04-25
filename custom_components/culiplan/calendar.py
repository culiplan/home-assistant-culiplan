"""Calendar entity placeholder — implemented in task-1366."""

from __future__ import annotations

from homeassistant.components.calendar import CalendarEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up calendar entities — full implementation in task-1366."""
    # Entities are added once coordinator and schema are finalised in task-1366.
