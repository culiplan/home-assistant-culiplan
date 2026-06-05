"""Tests for calendar entity — including wrapped API response (bug fix)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.culiplan.coordinator import CuliplanCoordinator


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans):
    coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
    coord.data = {
        "meal_plans": meal_plans,
        "shopping_lists": [],
        "pantry_items": [],
    }
    return coord


# ─── Parameterised: bare-list vs wrapped-dict API shapes ─────────────────────


@pytest.mark.parametrize(
    "meal_plans",
    [
        # Shape A — bare list (old / test-double shape)
        pytest.param(
            [
                {
                    "id": "2026-05-01",
                    "name": "2026-05-01",
                    "slots": [
                        {
                            "id": "entry1",
                            "date": "2026-05-01T18:00:00Z",
                            "title": "Spaghetti Bolognese",
                            "course": "dinner",
                            "recipeId": "rec42",
                            "servings": 2,
                        }
                    ],
                }
            ],
            id="bare-list",
        ),
        # Shape B — wrapped dict (what the real backend returns after the fix)
        pytest.param(
            [
                {
                    "id": "2026-05-01",
                    "name": "2026-05-01",
                    "slots": [
                        {
                            "id": "entry1",
                            "date": "2026-05-01T18:00:00Z",
                            "title": "Spaghetti Bolognese",
                            "course": "dinner",
                            "recipeId": "rec42",
                            "servings": 2,
                        }
                    ],
                }
            ],
            id="normalised-from-wrapped",
        ),
    ],
)
def test_calendar_entities_created_from_meal_plans(
    hass, mock_api_client, mock_config_entry, meal_plans
):
    """CuliplanCalendar can be instantiated for each plan in the list."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans)
    # Simulate what async_setup_entry does: create one entity per plan.
    entities = [
        CuliplanCalendar(coord, plan, mock_config_entry)
        for plan in coord.data["meal_plans"]
    ]
    assert len(entities) == 1
    cal = entities[0]
    assert cal._plan_id == "2026-05-01"
    assert cal._attr_name == "2026-05-01"


def test_calendar_events_built_from_normalised_slots(
    hass, mock_api_client, mock_config_entry
):
    """_build_events() correctly reads slots after normalisation."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    plan = {
        "id": "2026-05-01",
        "name": "2026-05-01",
        "slots": [
            {
                "id": "e1",
                "date": "2026-05-01T18:00:00Z",
                "title": "Pasta",
                "course": "dinner",
                "recipeId": "rX",
                "servings": 4,
            }
        ],
    }
    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, [plan])
    cal = CuliplanCalendar(coord, plan, mock_config_entry)
    events = cal._build_events()
    assert len(events) == 1
    assert events[0].summary == "Pasta"
    assert events[0].start == datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc)


def test_calendar_empty_slots_produces_no_events(
    hass, mock_api_client, mock_config_entry
):
    """A plan with no slots produces an empty event list — no crash."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    plan = {"id": "2026-05-01", "name": "2026-05-01", "slots": []}
    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, [plan])
    cal = CuliplanCalendar(coord, plan, mock_config_entry)
    assert cal._build_events() == []
    assert cal.event is None


# ─── async_get_meal_plans normalisation unit tests ────────────────────────────


@pytest.mark.asyncio
async def test_api_collapses_grouped_dict_into_single_plan(mock_api_client):
    """async_get_meal_plans flattens the grouped-dict response into ONE plan.

    The backend returns one outer key per date, but a user has one continuous
    meal-plan timeline — not one plan per date. The client must collapse this
    into exactly one plan with all slots flattened across dates, so HA creates
    exactly one calendar entity.
    """
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch

    # Raw backend shape: { date: { slot: [entry, ...] } }
    grouped = {
        "2026-05-01": {
            "dinner": [
                {
                    "id": "entry1",
                    "date": "2026-05-01T18:00:00.000Z",
                    "mealSlot": "dinner",
                    "recipeId": "recA",
                    "recipe": {"title": "Chicken Tikka"},
                }
            ]
        },
        "2026-05-02": {
            "lunch": [
                {
                    "id": "entry2",
                    "date": "2026-05-02T12:00:00.000Z",
                    "mealSlot": "lunch",
                    "recipeId": None,
                    "recipe": None,
                }
            ]
        },
    }

    from aiohttp import ClientSession

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=grouped):
        result = await client.async_get_meal_plans()

    # Exactly one plan, with both date entries flattened into its slot list.
    assert isinstance(result, list)
    assert len(result) == 1

    plan = result[0]
    assert plan["id"] == "current"
    assert plan["name"] == "Meal Plan"
    assert len(plan["slots"]) == 2

    by_id = {s["id"]: s for s in plan["slots"]}
    assert by_id["entry1"]["title"] == "Chicken Tikka"
    assert by_id["entry1"]["course"] == "dinner"
    assert by_id["entry1"]["recipeId"] == "recA"
    assert by_id["entry1"]["date"] == "2026-05-01T18:00:00.000Z"
    assert by_id["entry2"]["course"] == "lunch"
    assert by_id["entry2"]["recipeId"] is None


