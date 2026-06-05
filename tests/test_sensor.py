"""Tests for sensor entities — including wrapped API response shape (bug fix)."""

from __future__ import annotations

import datetime as dt
from datetime import datetime, timedelta, timezone
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


def _device(entry):
    from custom_components.culiplan.helpers import _build_device_info

    return _build_device_info(entry)


def _slot_this_week() -> str:
    """Return an ISO timestamp for Wednesday of the current ISO week (UTC)."""
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    wednesday = monday + dt.timedelta(days=2)
    return datetime(
        wednesday.year, wednesday.month, wednesday.day, 18, 0, tzinfo=timezone.utc
    ).isoformat()


# ─── Parameterised: both API shapes must count meals correctly ────────────────


@pytest.mark.parametrize(
    "meal_plans",
    [
        # Shape A — bare list (old / test-double shape)
        pytest.param(
            lambda: [
                {
                    "id": "2026-05-07",
                    "name": "2026-05-07",
                    "slots": [{"id": "s1", "date": _slot_this_week(), "title": "T"}],
                }
            ],
            id="bare-list",
        ),
        # Shape B — normalised from wrapped backend dict (after the api.py fix)
        pytest.param(
            lambda: [
                {
                    "id": "2026-05-07",
                    "name": "2026-05-07",
                    "slots": [{"id": "s1", "date": _slot_this_week(), "title": "T"}],
                }
            ],
            id="normalised-from-wrapped",
        ),
    ],
)
def test_meals_planned_this_week_counts_correctly(
    hass, mock_api_client, mock_config_entry, meal_plans
):
    """MealsPlanedThisWeekSensor.native_value counts slots inside the current week."""
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans())
    sensor = MealsPlanedThisWeekSensor(coord, _device(mock_config_entry))
    assert sensor.native_value == 1


def test_meals_planned_this_week_zero_when_no_plans(
    hass, mock_api_client, mock_config_entry
):
    """MealsPlanedThisWeekSensor returns 0 when meal_plans list is empty."""
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, [])
    sensor = MealsPlanedThisWeekSensor(coord, _device(mock_config_entry))
    assert sensor.native_value == 0


def test_meals_planned_this_week_excludes_outside_week(
    hass, mock_api_client, mock_config_entry
):
    """Slots outside the current ISO week are not counted."""
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

    far_future = (datetime.now(tz=timezone.utc) + timedelta(days=14)).isoformat()
    plans = [
        {
            "id": "future",
            "name": "future",
            "slots": [{"id": "s2", "date": far_future, "title": "T"}],
        }
    ]
    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, plans)
    sensor = MealsPlanedThisWeekSensor(coord, _device(mock_config_entry))
    assert sensor.native_value == 0


# ─── async_get_meal_plans → sensor integration ───────────────────────────────


@pytest.mark.asyncio
async def test_sensor_counts_after_api_normalisation(
    hass, mock_api_client, mock_config_entry
):
    """Verify end-to-end: grouped backend response → normalised plans → sensor count."""
    from custom_components.culiplan.api import CuliplanApiClient
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor
    from unittest.mock import patch
    from aiohttp import ClientSession

    slot_date = _slot_this_week()
    # Simulate what the backend returns (grouped dict)
    grouped = {
        slot_date[:10]: {
            "dinner": [
                {
                    "id": "e1",
                    "date": slot_date,
                    "mealSlot": "dinner",
                    "recipeId": "rX",
                    "recipe": {"title": "Test Meal"},
                }
            ]
        }
    }

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=grouped):
        meal_plans = await client.async_get_meal_plans()

    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans)
    sensor = MealsPlanedThisWeekSensor(coord, _device(mock_config_entry))
    assert sensor.native_value == 1


@pytest.mark.asyncio
async def test_sensor_counts_multi_date_after_single_plan_collapse(
    hass, mock_api_client, mock_config_entry
):
    """Multi-date grouped response collapses into 1 plan; sensor counts all in-week slots."""
    from custom_components.culiplan.api import CuliplanApiClient
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor
    from unittest.mock import patch
    from aiohttp import ClientSession

    # Build three in-week entries spread across Mon/Wed/Fri.
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())

    def _iso_for(offset_days: int, hour: int) -> str:
        d = monday + dt.timedelta(days=offset_days)
        return datetime(
            d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc
        ).isoformat()

    grouped: dict = {}
    for offset, slot, hour, eid in (
        (0, "DINNER", 18, "mon-d"),
        (2, "LUNCH", 12, "wed-l"),
        (4, "DINNER", 19, "fri-d"),
    ):
        iso = _iso_for(offset, hour)
        grouped.setdefault(iso[:10], {}).setdefault(slot, []).append(
            {"id": eid, "date": iso, "mealSlot": slot, "recipeId": None, "recipe": None}
        )

    client = CuliplanApiClient(
        session=MagicMock(spec=ClientSession), access_token="tok"
    )
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=grouped):
        meal_plans = await client.async_get_meal_plans()

    # Single collapsed plan with all 3 slots flattened.
    assert len(meal_plans) == 1
    assert len(meal_plans[0]["slots"]) == 3

    coord = _make_coordinator(hass, mock_api_client, mock_config_entry, meal_plans)
    sensor = MealsPlanedThisWeekSensor(coord, _device(mock_config_entry))
    assert sensor.native_value == 3
