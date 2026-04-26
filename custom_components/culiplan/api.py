"""OAuth-aware async HTTP client for the Flavorplan API."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .ai.types import PremiumRequiredError
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

    # ─── Read ────────────────────────────────────────────────────────────────

    async def async_get_user(self) -> dict[str, Any]:
        return await self._get("/api/users/me")

    async def async_get_meal_plans(self) -> list[dict[str, Any]]:
        return await self._get("/api/meal-plans")

    async def async_get_shopping_lists(self) -> list[dict[str, Any]]:
        return await self._get("/api/shopping-lists")

    async def async_get_pantry_items(self) -> list[dict[str, Any]]:
        return await self._get("/api/pantry")

    # ─── Shopping list mutations ─────────────────────────────────────────────

    async def async_add_shopping_item(
        self, list_id: str, name: str, quantity: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if quantity:
            payload["quantity"] = quantity
        return await self._post(f"/api/shopping-lists/{list_id}/items", payload)

    async def async_update_shopping_item(
        self, list_id: str, item_id: str, completed: bool
    ) -> dict[str, Any]:
        return await self._patch(
            f"/api/shopping-lists/{list_id}/items/{item_id}",
            {"completed": completed},
        )

    async def async_remove_shopping_item(self, list_id: str, item_id: str) -> None:
        await self._delete(f"/api/shopping-lists/{list_id}/items/{item_id}")

    async def async_call_voice_tool(
        self, tool_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._post(
            "/api/voice/ha-assist", {"tool": tool_name, "params": params}
        )

    # ─── Generic helpers (used by AI dispatcher service + Phase 2 services) ──

    async def async_get(self, path: str) -> Any:
        """Generic GET — used by Phase 2 service layer (tasks 1378, 1380)."""
        return await self._get(path)

    async def async_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Generic POST — used by AI dispatcher (1387) and Phase 2 services (1376, 1379)."""
        return await self._post(path, payload)

    # ─── HTTP helpers ────────────────────────────────────────────────────────

    async def _get(self, path: str) -> Any:
        async with self._session.get(
            f"{BASE_URL}{path}", headers=self._headers()
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        async with self._session.post(
            f"{BASE_URL}{path}", headers=self._headers(), json=payload
        ) as resp:
            self._raise_for_status(resp.status, path)
            if resp.status == 403:
                # Read the body before raise_for_status() so we can inspect
                # the structured {error, feature, upgradeUrl} payload and raise
                # a typed PremiumRequiredError (task-1416).
                try:
                    body: dict[str, Any] = await resp.json()
                except Exception:
                    body = {}
                if body.get("error") == "premium_required":
                    raise PremiumRequiredError(
                        feature=body.get("feature", "unknown"),
                        upgrade_url=body.get(
                            "upgradeUrl",
                            "https://culiplan.com/premium?source=ha",
                        ),
                    )
                # Non-premium 403 (e.g. forbidden scope) — raise as generic HA error
                raise HomeAssistantError(
                    f"Flavorplan API returned 403 on {path}: {body}"
                )
            resp.raise_for_status()
            return await resp.json()

    async def _post_raw(self, path: str, payload: dict[str, Any]) -> Any:
        """POST that preserves error response body in the raised exception message.

        Used by Phase 2 services so structured error bodies (e.g. 403 premium_required,
        404 PANTRY_ITEM_NOT_FOUND) can be parsed by the service layer.
        """
        import json as _json
        async with self._session.post(
            f"{BASE_URL}{path}", headers=self._headers(), json=payload
        ) as resp:
            self._raise_for_status(resp.status, path)
            if not resp.ok:
                try:
                    body = await resp.json()
                    body_str = _json.dumps(body)
                except Exception:
                    body_str = await resp.text()
                raise Exception(f"{resp.status} {body_str}")
            return await resp.json()

    async def _patch(self, path: str, payload: dict[str, Any]) -> Any:
        async with self._session.patch(
            f"{BASE_URL}{path}", headers=self._headers(), json=payload
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()
            return await resp.json()

    async def _delete(self, path: str) -> None:
        async with self._session.delete(
            f"{BASE_URL}{path}", headers=self._headers()
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()

    @staticmethod
    def _raise_for_status(status: int, path: str) -> None:
        """Convert 401 to ConfigEntryAuthFailed so HA triggers re-auth flow."""
        if status == 401:
            raise ConfigEntryAuthFailed(
                f"Flavorplan token expired or revoked (401 on {path})"
            )