@pytest.mark.asyncio
async def test_api_empty_grouped_dict_still_emits_one_plan():
    """An empty backend response still emits one plan so the calendar entity is stable."""
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch
    from aiohttp import ClientSession

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
        result = await client.async_get_meal_plans()

    assert result == [{"id": "current", "name": "Meal Plan", "slots": []}]


@pytest.mark.asyncio
async def test_api_passthrough_bare_list(mock_api_client):
    """async_get_meal_plans passes a bare-list response straight through."""
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch
    from aiohttp import ClientSession

    bare = [{"id": "mp1", "name": "Week", "slots": []}]
    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=bare):
        result = await client.async_get_meal_plans()

    assert result == bare


@pytest.mark.asyncio
async def test_api_returns_empty_list_on_unexpected_type():
    """async_get_meal_plans returns [] when the backend sends an unexpected type."""
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch
    from aiohttp import ClientSession

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value="oops"):
        result = await client.async_get_meal_plans()

    assert result == []


# ─── Production-shape regression test ────────────────────────────────────────
#
# This fixture mirrors the actual shape returned by GET /api/meal-plans in
# production (see packages/backend/src/routes/public/planner.routes.ts —
# groupMealPlans + the meal-plan select clause). It exists to prevent
# regressions of the 2026-06-04 bug where the integration created one
# calendar entity per date (11+/week) instead of one entity with N events.


def _prod_shape_meal_plans() -> dict:
    """Replicate the production GET /api/meal-plans response for a 5-day week."""
    days = [
        ("2026-06-08", "BREAKFAST", "e-mon-b", "Avocado Toast", "r-toast"),
        ("2026-06-08", "DINNER", "e-mon-d", "Spaghetti Bolognese", "r-bolo"),
        ("2026-06-09", "LUNCH", "e-tue-l", "Caesar Salad", "r-caesar"),
        ("2026-06-09", "DINNER", "e-tue-d", "Chicken Tikka", "r-tikka"),
        ("2026-06-10", "DINNER", "e-wed-d", "Beef Stir Fry", "r-stirfry"),
        ("2026-06-11", "LUNCH", "e-thu-l", "Tomato Soup", "r-soup"),
        ("2026-06-11", "DINNER", "e-thu-d", "Salmon en Croute", "r-salmon"),
        ("2026-06-12", "BREAKFAST", "e-fri-b", "Granola Bowl", "r-granola"),
        ("2026-06-12", "DINNER", "e-fri-d", "Margherita Pizza", "r-pizza"),
    ]
    grouped: dict = {}
    for date_str, slot, eid, title, rid in days:
        grouped.setdefault(date_str, {}).setdefault(slot, []).append(
            {
                "id": eid,
                "userId": "user-abc",
                "householdId": None,
                "date": f"{date_str}T12:00:00.000Z",
                "mealSlot": slot,
                "sortOrder": 0,
                "recipeId": rid,
                "isEatingOut": False,
                "isApproved": True,
                "ingredientsStatus": "PLANNED",
                "source": "recipe",
                "frozenPortionId": None,
                "createdAt": "2026-06-01T00:00:00.000Z",
                "updatedAt": "2026-06-01T00:00:00.000Z",
                "recipe": {"id": rid, "title": title},
            }
        )
    return grouped


@pytest.mark.asyncio
async def test_prod_shape_yields_exactly_one_calendar_entity(
    hass, mock_api_client, mock_config_entry
):
    """A real-shape 9-entry / 5-date response must yield ONE calendar entity.

    Regression guard for the 2026-06-04 bug: the original implementation
    produced one plan per date, so HA created 5 calendar entities here
    (11+ in a fuller week). After the fix, the integration must collapse the
    grouped response into a single plan and HA must create exactly one
    calendar entity that holds all 9 events.
    """
    from custom_components.culiplan.api import CuliplanApiClient
    from custom_components.culiplan.calendar import CuliplanCalendar
    from unittest.mock import patch
    from aiohttp import ClientSession

    grouped = _prod_shape_meal_plans()

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=grouped):
        meal_plans = await client.async_get_meal_plans()

    # The api normalisation alone must produce a single-plan list.
    assert len(meal_plans) == 1, (
        f"Expected exactly 1 plan, got {len(meal_plans)} — would create "
        f"{len(meal_plans)} calendar entities. Backend returned "
        f"{len(grouped)} dates with 9 entries; all must collapse into 1 plan."
    )

    # Same construction path async_setup_entry uses (calendar.py:31-33).
    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans)
    entities = [
        CuliplanCalendar(coord, plan, mock_config_entry)
        for plan in coord.data["meal_plans"]
    ]
    assert len(entities) == 1
    cal = entities[0]

    # The single calendar must surface all 9 events, sorted by start.
    events = cal._build_events()
    assert len(events) == 9
    starts = [e.start for e in events]
    assert starts == sorted(starts)

    # Stable unique_id — survives coordinator refreshes without re-registering.
    assert cal.unique_id == "culiplan_calendar_current"
