"""Tests for the Culiplan LLM API (v0.3.0 — Phase C of the Gold/Platinum roadmap).

Covers:
- CuliplanLLMAPI registers with the expected id / name and ships a non-empty
  tool list.
- `async_register_llm_api` is idempotent across calls (integration reload
  must not raise).
- `async_unregister_llm_api` removes the entry from the singleton dict.
- Each tool advertises a name + description + voluptuous parameter schema
  (LLM-side schema serialization depends on this).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.culiplan.llm_api import (
    LLM_API_ID,
    CuliplanLLMAPI,
    async_register_llm_api,
    async_unregister_llm_api,
    _build_tools,
)


def test_culiplan_llm_api_metadata() -> None:
    """API id + name match what HA Conversation Agent settings expect."""
    hass = MagicMock()
    api = CuliplanLLMAPI(hass)
    assert api.id == LLM_API_ID
    assert api.id == "culiplan-llm"
    assert api.name == "Culiplan"


def test_build_tools_non_empty_and_well_formed() -> None:
    """Each tool has a name, description, and voluptuous parameter schema."""
    tools = _build_tools()
    assert len(tools) >= 6, "Expected at least 6 LLM tools (v0.3.0 ship list)"
    names = {t.name for t in tools}
    assert {
        "get_meal_plan",
        "suggest_meal",
        "add_to_shopping_list",
        "find_recipes_by_ingredients",
        "get_recipe",
        "get_pantry_items",
    }.issubset(names)
    for tool in tools:
        assert tool.name, f"Tool missing name: {tool}"
        assert tool.description, f"Tool {tool.name} missing description"
        assert isinstance(tool.parameters, vol.Schema), (
            f"Tool {tool.name} parameters must be vol.Schema"
        )


def test_register_llm_api_is_idempotent() -> None:
    """Calling register twice must not raise (integration reload safety)."""
    hass = MagicMock()
    hass.data = {}
    async_register_llm_api(hass)
    # Second call: HA's async_register_api would raise; our wrapper must not.
    async_register_llm_api(hass)


def test_unregister_llm_api_pops_singleton_entry() -> None:
    """Unregister must remove the API id from hass.data['llm']."""
    hass = MagicMock()
    hass.data = {"llm": {LLM_API_ID: object(), "other-api": object()}}
    async_unregister_llm_api(hass)
    assert LLM_API_ID not in hass.data["llm"]
    assert "other-api" in hass.data["llm"]


def test_unregister_llm_api_safe_when_missing() -> None:
    """Unregister must be a no-op when nothing is registered yet."""
    hass = MagicMock()
    hass.data = {}
    # Must not raise.
    async_unregister_llm_api(hass)


@pytest.mark.asyncio
async def test_get_api_instance_returns_tools() -> None:
    """async_get_api_instance returns an APIInstance with the tool list."""
    import inspect

    from homeassistant.helpers import llm as ha_llm

    hass = MagicMock()
    api = CuliplanLLMAPI(hass)
    # LLMContext's fields drift across HA releases (e.g. `user_prompt` was
    # removed in HA 2026.x). Build kwargs from the live signature so this
    # test passes on every HA version in the CI matrix.
    ctx_params = inspect.signature(ha_llm.LLMContext).parameters
    ctx_kwargs = {
        "platform": "test",
        "context": None,
        "user_prompt": "test",
        "language": "en",
        "assistant": None,
        "device_id": None,
    }
    llm_context = ha_llm.LLMContext(
        **{k: v for k, v in ctx_kwargs.items() if k in ctx_params}
    )
    instance = await api.async_get_api_instance(llm_context)
    assert isinstance(instance, ha_llm.APIInstance)
    assert instance.tools, "APIInstance must carry the Culiplan tool list"
    assert instance.api_prompt, "APIInstance must include the prompt fragment"


# ─── Tool execution coverage (added v0.13.0) ─────────────────────────────────


from typing import Any
from unittest.mock import AsyncMock

from custom_components.culiplan.const import DOMAIN
from custom_components.culiplan.llm_api import (
    _filter_expiring,
    _find_entry_id,
    _get_client,
    _slot_in_range,
    _AddToShoppingListTool,
    _FindRecipesByIngredientsTool,
    _GetMealPlanTool,
    _GetPantryItemsTool,
    _GetRecipeTool,
    _SuggestMealTool,
)


def _hass_with_client(client: Any) -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"client": client}}}
    hass.services = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_call = AsyncMock()
    hass.bus = MagicMock()
    return hass


def _ti(args: dict) -> MagicMock:
    ti = MagicMock()
    ti.tool_args = args
    return ti


# _find_entry_id / _get_client


def test_find_entry_id_first_key():
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {}, "e2": {}}}
    assert _find_entry_id(hass) == "e1"


def test_find_entry_id_none_empty():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    assert _find_entry_id(hass) is None


def test_find_entry_id_none_no_domain():
    hass = MagicMock()
    hass.data = {}
    assert _find_entry_id(hass) is None


def test_get_client_no_entry_returns_none():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    assert _get_client(hass) is None


def test_get_client_no_client_returns_none():
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": {}}}
    assert _get_client(hass) is None


# _slot_in_range / _filter_expiring


@pytest.mark.parametrize(
    "date_value,start,end,expected",
    [
        ("2026-06-07T18:00:00Z", None, None, True),
        ("2026-06-07", "2026-06-01", "2026-06-08", True),
        ("2026-06-07", "2026-06-08", None, False),
        ("2026-06-07", None, "2026-06-06", False),
        (None, "2026-06-01", "2026-06-08", True),
    ],
)
def test_slot_in_range(date_value, start, end, expected):
    assert _slot_in_range(date_value, start, end) is expected


def test_filter_expiring_skips_non_dict():
    assert _filter_expiring(["not-a-dict"], 3) == []  # type: ignore[arg-type]


def test_filter_expiring_skips_no_expiry():
    assert _filter_expiring([{"id": "1"}], 3) == []


def test_filter_expiring_skips_bad_date():
    assert _filter_expiring([{"id": "1", "expiresAt": "garbage"}], 3) == []


def test_filter_expiring_includes_soon():
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
    assert len(_filter_expiring([{"id": "1", "expiresAt": soon}], 3)) == 1


# get_meal_plan tool


@pytest.mark.asyncio
async def test_meal_plan_tool_not_configured():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    result = await _GetMealPlanTool().async_call(hass, _ti({}), MagicMock())
    assert result["error"] == "not_configured"


@pytest.mark.asyncio
async def test_meal_plan_tool_all_slots():
    plans = [{"id": "p1", "slots": [{"date": "2026-06-07"}, {"date": "2026-06-08"}]}]
    client = MagicMock()
    client.async_get_meal_plans = AsyncMock(return_value=plans)
    result = await _GetMealPlanTool().async_call(_hass_with_client(client), _ti({}), MagicMock())
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_meal_plan_tool_filtered():
    plans = [{"id": "p1", "slots": [
        {"date": "2026-06-07"}, {"date": "2026-06-30"},
    ]}]
    client = MagicMock()
    client.async_get_meal_plans = AsyncMock(return_value=plans)
    result = await _GetMealPlanTool().async_call(
        _hass_with_client(client),
        _ti({"start_date": "2026-06-01", "end_date": "2026-06-08"}),
        MagicMock(),
    )
    assert result["count"] == 1


# suggest_meal tool


@pytest.mark.asyncio
async def test_suggest_tool_no_service():
    hass = MagicMock()
    hass.services.has_service.return_value = False
    result = await _SuggestMealTool().async_call(hass, _ti({}), MagicMock())
    assert result["error"] == "not_configured"


@pytest.mark.asyncio
async def test_suggest_tool_captures_event():
    hass = _hass_with_client(MagicMock())
    callbacks: list = []
    hass.bus.async_listen = MagicMock(side_effect=lambda name, cb: callbacks.append(cb) or MagicMock())

    async def _fire(*a, **k):
        ev = MagicMock()
        ev.data = {"result": "Pasta", "mode": "cloud"}
        callbacks[0](ev)

    hass.services.async_call = AsyncMock(side_effect=_fire)
    result = await _SuggestMealTool().async_call(hass, _ti({}), MagicMock())
    assert result["suggestion"] == "Pasta"


@pytest.mark.asyncio
async def test_suggest_tool_no_result():
    hass = _hass_with_client(MagicMock())
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    result = await _SuggestMealTool().async_call(hass, _ti({}), MagicMock())
    assert result["error"] == "no_result"


# add_to_shopping_list tool


@pytest.mark.asyncio
async def test_add_to_shopping_list():
    client = MagicMock()
    client.async_add_shopping_item = AsyncMock(return_value={"id": "i1"})
    result = await _AddToShoppingListTool().async_call(
        _hass_with_client(client), _ti({"name": "Milk", "quantity": "1L"}), MagicMock()
    )
    assert result["added"] is True


@pytest.mark.asyncio
async def test_add_to_shopping_list_no_client():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    result = await _AddToShoppingListTool().async_call(
        hass, _ti({"name": "Milk"}), MagicMock()
    )
    assert result["error"] == "not_configured"


# find_recipes_by_ingredients tool


@pytest.mark.asyncio
async def test_find_recipes_envelope():
    client = MagicMock()
    client.async_get = AsyncMock(return_value={"data": [{"id": "r1", "title": "Pasta"}]})
    result = await _FindRecipesByIngredientsTool().async_call(
        _hass_with_client(client), _ti({"ingredients": ["chicken"]}), MagicMock()
    )
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_find_recipes_bare_list():
    client = MagicMock()
    client.async_get = AsyncMock(return_value=[{"id": "r1", "title": "Soup"}])
    result = await _FindRecipesByIngredientsTool().async_call(
        _hass_with_client(client), _ti({"ingredients": ["onion"]}), MagicMock()
    )
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_find_recipes_unexpected_response():
    client = MagicMock()
    client.async_get = AsyncMock(return_value="garbage")
    result = await _FindRecipesByIngredientsTool().async_call(
        _hass_with_client(client), _ti({"ingredients": ["x"]}), MagicMock()
    )
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_find_recipes_not_configured():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    result = await _FindRecipesByIngredientsTool().async_call(
        hass, _ti({"ingredients": ["x"]}), MagicMock()
    )
    assert result["error"] == "not_configured"


# get_recipe tool


@pytest.mark.asyncio
async def test_get_recipe_trims_keys():
    recipe = {"id": "r1", "title": "Pasta", "images": ["bigfile.jpg"], "audit": {}}
    client = MagicMock()
    client.async_get = AsyncMock(return_value=recipe)
    result = await _GetRecipeTool().async_call(
        _hass_with_client(client), _ti({"recipe_id": "r1"}), MagicMock()
    )
    assert "images" not in result["recipe"]
    assert result["recipe"]["title"] == "Pasta"


@pytest.mark.asyncio
async def test_get_recipe_not_found():
    client = MagicMock()
    client.async_get = AsyncMock(return_value=None)
    result = await _GetRecipeTool().async_call(
        _hass_with_client(client), _ti({"recipe_id": "r1"}), MagicMock()
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_get_recipe_not_configured():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    result = await _GetRecipeTool().async_call(
        hass, _ti({"recipe_id": "r1"}), MagicMock()
    )
    assert result["error"] == "not_configured"


# get_pantry_items tool


@pytest.mark.asyncio
async def test_pantry_tool_all_items():
    client = MagicMock()
    client.async_get_pantry_items = AsyncMock(return_value=[
        {"id": "p1", "name": "Milk"}, {"id": "p2", "name": "Cheese"},
    ])
    result = await _GetPantryItemsTool().async_call(
        _hass_with_client(client), _ti({}), MagicMock()
    )
    assert result["count"] == 2
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_pantry_tool_filtered_by_expiry():
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
    far = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()
    client = MagicMock()
    client.async_get_pantry_items = AsyncMock(return_value=[
        {"id": "p1", "expiresAt": soon},
        {"id": "p2", "expiresAt": far},
    ])
    result = await _GetPantryItemsTool().async_call(
        _hass_with_client(client), _ti({"expiring_within_days": 3}), MagicMock()
    )
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_pantry_tool_caps_at_50():
    client = MagicMock()
    client.async_get_pantry_items = AsyncMock(return_value=[
        {"id": str(i)} for i in range(60)
    ])
    result = await _GetPantryItemsTool().async_call(
        _hass_with_client(client), _ti({}), MagicMock()
    )
    assert result["count"] == 50
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_pantry_tool_not_configured():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    result = await _GetPantryItemsTool().async_call(hass, _ti({}), MagicMock())
    assert result["error"] == "not_configured"


# Register failure non-fatal


def test_register_failure_non_fatal():
    from custom_components.culiplan import llm_api as mod

    hass = MagicMock()
    hass.data = {"llm": {}}
    original = mod.llm.async_register_api
    mod.llm.async_register_api = MagicMock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]
    try:
        async_register_llm_api(hass)  # must not raise
    finally:
        mod.llm.async_register_api = original  # type: ignore[attr-defined]
