"""Final coverage push — helpers, todo CRUD, calendar coordinator updates,
sensor edge cases, api endpoint helpers, and dispatcher reconnect branches.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.const import DOMAIN


# ─── helpers.parse_dt ────────────────────────────────────────────────────────


class TestParseDt:
    def test_iso_with_tz(self):
        from custom_components.culiplan.helpers import parse_dt

        dt = parse_dt("2026-06-07T18:00:00+00:00")
        assert dt.tzinfo is not None

    def test_iso_with_zulu(self):
        from custom_components.culiplan.helpers import parse_dt

        dt = parse_dt("2026-06-07T18:00:00Z")
        assert dt.tzinfo is not None

    def test_iso_naive(self):
        """A naive datetime gets stamped UTC."""
        from custom_components.culiplan.helpers import parse_dt

        dt = parse_dt("2026-06-07T18:00:00")
        assert dt.tzinfo == timezone.utc

    def test_date_only(self):
        """A bare date falls back to midnight UTC."""
        from custom_components.culiplan.helpers import parse_dt

        dt = parse_dt("2026-06-07")
        assert dt.hour == 0
        assert dt.tzinfo == timezone.utc


class TestBuildDeviceInfo:
    def test_includes_manifest_version(self):
        from custom_components.culiplan.helpers import _build_device_info

        entry = MagicMock()
        entry.entry_id = "e1"
        info = _build_device_info(entry)
        assert (DOMAIN, "e1") in info["identifiers"]
        assert info["manufacturer"] == "Culiplan"
        # sw_version is the manifest's version (always populated for the real repo).
        assert info["sw_version"] is not None

    def test_manifest_failure_returns_none_sw_version(self):
        from custom_components.culiplan import helpers

        with patch.object(
            helpers,
            "_MANIFEST_PATH",
            MagicMock(read_text=MagicMock(side_effect=OSError("boom"))),
        ):
            entry = MagicMock()
            entry.entry_id = "e1"
            info = helpers._build_device_info(entry)
            assert info["sw_version"] is None


# ─── todo.async_update / async_delete ────────────────────────────────────────


@pytest.mark.asyncio
async def test_todo_update_calls_api_and_writes_state():
    from custom_components.culiplan.todo import CuliplanShoppingList
    from homeassistant.components.todo import TodoItem, TodoItemStatus

    client = MagicMock()
    client.async_update_shopping_item = AsyncMock(return_value={"id": "i1"})
    coordinator = MagicMock()
    coordinator.client = client
    coordinator._refresh_shopping_lists = AsyncMock()
    coordinator.data = {"shopping_lists": [{"id": "sl1", "items": []}]}

    entry = MagicMock()
    entity = CuliplanShoppingList(coordinator, {"id": "sl1"}, entry)
    entity.async_write_ha_state = MagicMock()
    item = TodoItem(uid="i1", summary="x", status=TodoItemStatus.COMPLETED)
    await entity.async_update_todo_item(item)
    client.async_update_shopping_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_todo_delete_calls_api_per_uid():
    from custom_components.culiplan.todo import CuliplanShoppingList

    client = MagicMock()
    client.async_remove_shopping_item = AsyncMock()
    coordinator = MagicMock()
    coordinator.client = client
    coordinator._refresh_shopping_lists = AsyncMock()
    coordinator.data = {"shopping_lists": []}

    entry = MagicMock()
    entity = CuliplanShoppingList(coordinator, {"id": "sl1"}, entry)
    entity.async_write_ha_state = MagicMock()
    await entity.async_delete_todo_items(["i1", "i2"])
    assert client.async_remove_shopping_item.await_count == 2


def test_todo_items_returns_empty_when_list_id_unknown():
    """If the coordinator data doesn't include this list, todo_items is empty."""
    from custom_components.culiplan.todo import CuliplanShoppingList

    coordinator = MagicMock()
    coordinator.data = {"shopping_lists": [{"id": "other", "items": []}]}
    entry = MagicMock()
    entity = CuliplanShoppingList(coordinator, {"id": "missing"}, entry)
    assert entity.todo_items == []


# ─── calendar handle_coordinator_update / event accessor ─────────────────────


def test_calendar_event_none_when_all_in_past():
    """`event` is None when every event in the meal plan is in the past."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    coordinator = MagicMock()
    past_iso = "2020-01-01T18:00:00Z"
    coordinator.data = {
        "meal_plans": [
            {
                "id": "p1",
                "name": "P1",
                "slots": [{"id": "s1", "date": past_iso, "title": "Old Meal"}],
            }
        ]
    }
    entry = MagicMock()
    cal = CuliplanCalendar(coordinator, coordinator.data["meal_plans"][0], entry)
    assert cal.event is None


def test_calendar_extra_state_attributes_empty_without_event():
    from custom_components.culiplan.calendar import CuliplanCalendar

    coordinator = MagicMock()
    coordinator.data = {"meal_plans": [{"id": "p1", "name": "P1", "slots": []}]}
    entry = MagicMock()
    cal = CuliplanCalendar(coordinator, coordinator.data["meal_plans"][0], entry)
    assert cal.extra_state_attributes == {}


def test_calendar_handle_coordinator_update_refreshes_plan():
    """A coordinator update reads the matching plan from the refreshed data."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    coordinator = MagicMock()
    coordinator.data = {
        "meal_plans": [
            {"id": "p1", "name": "P1", "slots": []},
            {"id": "p2", "name": "P2", "slots": []},
        ]
    }
    entry = MagicMock()
    cal = CuliplanCalendar(coordinator, {"id": "p2"}, entry)
    cal.async_write_ha_state = MagicMock()
    cal._handle_coordinator_update()
    assert cal._plan["name"] == "P2"


