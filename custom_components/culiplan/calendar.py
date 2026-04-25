"""Calendar entity — one per Flavorplan meal plan (task-1366)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlavorplanCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flavorplan calendar entities."""
    coordinator: FlavorplanCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    meal_plans = (coordinator.data or {}).get("meal_plans", [])
    async_add_entities(
        FlavorplanCalendar(coordinator, plan) for plan in meal_plans
    )


class FlavorplanCalendar(CoordinatorEntity[FlavorplanCoordinator], CalendarEntity):
    """Calendar entity for a single Flavorplan meal plan."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FlavorplanCoordinator,
        plan: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._plan = plan
        self._plan_id: str = plan["id"]
        self._attr_unique_id = f"{DOMAIN}_calendar_{self._plan_id}"
        self._attr_name = plan.get("name", "Meal Plan")

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current/next event."""
        events = self._build_events()
        now = datetime.now(tz=timezone.utc)
        upcoming = [e for e in events if e.end > now]
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return events within the requested window."""
        return [
            e
            for e in self._build_events()
            if e.start < end_date and e.end > start_date
        ]

    def _build_events(self) -> list[CalendarEvent]:
        """Convert meal plan slots into CalendarEvent objects."""
        events: list[CalendarEvent] = []
        plans = (self.coordinator.data or {}).get("meal_plans", [])
        for plan in plans:
            if plan["id"] != self._plan_id:
                continue
            for slot in plan.get("slots", []):
                try:
                    start = _parse_dt(slot["date"])
                    end = start + timedelta(hours=1)
                    events.append(
                        CalendarEvent(
                            start=start,
                            end=end,
                            summary=slot.get("title", "Meal"),
                            description=None,
                            uid=slot.get("id"),
                            extra_state_attributes={
                                "recipe_id": slot.get("recipeId"),
                                "servings": slot.get("servings"),
                                "course": slot.get("course"),
                            },
                        )
                    )
                except (KeyError, ValueError) as err:
                    _LOGGER.debug("Skipping malformed meal slot: %s", err)
        return sorted(events, key=lambda e: e.start)

    def _handle_coordinator_update(self) -> None:
        """Refresh plan reference from coordinator data."""
        plans = (self.coordinator.data or {}).get("meal_plans", [])
        for plan in plans:
            if plan["id"] == self._plan_id:
                self._plan = plan
                break
        super()._handle_coordinator_update()


def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 date or datetime string into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Treat bare date strings as midnight UTC.
        return datetime.combine(date.fromisoformat(value), datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
