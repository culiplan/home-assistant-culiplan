"""Tests for CuliplanApiClient — HTTP plumbing, response normalisation,
401 → reauth, 403 → typed PremiumRequiredError mapping.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from custom_components.culiplan.ai.types import PremiumRequiredError
from custom_components.culiplan.api import CuliplanApiClient


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_resp(
    status: int = 200,
    json_payload: Any = None,
    raise_for_status: bool = False,
    text: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.ok = 200 <= status < 300
    resp.json = AsyncMock(return_value=json_payload)
    resp.text = AsyncMock(return_value=text)
    resp.raise_for_status = MagicMock(
        side_effect=Exception(f"HTTP {status}") if raise_for_status else None
    )
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_client(method: str, resp: MagicMock) -> CuliplanApiClient:
    session = MagicMock(spec=ClientSession)
    setattr(session, method, MagicMock(return_value=resp))
    return CuliplanApiClient(session=session, access_token="tok")


# ─── 401 → ConfigEntryAuthFailed ─────────────────────────────────────────────


class TestAuthFailure:
    @pytest.mark.asyncio
    async def test_401_get_raises_auth_failed(self):
        client = _make_client("get", _make_resp(status=401))
        with pytest.raises(ConfigEntryAuthFailed):
            await client.async_get_user()

    @pytest.mark.asyncio
    async def test_401_post_raises_auth_failed(self):
        client = _make_client("post", _make_resp(status=401))
        with pytest.raises(ConfigEntryAuthFailed):
            await client.async_post("/api/x", {})

    @pytest.mark.asyncio
    async def test_401_patch_raises_auth_failed(self):
        client = _make_client("patch", _make_resp(status=401))
        with pytest.raises(ConfigEntryAuthFailed):
            await client.async_update_shopping_item("list1", "item1", True)

    @pytest.mark.asyncio
    async def test_401_delete_raises_auth_failed(self):
        client = _make_client("delete", _make_resp(status=401))
        with pytest.raises(ConfigEntryAuthFailed):
            await client.async_remove_shopping_item("list1", "item1")


# ─── 403 typed error mapping (task-1416) ─────────────────────────────────────


class TestPremiumRequired:
    @pytest.mark.asyncio
    async def test_403_premium_required_raises_typed(self):
        resp = _make_resp(
            status=403,
            json_payload={
                "error": "premium_required",
                "feature": "ai.suggestion",
                "upgradeUrl": "https://culiplan.com/premium?source=ha",
            },
        )
        client = _make_client("post", resp)
        with pytest.raises(PremiumRequiredError) as excinfo:
            await client.async_post("/api/x", {})
        assert excinfo.value.feature == "ai.suggestion"
        assert "culiplan.com" in excinfo.value.upgrade_url

    @pytest.mark.asyncio
    async def test_403_non_premium_raises_homeassistant_error(self):
        resp = _make_resp(
            status=403,
            json_payload={"error": "forbidden_scope"},
        )
        client = _make_client("post", resp)
        with pytest.raises(HomeAssistantError):
            await client.async_post("/api/x", {})

    @pytest.mark.asyncio
    async def test_403_unparseable_body_raises_homeassistant_error(self):
        resp = _make_resp(status=403, json_payload=None)
        resp.json = AsyncMock(side_effect=Exception("invalid json"))
        client = _make_client("post", resp)
        with pytest.raises(HomeAssistantError):
            await client.async_post("/api/x", {})


# ─── Response normalisation ──────────────────────────────────────────────────


class TestMealPlansNormalisation:
    @pytest.mark.asyncio
    async def test_bare_list_returned_as_is(self):
        bare = [{"id": "p1", "name": "P", "slots": []}]
        client = _make_client("get", _make_resp(json_payload=bare))
        result = await client.async_get_meal_plans()
        assert result == bare

    @pytest.mark.asyncio
    async def test_grouped_dict_flattens_into_single_plan(self):
        grouped = {
            "2026-06-07": {
                "dinner": [
                    {
                        "id": "e1",
                        "date": "2026-06-07T18:00:00Z",
                        "recipe": {"title": "Pasta"},
                        "recipeId": "r1",
                        "servings": 2,
                    }
                ],
                "lunch": [
                    {
                        "id": "e2",
                        "date": "2026-06-07T12:00:00Z",
                        "title": "Sandwich",
                        "mealSlot": "lunch",
                    }
                ],
            }
        }
        client = _make_client("get", _make_resp(json_payload=grouped))
        result = await client.async_get_meal_plans()
        assert len(result) == 1
        assert result[0]["id"] == "current"
        assert len(result[0]["slots"]) == 2

    @pytest.mark.asyncio
    async def test_unexpected_type_returns_empty(self):
        client = _make_client("get", _make_resp(json_payload="garbage"))
        assert await client.async_get_meal_plans() == []

    @pytest.mark.asyncio
    async def test_grouped_dict_skips_malformed_entries(self):
        grouped = {
            "2026-06-07": {
                "dinner": ["not-a-dict", {"id": "e1", "date": "2026-06-07T18:00:00Z"}],
                "lunch": "not-a-list",
            },
            "2026-06-08": "not-a-dict",
        }
        client = _make_client("get", _make_resp(json_payload=grouped))
        result = await client.async_get_meal_plans()
        assert len(result[0]["slots"]) == 1


class TestShoppingListNormalisation:
    @pytest.mark.asyncio
    async def test_wraps_items_into_single_list(self):
        items = [{"id": "i1", "name": "Pasta", "completed": False}]
        client = _make_client("get", _make_resp(json_payload=items))
        result = await client.async_get_shopping_lists()
        assert len(result) == 1
        assert result[0]["id"] == "default"
        assert result[0]["items"] == items


class TestPantryNormalisation:
    @pytest.mark.asyncio
    async def test_unwraps_data_key(self):
        items = [{"id": "p1", "name": "Milk"}]
        client = _make_client("get", _make_resp(json_payload={"data": items}))
        result = await client.async_get_pantry_items()
        assert result == items

    @pytest.mark.asyncio
    async def test_bare_list_passthrough(self):
        items = [{"id": "p1", "name": "Milk"}]
        client = _make_client("get", _make_resp(json_payload=items))
        result = await client.async_get_pantry_items()
        assert result == items

    @pytest.mark.asyncio
    async def test_unexpected_type_returns_empty(self):
        client = _make_client("get", _make_resp(json_payload="garbage"))
        assert await client.async_get_pantry_items() == []


# ─── Mutation helpers ────────────────────────────────────────────────────────


class TestMutations:
    @pytest.mark.asyncio
    async def test_add_shopping_item_unwraps_array_response(self):
        resp = _make_resp(json_payload=[{"id": "i1", "name": "Bread"}])
        client = _make_client("post", resp)
        result = await client.async_add_shopping_item("list1", "Bread")
        assert result["name"] == "Bread"

    @pytest.mark.asyncio
    async def test_add_shopping_item_includes_quantity_when_set(self):
        resp = _make_resp(json_payload={"id": "i1", "name": "Eggs", "quantity": "12"})
        client = _make_client("post", resp)
        await client.async_add_shopping_item("list1", "Eggs", quantity="12")
        # The .post call payload includes quantity inside items[0].
        post_args = client._session.post.call_args
        assert post_args.kwargs["json"]["items"][0]["quantity"] == "12"

    @pytest.mark.asyncio
    async def test_update_shopping_item_patches_checked(self):
        resp = _make_resp(json_payload={"id": "i1", "checked": True})
        client = _make_client("patch", resp)
        result = await client.async_update_shopping_item("list1", "i1", True)
        assert result["checked"] is True

    @pytest.mark.asyncio
    async def test_remove_shopping_item_deletes(self):
        resp = _make_resp(status=204, json_payload=None)
        client = _make_client("delete", resp)
        # Should not raise
        await client.async_remove_shopping_item("list1", "i1")

    @pytest.mark.asyncio
    async def test_call_voice_tool_posts_with_payload(self):
        resp = _make_resp(json_payload={"speakable": "OK"})
        client = _make_client("post", resp)
        result = await client.async_call_voice_tool(
            "suggest_meal", {"mealSlot": "dinner"}
        )
        assert result["speakable"] == "OK"
