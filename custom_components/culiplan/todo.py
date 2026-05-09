"""Todo entity — one per Flavorplan shopping list (task-1367)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlavorplanCoordinator
from .helpers import _build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flavorplan todo (shopping list) entities."""
    coordinator: FlavorplanCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    shopping_lists = (coordinator.data or {}).get("shopping_lists", [])
    async_add_entities(
        FlavorplanShoppingList(coordinator, sl, entry) for sl in shopping_lists
    )


class FlavorplanShoppingList(CoordinatorEntity[FlavorplanCoordinator], TodoListEntity):
    """Todo entity for a Flavorplan shopping list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: FlavorplanCoordinator,
        shopping_list: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._list_id: str = shopping_list["id"]
        self._attr_unique_id = f"{DOMAIN}_todo_{self._list_id}"
        self._attr_name = shopping_list.get("name", "Shopping List")
        self._attr_device_info = _build_device_info(entry)

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the current items in this shopping list."""
        for sl in (self.coordinator.data or {}).get("shopping_lists", []):
            if sl["id"] == self._list_id:
                return [_to_todo_item(item) for item in sl.get("items", [])]
        return []

    # ─── Mutations ───────────────────────────────────────────────────────────

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item to the shopping list (HA → backend)."""
        await self.coordinator.client.async_add_shopping_item(
            self._list_id, name=item.summary or ""
        )
        # Optimistic state update so the UI is instant; Socket.IO event corrects later.
        await self.coordinator._refresh_shopping_lists()  # noqa: SLF001
        self.async_write_ha_state()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Check or uncheck an item (HA → backend)."""
        await self.coordinator.client.async_update_shopping_item(
            self._list_id,
            item_id=item.uid or "",
            completed=(item.status == TodoItemStatus.COMPLETED),
        )
        await self.coordinator._refresh_shopping_lists()  # noqa: SLF001
        self.async_write_ha_state()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove items from the shopping list (HA → backend)."""
        for uid in uids:
            await self.coordinator.client.async_remove_shopping_item(
                self._list_id, item_id=uid
            )
        await self.coordinator._refresh_shopping_lists()  # noqa: SLF001
        self.async_write_ha_state()


def _to_todo_item(item: dict[str, Any]) -> TodoItem:
    return TodoItem(
        uid=item.get("id", ""),
        summary=item.get("name", ""),
        status=(
            TodoItemStatus.COMPLETED if item.get("completed") else TodoItemStatus.NEEDS_ACTION
        ),
    )
