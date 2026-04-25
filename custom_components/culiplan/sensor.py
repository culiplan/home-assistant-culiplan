"""Sensor entities placeholder — implemented in task-1368."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities — full implementation in task-1368."""
    # Entities are added once coordinator and schema are finalised in task-1368.
    # Tier 1 sensor trio: meals_today, shopping_items_count, expiring_pantry_items.
