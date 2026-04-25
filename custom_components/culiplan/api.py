"""OAuth-aware async HTTP client for the Flavorplan API."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)


class FlavorplanApiClient:
    """Client for the Flavorplan REST API."""

    def __init__(self, session: ClientSession, access_token: str) -> None:
        self._session = session
        self._access_token = access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def async_get_user(self) -> dict[str, Any]:
        """Fetch the authenticated user profile."""
        return await self._get("/api/users/me")

    async def async_get_meal_plans(self) -> list[dict[str, Any]]:
        """Fetch active meal plans."""
        return await self._get("/api/meal-plans")

    async def async_get_shopping_lists(self) -> list[dict[str, Any]]:
        """Fetch shopping lists."""
        return await self._get("/api/shopping-lists")

    async def async_add_shopping_item(
        self, list_id: str, name: str, quantity: str | None = None
    ) -> dict[str, Any]:
        """Add an item to a shopping list."""
        payload: dict[str, Any] = {"name": name}
        if quantity:
            payload["quantity"] = quantity
        return await self._post(f"/api/shopping-lists/{list_id}/items", payload)

    async def _get(self, path: str) -> Any:
        async with self._session.get(
            f"{BASE_URL}{path}", headers=self._headers()
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        async with self._session.post(
            f"{BASE_URL}{path}", headers=self._headers(), json=payload
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
