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
async def test_api_unwraps_grouped_dict_response(mock_api_client):
    """async_get_meal_plans converts the grouped-dict backend response to a list."""
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

    client = CuliplanApiClient(session=MagicMock(spec=ClientSession), access_token="tok")
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=grouped):
        result = await client.async_get_meal_plans()

    assert isinstance(result, list)
    assert len(result) == 2

    # Locate the two plans by id
    plan_by_id = {p["id"]: p for p in result}
    assert "2026-05-01" in plan_by_id
    assert "2026-05-02" in plan_by_id

    plan1 = plan_by_id["2026-05-01"]
    assert plan1["slots"][0]["id"] == "entry1"
    assert plan1["slots"][0]["title"] == "Chicken Tikka"
    assert plan1["slots"][0]["course"] == "dinner"
    assert plan1["slots"][0]["recipeId"] == "recA"

    plan2 = plan_by_id["2026-05-02"]
    assert plan2["slots"][0]["course"] == "lunch"


@pytest.mark.asyncio
async def test_api_passthrough_bare_list(mock_api_client):
    """async_get_meal_plans passes a bare-list response straight through."""
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch
    from aiohttp import ClientSession

    bare = [{"id": "mp1", "name": "Week", "slots": []}]
    client = CuliplanApiClient(session=MagicMock(spec=ClientSession), access_token="tok")
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=bare):
        result = await client.async_get_meal_plans()

    assert result == bare


@pytest.mark.asyncio
async def test_api_returns_empty_list_on_unexpected_type():
    """async_get_meal_plans returns [] when the backend sends an unexpected type."""
    from custom_components.culiplan.api import CuliplanApiClient
    from unittest.mock import patch
    from aiohttp import ClientSession

    client = CuliplanApiClient(session=MagicMock(spec=ClientSession), access_token="tok")
    with patch.object(client, "_get", new_callable=AsyncMock, return_value="oops"):
        result = await client.async_get_meal_plans()

    assert result == []
