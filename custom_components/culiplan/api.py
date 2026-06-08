"""OAuth-aware async HTTP client for the Culiplan API."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiohttp import ClientSession

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .ai.types import PremiumRequiredError
from .const import BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CuliplanApiClient:
    """Client for the Culiplan REST API."""

    def __init__(
        self,
        session: ClientSession,
        access_token: str,
        *,
        token_provider: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        # When supplied, an async callable that ensures the OAuth token is
        # valid (refreshing if near expiry) and returns the current access
        # token. Every request resolves the token through this so long-lived
        # entries don't 401 once the captured token ages past its TTL — which
        # otherwise forces a full reauth on the next event-driven REST call or
        # user service invocation.
        self._token_provider = token_provider

    async def async_get_access_token(self) -> str:
        """Return a currently-valid access token, refreshing if needed."""
        if self._token_provider is not None:
            self._access_token = await self._token_provider()
        return self._access_token

    async def _async_headers(self) -> dict[str, str]:
        """Build auth headers with a freshly-validated token."""
        await self.async_get_access_token()
        return self._headers()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ─── Read ────────────────────────────────────────────────────────────────

    async def async_get_user(self) -> dict[str, Any]:
        return cast(dict[str, Any], await self._get("/api/users/me"))

    async def async_get_meal_plans(self) -> list[dict[str, Any]]:
        """Fetch meal plans and normalise to a single-plan list shape.

        The backend returns a date-grouped structure:
            { "<YYYY-MM-DD>": { "<slot>": [ <entry>, ... ], ... }, ... }

        A Culiplan user has one continuous meal-plan timeline, not one plan
        per date. We expose it as exactly one plan with all entries flattened
        into a single ``slots`` list. This produces one ``calendar.culiplan``
        entity with N events, regardless of how many dates the backend
        returns.

            [
              {
                "id":    "current",
                "name":  "Meal Plan",
                "slots": [
                  { "id": <entry.id>, "date": "<YYYY-MM-DDT…>",
                    "title": <recipe title or slot>, "course": <mealSlot>,
                    "recipeId": <entry.recipeId>, "servings": null },
                  ...
                ],
              }
            ]

        The plan is always emitted (even with an empty ``slots`` list) so the
        calendar entity identity stays stable across refreshes.

        A bare list-of-dicts response (legacy / test doubles) is returned
        as-is so unit tests injecting the old shape keep working.
        """
        raw = await self._get("/api/meal-plans")

        # Legacy / test-double path: bare list already in the expected shape.
        if isinstance(raw, list):
            return cast(list[dict[str, Any]], raw)

        if not isinstance(raw, dict):
            _LOGGER.warning(
                "async_get_meal_plans: unexpected response type %s", type(raw)
            )
            return []

        # Grouped dict path: { date_str: { slot_name: [entry, ...] } }
        slots: list[dict[str, Any]] = []
        for date_str, slots_by_name in raw.items():
            if not isinstance(slots_by_name, dict):
                continue
            for slot_name, entries in slots_by_name.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    # Backend stores the date as a full ISO timestamp on the
                    # entry; fall back to the dict-key date if absent.
                    entry_date: Any = entry.get("date") or f"{date_str}T12:00:00Z"
                    if not isinstance(entry_date, str):
                        entry_date = str(entry_date)
                    recipe = entry.get("recipe") or {}
                    title: str = recipe.get("title") or entry.get("title") or slot_name
                    slots.append(
                        {
                            "id": entry.get("id", f"{date_str}-{slot_name}"),
                            "date": entry_date,
                            "title": title,
                            "course": entry.get("mealSlot", slot_name),
                            "recipeId": entry.get("recipeId"),
                            "servings": entry.get("servings"),
                        }
                    )

        return [
            {
                "id": "current",
                "name": "Meal Plan",
                "slots": slots,
            }
        ]

    async def async_get_shopping_lists(self) -> list[dict[str, Any]]:
        """
        Return the user's shopping list as a single-element list, matching the
        HA todo entity model.

        The Culiplan backend has one shopping list per user (or one
        household-shared list); the REST endpoint returns a flat array of
        ``ShoppingListItem`` records. We wrap that into a single synthetic
        list with id ``"default"`` so coordinator/todo can keep using a
        ``list[dict]`` shape without leaking the impedance mismatch.
        """
        items = await self._get("/api/shopping-list")
        return [{"id": "default", "name": "Shopping List", "items": items}]

    async def async_get_pantry_items(self) -> list[dict[str, Any]]:
        """Return the user's pantry stock as a flat list.

        Backend endpoint is paginated (``GET /api/pantry/stock``); we ask for
        the maximum page size (100) and unwrap ``data``. For typical home
        pantries 100 items is well above the actual count; sensors that need
        finer slicing (e.g. expiring-within-N-days) can still filter the
        returned list client-side.
        """
        response = await self._get("/api/pantry/stock?limit=100")
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return cast(list[dict[str, Any]], response["data"])
        return (
            cast(list[dict[str, Any]], response) if isinstance(response, list) else []
        )

    async def async_get_energy_today(self) -> dict[str, Any]:
        """Fetch today's estimated kWh for planned recipes (task-1399)."""
        return cast(dict[str, Any], await self._get("/api/ha/energy/today"))

    # ─── Shopping list mutations ─────────────────────────────────────────────
    # The backend exposes a flat, single-list API (POST /api/shopping-list
    # accepts {items: [...]}, PATCH/DELETE target /api/shopping-list/:id).
    # ``list_id`` is preserved in the signatures for callers in todo.py but
    # is ignored — see async_get_shopping_lists for context.

    async def async_add_shopping_item(
        self, list_id: str, name: str, quantity: str | None = None
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"name": name}
        if quantity:
            item["quantity"] = quantity
        created = await self._post("/api/shopping-list", {"items": [item]})
        if isinstance(created, list) and created:
            return cast(dict[str, Any], created[0])
        return cast(dict[str, Any], created)

    async def async_update_shopping_item(
        self, list_id: str, item_id: str, completed: bool
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._patch(
                f"/api/shopping-list/{item_id}",
                {"checked": completed},
            ),
        )

    async def async_remove_shopping_item(self, list_id: str, item_id: str) -> None:
        await self._delete(f"/api/shopping-list/{item_id}")

    async def async_call_voice_tool(
        self, tool_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._post(
                "/api/voice/ha-assist", {"tool": tool_name, "params": params}
            ),
        )

    # ─── Generic helpers (used by AI dispatcher service + Phase 2 services) ──

    async def async_get(self, path: str) -> Any:
        """Generic GET — used by Phase 2 service layer (tasks 1378, 1380)."""
        return await self._get(path)

    async def async_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Generic POST — used by AI dispatcher (1387) and Phase 2 services (1376, 1379)."""
        return cast(dict[str, Any], await self._post(path, payload))

    # ─── HTTP helpers ────────────────────────────────────────────────────────

    async def _get(self, path: str) -> Any:
        async with self._session.get(
            f"{BASE_URL}{path}", headers=await self._async_headers()
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        async with self._session.post(
            f"{BASE_URL}{path}", headers=await self._async_headers(), json=payload
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
                    translation_domain=DOMAIN,
                    translation_key="api_forbidden",
                    translation_placeholders={"path": path, "body": str(body)},
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
            f"{BASE_URL}{path}", headers=await self._async_headers(), json=payload
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
            f"{BASE_URL}{path}", headers=await self._async_headers(), json=payload
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()
            return await resp.json()

    async def _delete(self, path: str) -> None:
        async with self._session.delete(
            f"{BASE_URL}{path}", headers=await self._async_headers()
        ) as resp:
            self._raise_for_status(resp.status, path)
            resp.raise_for_status()

    @staticmethod
    def _raise_for_status(status: int, path: str) -> None:
        """Convert 401 to ConfigEntryAuthFailed so HA triggers re-auth flow."""
        if status == 401:
            raise ConfigEntryAuthFailed(
                f"Culiplan token expired or revoked (401 on {path})"
            )