def test_calendar_build_events_skips_malformed_slot():
    """A slot missing required fields is skipped silently."""
    from custom_components.culiplan.calendar import CuliplanCalendar

    coordinator = MagicMock()
    coordinator.data = {
        "meal_plans": [
            {
                "id": "p1",
                "slots": [
                    {"id": "s1"},  # missing date → skipped
                    {"id": "s2", "date": "2026-06-07T18:00:00Z", "title": "Pasta"},
                ],
            }
        ]
    }
    entry = MagicMock()
    cal = CuliplanCalendar(coordinator, {"id": "p1"}, entry)
    events = cal._build_events()
    assert len(events) == 1


# ─── sensor edge cases ───────────────────────────────────────────────────────


def test_meals_planned_this_week_swallows_malformed_dates():
    """A slot with a bad date string is skipped silently, not counted."""
    from custom_components.culiplan.sensor import MealsPlanedThisWeekSensor

    coordinator = MagicMock()
    coordinator.data = {
        "meal_plans": [
            {
                "id": "p1",
                "slots": [
                    {"id": "s1", "date": "not-a-date"},
                ],
            }
        ]
    }
    entry = MagicMock()
    entry.entry_id = "e1"
    device = MagicMock()
    sensor = MealsPlanedThisWeekSensor(coordinator, device, entry)
    # No crash; bad slot ignored.
    assert sensor.native_value == 0


def test_planned_kwh_today_handles_non_numeric_kwh():
    """If estimated_kwh isn't a number, the sensor returns 0 cleanly."""
    from custom_components.culiplan.sensor import PlannedKwhTodaySensor

    coordinator = MagicMock()
    coordinator.data = {"energy_today": {"estimated_kwh": "not-a-number"}}
    entry = MagicMock()
    entry.entry_id = "e1"
    sensor = PlannedKwhTodaySensor(coordinator, MagicMock(), entry)
    assert sensor.native_value == 0.0


def test_expiring_pantry_swallows_malformed_dates():
    from custom_components.culiplan.sensor import ExpiringPantrySensor

    coordinator = MagicMock()
    coordinator.data = {
        "pantry_items": [
            {"id": "p1", "expiresAt": "garbage"},
        ]
    }
    entry = MagicMock()
    entry.entry_id = "e1"
    sensor = ExpiringPantrySensor(coordinator, MagicMock(), entry, expiry_days=3)
    assert sensor.native_value == 0


# ─── api.async_get_meal_plans alternate paths ────────────────────────────────


@pytest.mark.asyncio
async def test_api_get_meal_plans_unparseable_date():
    """A non-string `date` is stringified rather than dropped."""
    from custom_components.culiplan.api import CuliplanApiClient

    session = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.ok = True
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(
        return_value={
            "2026-06-07": {
                "dinner": [
                    # `date` is None on the entry → falls back to <date_str>T12:00:00Z
                    {"id": "e1", "date": None, "recipe": None}
                ]
            }
        }
    )
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=resp)
    client = CuliplanApiClient(session=session, access_token="tok")
    result = await client.async_get_meal_plans()
    assert len(result[0]["slots"]) == 1
    assert "T12:00:00Z" in result[0]["slots"][0]["date"]


@pytest.mark.asyncio
async def test_api_call_voice_tool_post_body():
    """async_call_voice_tool posts with the {tool, params} envelope."""
    from custom_components.culiplan.api import CuliplanApiClient

    session = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.ok = True
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={"speakable": "OK"})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=resp)
    client = CuliplanApiClient(session=session, access_token="tok")
    result = await client.async_call_voice_tool(
        "suggest_meal", {"mealSlot": "dinner"}
    )
    assert result["speakable"] == "OK"
    # Body contains tool name + params.
    body = session.post.call_args.kwargs["json"]
    assert body["tool"] == "suggest_meal"
    assert body["params"]["mealSlot"] == "dinner"


@pytest.mark.asyncio
async def test_api_post_raw_returns_body_string_on_error():
    """_post_raw raises Exception("<status> <body>") for non-ok responses."""
    from custom_components.culiplan.api import CuliplanApiClient

    session = MagicMock()
    resp = MagicMock()
    resp.status = 500
    resp.ok = False
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(side_effect=Exception("not-json"))
    resp.text = AsyncMock(return_value="Internal error")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=resp)
    client = CuliplanApiClient(session=session, access_token="tok")
    with pytest.raises(Exception, match="500"):
        await client._post_raw("/x", {})


@pytest.mark.asyncio
async def test_api_get_energy_today_proxies():
    from custom_components.culiplan.api import CuliplanApiClient

    session = MagicMock()
    resp = MagicMock()
    resp.status = 200
    resp.ok = True
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={"date": "2026-06-07", "estimated_kwh": 1.0})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=resp)
    client = CuliplanApiClient(session=session, access_token="tok")
    result = await client.async_get_energy_today()
    assert result["estimated_kwh"] == 1.0


