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
