"""
Culiplan LLM API — exposes Culiplan tools to any HA Conversation Agent
(OpenAI / Anthropic / Google / Ollama / HA Voice Preview) via
``homeassistant.helpers.llm.async_register_api()``.

Phase C of the Gold/Platinum roadmap (task / v0.3.0). Before this lands, a
user with HA's built-in Conversation Agent could only call Culiplan tools
if they ALSO configured Culiplan BYOK. After this lands, the user's
existing HA LLM agent calls Culiplan natively — no BYOK setup required
for users who only want the LLM tools surface.

Architecture notes:
- The Conversation Agent's LLM is used only for natural-language
  understanding and tool selection. Culiplan's own AI dispatcher still
  handles tools like ``suggest_meal`` (Premium gating, BYOK key routing,
  cloud / local model selection are all preserved).
- ``hass.data["llm"]`` is the singleton dict where registered APIs live
  (see ``homeassistant.helpers.llm._async_get_apis``). HA does NOT expose
  an ``async_unregister_api`` helper, so on integration unload we pop our
  entry directly from that dict to avoid orphaning a stale API instance
  across reloads.
- ``llm.async_register_api`` has been available since HA 2024.6; the
  integration's compatibility floor (2024.10) covers it. The import is
  wrapped in a try/except for forward compatibility — if HA ever moves
  the helper, the integration logs a graceful message and continues.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .api import CuliplanApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Public ID for the registered API. HA addresses APIs by this string in
# Conversation Agent settings ("Control Home Assistant" dropdown).
LLM_API_ID = f"{DOMAIN}-llm"

# Prompt fragment injected into the system prompt of any LLM that has
# selected this API. Kept short — HA already includes a generic preamble.
_PROMPT = (
    "You can answer questions about the user's meal plan, recipes, "
    "shopping list, and pantry. Use the Culiplan tools to fetch live "
    "data — never invent recipes or quantities. If a tool returns no "
    "results, say so honestly. Dates are ISO 8601 (YYYY-MM-DD)."
)


# ─── API class ───────────────────────────────────────────────────────────────


class CuliplanLLMAPI(llm.API):
    """Expose Culiplan tools to any HA Conversation Agent."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            id=LLM_API_ID,
            name="Culiplan",
        )

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return a per-call APIInstance with the Culiplan tools."""
        return llm.APIInstance(
            api=self,
            api_prompt=_PROMPT,
            llm_context=llm_context,
            tools=_build_tools(),
        )


def _build_tools() -> list[llm.Tool]:
    """Return the Culiplan tools available to this LLM call.

    Tools are stateless instances — they read the active config entry
    from ``hass.data[DOMAIN]`` at call time, so the same tool list works
    across reloads and multi-entry setups (first entry wins; matches the
    service-handler convention in services.py).
    """
    return [
        _GetMealPlanTool(),
        _SuggestMealTool(),
        _AddToShoppingListTool(),
        _FindRecipesByIngredientsTool(),
        _GetRecipeTool(),
        _GetPantryItemsTool(),
    ]


# ─── Shared helpers ──────────────────────────────────────────────────────────


def _find_entry_id(hass: HomeAssistant) -> str | None:
    """Return the first active Culiplan config entry ID.

    Mirrors services.py:_find_entry_id so tool calls and HA service calls
    pick the same entry on multi-entry installs (a single-entry guard is
    enforced at config-flow level today; this is a defensive fallback).
    """
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries), None)


def _get_client(hass: HomeAssistant) -> CuliplanApiClient | None:
    """Return the active CuliplanApiClient or ``None`` if not configured."""
    entry_id = _find_entry_id(hass)
    if not entry_id:
        return None
    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if not data:
        return None
    return cast(CuliplanApiClient, data.get("client"))


def _not_configured() -> JsonObjectType:
    """Standard "integration not yet configured" tool response."""
    return {
        "error": "not_configured",
        "message": (
            "Culiplan integration is not configured. "
            "Ask the user to set it up under Settings → Devices & Services."
        ),
    }


# ─── Tools ───────────────────────────────────────────────────────────────────


class _GetMealPlanTool(llm.Tool):
    """Fetch the user's current meal plan."""

    name = "get_meal_plan"
    description = (
        "Return the user's current meal plan. Optionally filter to a "
        "date range with start_date / end_date (ISO 8601, YYYY-MM-DD). "
        "Use this for questions like 'what's for dinner tonight?', "
        "'what am I cooking this week?', or 'show me Friday's meals'."
    )
    parameters = vol.Schema(
        {
            vol.Optional("start_date"): str,
            vol.Optional("end_date"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        client = _get_client(hass)
        if not client:
            return _not_configured()

        plans = await client.async_get_meal_plans()
        start = tool_input.tool_args.get("start_date")
        end = tool_input.tool_args.get("end_date")

        # When a date range is supplied, filter the flat slots list
        # client-side. The backend returns ALL slots; we trim to make the
        # LLM payload smaller and prevent reasoning over irrelevant days.
        if (start or end) and plans:
            plan = plans[0]
            slots = [
                s
                for s in plan.get("slots", [])
                if _slot_in_range(s.get("date"), start, end)
            ]
            plan = {**plan, "slots": slots}
            plans = [plan]

        # cast: JsonObjectType in HA's helpers/llm.py is strict about value
        # types; meal_plan is list[dict[str, Any]] which mypy doesn't widen
        # to JsonValueType automatically. The runtime payload is JSON-clean.
        return cast(
            JsonObjectType,
            {
                "meal_plan": plans,
                "count": sum(len(p.get("slots", [])) for p in plans),
            },
        )


class _SuggestMealTool(llm.Tool):
    """Generate a meal suggestion via the Culiplan AI dispatcher."""

    name = "suggest_meal"
    description = (
        "Suggest a meal for the user. Routes through Culiplan's own AI "
        "dispatcher so Premium gating and the user's configured AI mode "
        "(Cloud / BYOK / Local) are respected. Optional constraints "
        "string (e.g. 'vegetarian, under 30 minutes'), meal_slot "
        "('breakfast'/'lunch'/'dinner'/'snack'), or max_time_minutes."
    )
    parameters = vol.Schema(
        {
            vol.Optional("constraints"): str,
            vol.Optional("meal_slot"): vol.In(
                ["breakfast", "lunch", "dinner", "snack"]
            ),
            vol.Optional("max_time_minutes"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=1440)
            ),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        # Route through the registered HA service so Premium gating, AI
        # mode dispatch, BYOK key resolution and the Repairs upsell flow
        # are all preserved (see services.py:handle_suggest_meal).
        if not hass.services.has_service(DOMAIN, "suggest_meal"):
            return _not_configured()

        service_data: dict[str, Any] = {
            k: v
            for k, v in {
                "constraints": tool_input.tool_args.get("constraints"),
                "meal_slot": tool_input.tool_args.get("meal_slot"),
                "max_time_minutes": tool_input.tool_args.get("max_time_minutes"),
            }.items()
            if v is not None
        }

        # ``suggest_meal`` fires a domain event with the result rather
        # than returning text. We capture the next event so the LLM gets
        # the suggestion synchronously.
        captured: dict[str, Any] = {}
        event_name = f"{DOMAIN}_suggest_meal_result"

        def _capture(event: Any) -> None:
            if not captured:
                captured.update(event.data)

        cancel = hass.bus.async_listen(event_name, _capture)
        try:
            await hass.services.async_call(
                DOMAIN,
                "suggest_meal",
                service_data,
                blocking=True,
            )
        finally:
            cancel()

        if not captured:
            return {
                "error": "no_result",
                "message": "The suggestion service ran but produced no result.",
            }
        return {
            "suggestion": captured.get("result", ""),
            "ai_mode": captured.get("mode"),
        }


class _AddToShoppingListTool(llm.Tool):
    """Add an item to the user's shopping list."""

    name = "add_to_shopping_list"
    description = (
        "Add an item to the user's Culiplan shopping list. Use this for "
        "requests like 'add milk to my shopping list' or 'put two "
        "kilograms of potatoes on the list'."
    )
    parameters = vol.Schema(
        {
            vol.Required("name"): vol.All(str, vol.Length(min=1, max=200)),
            vol.Optional("quantity"): vol.All(str, vol.Length(max=80)),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        client = _get_client(hass)
        if not client:
            return _not_configured()

        name = tool_input.tool_args["name"]
        quantity = tool_input.tool_args.get("quantity")
        # The backend has one shopping list per user; api.py wraps it as
        # a synthetic single-element list with id "default" (see
        # async_get_shopping_lists). The list_id param is preserved in
        # signatures but ignored server-side.
        created = await client.async_add_shopping_item(
            "default", name=name, quantity=quantity
        )
        return {
            "added": True,
            "name": name,
            "quantity": quantity,
            "item_id": created.get("id") if isinstance(created, dict) else None,
        }


class _FindRecipesByIngredientsTool(llm.Tool):
    """Search recipes by ingredient list."""

    name = "find_recipes_by_ingredients"
    description = (
        "Find recipes the user can make from a list of ingredients they "
        "have. Returns up to 10 matches with id, title and prep time. "
        "Use this for 'what can I cook with chicken and broccoli?' or "
        "'recipes that use leftover rice'."
    )
    parameters = vol.Schema(
        {
            vol.Required("ingredients"): vol.All([str], vol.Length(min=1, max=20)),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        client = _get_client(hass)
        if not client:
            return _not_configured()

        ingredients = tool_input.tool_args["ingredients"]
        # The backend's GET /api/recipes accepts comma-separated
        # ingredients and a 10-item page limit suffices for LLM display.
        query = ",".join(ingredients)
        from urllib.parse import quote

        path = f"/api/recipes?ingredients={quote(query)}&limit=10"
        result = await client.async_get(path)
        # The endpoint returns either a {data, pagination} envelope or a
        # bare list, depending on cursor mode. Normalise.
        recipes_raw: Any
        if isinstance(result, dict) and "data" in result:
            recipes_raw = result["data"]
        elif isinstance(result, list):
            recipes_raw = result
        else:
            recipes_raw = []

        recipes: list[dict[str, Any]] = []
        if isinstance(recipes_raw, list):
            for r in recipes_raw[:10]:
                if not isinstance(r, dict):
                    continue
                recipes.append(
                    {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "prep_time_minutes": r.get("prepTime")
                        or r.get("prepTimeMinutes"),
                        "servings": r.get("servings"),
                    }
                )

        return {
            "recipes": recipes,
            "count": len(recipes),
            "ingredients_searched": ingredients,
        }


class _GetRecipeTool(llm.Tool):
    """Fetch full details for a single recipe by ID."""

    name = "get_recipe"
    description = (
        "Fetch full details for a recipe by ID — ingredients, "
        "instructions, prep time, servings. Use the recipe_id returned "
        "by find_recipes_by_ingredients or get_meal_plan."
    )
    parameters = vol.Schema(
        {
            vol.Required("recipe_id"): vol.All(str, vol.Length(min=1, max=200)),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        client = _get_client(hass)
        if not client:
            return _not_configured()

        recipe_id = tool_input.tool_args["recipe_id"]
        from urllib.parse import quote

        recipe = await client.async_get(f"/api/recipes/{quote(recipe_id, safe='')}")
        if not isinstance(recipe, dict):
            return {
                "error": "not_found",
                "message": f"No recipe found for id '{recipe_id}'.",
            }
        # Trim large fields the LLM doesn't need (image variants, audit
        # metadata, etc.) so the tool payload stays well under the
        # Conversation Agent's context window.
        keep_keys = {
            "id",
            "title",
            "description",
            "ingredients",
            "instructions",
            "prepTime",
            "cookTime",
            "totalTime",
            "servings",
            "cuisine",
            "tags",
            "calories",
            "nutritionPerServing",
        }
        trimmed: dict[str, Any] = {k: v for k, v in recipe.items() if k in keep_keys}
        return {"recipe": trimmed}


class _GetPantryItemsTool(llm.Tool):
    """Return pantry stock, optionally filtered to items expiring soon."""

    name = "get_pantry_items"
    description = (
        "Return the user's pantry stock. Optional expiring_within_days "
        "filters to items expiring in that many days (use 3 or 7 for "
        "'what's about to expire?' questions). Otherwise returns all "
        "tracked pantry items."
    )
    parameters = vol.Schema(
        {
            vol.Optional("expiring_within_days"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=365)
            ),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        client = _get_client(hass)
        if not client:
            return _not_configured()

        items = await client.async_get_pantry_items()
        within_days = tool_input.tool_args.get("expiring_within_days")
        if within_days is not None:
            items = _filter_expiring(items, int(within_days))

        # Strip internal fields and cap to 50 for context-window safety.
        slimmed = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "expires_at": item.get("expiresAt"),
            }
            for item in items[:50]
            if isinstance(item, dict)
        ]
        return cast(
            JsonObjectType,
            {
                "pantry_items": slimmed,
                "count": len(slimmed),
                "truncated": len(items) > 50,
            },
        )


# ─── Date helpers ────────────────────────────────────────────────────────────


def _slot_in_range(date_value: Any, start: str | None, end: str | None) -> bool:
    """Return True if a slot's date falls within [start, end] (ISO YYYY-MM-DD)."""
    if not isinstance(date_value, str):
        return True  # Don't filter out slots with unparseable dates.
    # Date may be a full ISO timestamp; truncate to date-only for comparison.
    date_only = date_value[:10]
    if start and date_only < start:
        return False
    if end and date_only > end:
        return False
    return True


def _filter_expiring(
    items: list[dict[str, Any]], within_days: int
) -> list[dict[str, Any]]:
    """Return only items expiring within ``within_days`` from today.

    Items without an ``expiresAt`` are excluded — by definition they
    aren't expiring soon. Date math is done in UTC; sub-day precision
    isn't meaningful for a "next N days" question.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(tz=timezone.utc)
    cutoff = now + timedelta(days=within_days)

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        expires_raw = item.get("expiresAt")
        if not isinstance(expires_raw, str):
            continue
        try:
            # fromisoformat in 3.12 accepts trailing Z via Python 3.11+
            # but not all backends emit it; normalise.
            expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if expires <= cutoff:
            out.append(item)
    return out


# ─── Registration helpers ────────────────────────────────────────────────────


def async_register_llm_api(hass: HomeAssistant) -> None:
    """Register Culiplan as an HA LLM API.

    Idempotent across reloads: if the API id is already present in the
    singleton dict, we leave it alone rather than raising. HA's
    ``async_register_api`` itself raises on duplicate registration —
    that's fine on first setup but breaks integration reload, so we
    pre-check.
    """
    try:
        apis = hass.data.get("llm", {})
        if LLM_API_ID in apis:
            _LOGGER.debug(
                "[culiplan] LLM API '%s' already registered; skipping",
                LLM_API_ID,
            )
            return
        llm.async_register_api(hass, CuliplanLLMAPI(hass))
        _LOGGER.info(
            "[culiplan] Registered LLM API '%s' with %d tools",
            LLM_API_ID,
            len(_build_tools()),
        )
    except Exception as err:  # noqa: BLE001
        # Non-fatal: integration still works without the LLM surface.
        _LOGGER.warning(
            "[culiplan] Could not register LLM API (non-fatal): %s. "
            "Conversation Agents will not see Culiplan tools, but "
            "everything else continues to work.",
            err,
        )


def async_unregister_llm_api(hass: HomeAssistant) -> None:
    """Remove Culiplan from the HA LLM API registry.

    HA does not expose an ``async_unregister_api`` helper; we pop the
    entry from the singleton dict directly. ``hass.data["llm"]`` is the
    dict returned by ``_async_get_apis`` (see helpers/llm.py).
    """
    apis = hass.data.get("llm")
    if isinstance(apis, dict):
        apis.pop(LLM_API_ID, None)
        _LOGGER.debug("[culiplan] Deregistered LLM API '%s'", LLM_API_ID)
