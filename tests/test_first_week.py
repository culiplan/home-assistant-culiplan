"""Tests for the one-time "Plan your first week" Repairs hint (v0.16.0)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.culiplan import first_week as fw
from custom_components.culiplan.const import CONF_FIRST_WEEK_HINT, DOMAIN, PLANNER_URL

_MEAL = {"id": "m1", "date": "2026-10-28T18:00:00Z", "title": "Pasta"}


def _plans(*slots: dict) -> dict:
    return {
        "meal_plans": [{"id": "current", "name": "Meal Plan", "slots": list(slots)}]
    }


def _coordinator(data: dict | None, history: list | Exception | None = None):
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = True
    coordinator.listeners = []
    unsub = MagicMock()

    def _add_listener(cb):  # type: ignore[no-untyped-def]
        coordinator.listeners.append(cb)
        return unsub

    coordinator.async_add_listener = MagicMock(side_effect=_add_listener)
    coordinator.unsub = unsub
    if isinstance(history, Exception):
        coordinator.client.async_get_meal_plans = AsyncMock(side_effect=history)
    else:
        coordinator.client.async_get_meal_plans = AsyncMock(
            return_value=history
            if history is not None
            else [{"id": "current", "slots": []}]
        )
    return coordinator


def _entry(hass, hint: bool = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_FIRST_WEEK_HINT: True} if hint else {}
    )
    entry.add_to_hass(hass)
    return entry


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, fw.first_week_issue_id(entry.entry_id)
    )


async def _done_ids(hass) -> set[str]:
    return await fw._async_done_ids(hass)


# ─── has_planned_meals ───────────────────────────────────────────────────────


def test_has_planned_meals():
    assert fw.has_planned_meals(_plans(_MEAL)) is True
    assert fw.has_planned_meals(_plans()) is False
    assert fw.has_planned_meals({"meal_plans": []}) is False
    assert fw.has_planned_meals(None) is False
    assert fw.has_planned_meals({"meal_plans": ["junk"]}) is False


# ─── Eligibility ─────────────────────────────────────────────────────────────


async def test_existing_install_without_flag_is_never_hinted(hass):
    """Entries created before 0.16.0 have no flag: nothing happens."""
    entry = _entry(hass, hint=False)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)

    await hint.async_start()

    assert hint.active is False
    coordinator.async_add_listener.assert_not_called()
    assert _issue(hass, entry) is None


async def test_already_done_entry_is_not_hinted_again(hass):
    entry = _entry(hass)
    await fw.async_mark_first_week_done(hass, entry.entry_id)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)

    await hint.async_start()

    assert hint.active is False
    assert _issue(hass, entry) is None


async def test_meals_at_start_marks_done_without_issue(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans(_MEAL))
    hint = fw.FirstWeekHint(hass, entry, coordinator)

    await hint.async_start()

    assert hint.active is False
    assert entry.entry_id in await _done_ids(hass)
    assert _issue(hass, entry) is None
    coordinator.unsub.assert_called()


# ─── Raising the issue ───────────────────────────────────────────────────────


async def test_empty_account_gets_issue_after_grace_period(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)

    await hint.async_start()
    # Inside the grace period: no issue yet, no history call.
    assert _issue(hass, entry) is None
    coordinator.client.async_get_meal_plans.assert_not_called()

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=fw.GRACE_PERIOD_SECONDS + 1)
    )
    await hass.async_block_till_done()

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.translation_key == "plan_first_week"
    assert issue.translation_placeholders == {"planner_url": PLANNER_URL}
    assert issue.learn_more_url == PLANNER_URL
    # History check asked for a long look-back window.
    start, end = coordinator.client.async_get_meal_plans.call_args[0]
    assert (end - start).days >= fw.HISTORY_LOOKBACK_DAYS
    hint.async_stop()


async def test_issue_auto_dismisses_when_meals_appear(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True
    await hint.async_evaluate()
    assert _issue(hass, entry) is not None

    # A meal is planned in Culiplan; the push channel updates the coordinator.
    coordinator.data = _plans(_MEAL)
    for listener in coordinator.listeners:
        listener()
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None
    assert entry.entry_id in await _done_ids(hass)
    assert hint.active is False

    # Emptying the plan again never brings the hint back.
    coordinator.data = _plans()
    await hint.async_evaluate()
    assert _issue(hass, entry) is None


async def test_account_that_planned_before_is_never_hinted(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans(), history=[{"id": "current", "slots": [_MEAL]}])
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True

    await hint.async_evaluate()

    assert _issue(hass, entry) is None
    assert entry.entry_id in await _done_ids(hass)


async def test_failed_history_check_raises_nothing_and_retries(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans(), history=RuntimeError("boom"))
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True

    await hint.async_evaluate()
    assert _issue(hass, entry) is None
    assert hint.active is True

    coordinator.client.async_get_meal_plans = AsyncMock(
        return_value=[{"id": "current", "slots": []}]
    )
    await hint.async_evaluate()
    assert _issue(hass, entry) is not None
    hint.async_stop()


async def test_no_issue_while_coordinator_has_no_good_data(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    coordinator.last_update_success = False
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True

    await hint.async_evaluate()

    assert _issue(hass, entry) is None
    coordinator.client.async_get_meal_plans.assert_not_called()
    hint.async_stop()


async def test_meals_arriving_during_history_check_win(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())

    async def _history(*_args):  # type: ignore[no-untyped-def]
        coordinator.data = _plans(_MEAL)
        return [{"id": "current", "slots": []}]

    coordinator.client.async_get_meal_plans = AsyncMock(side_effect=_history)
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True

    await hint.async_evaluate()

    assert _issue(hass, entry) is None
    assert entry.entry_id in await _done_ids(hass)


async def test_concurrent_evaluation_is_skipped(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True
    hint._evaluating = True

    await hint.async_evaluate()

    coordinator.client.async_get_meal_plans.assert_not_called()
    hint._evaluating = False
    hint.async_stop()


# ─── Stop / done / forget ────────────────────────────────────────────────────


async def test_stop_unsubscribes_and_ignores_updates(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()

    hint.async_stop()

    assert hint.active is False
    coordinator.unsub.assert_called_once()  # coordinator listener
    assert hint._unsubs == []  # grace timer cancelled too
    for listener in coordinator.listeners:
        listener()
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None


async def test_mark_done_from_fix_flow_stops_running_hint(hass):
    entry = _entry(hass)
    coordinator = _coordinator(_plans())
    hint = fw.FirstWeekHint(hass, entry, coordinator)
    await hint.async_start()
    hint._grace_over = True
    await hint.async_evaluate()
    assert _issue(hass, entry) is not None

    await fw.async_mark_first_week_done(hass, entry.entry_id)
    # Idempotent.
    await fw.async_mark_first_week_done(hass, entry.entry_id)

    assert hint.active is False
    assert _issue(hass, entry) is None
    assert await _done_ids(hass) == {entry.entry_id}


async def test_forget_on_entry_removal(hass):
    entry = _entry(hass)
    await fw.async_mark_first_week_done(hass, entry.entry_id)
    ir.async_create_issue(
        hass,
        DOMAIN,
        fw.first_week_issue_id(entry.entry_id),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="plan_first_week",
    )

    from custom_components.culiplan import async_remove_entry

    await async_remove_entry(hass, entry)
    # Second call is a no-op.
    await fw.async_forget_first_week(hass, entry.entry_id)

    assert _issue(hass, entry) is None
    assert entry.entry_id not in await _done_ids(hass)


@pytest.mark.parametrize("lang", ["en", "de", "es", "fr", "nl"])
def test_issue_strings_exist_in_every_language(lang):
    import json
    from pathlib import Path

    path = (
        Path(__file__).parent.parent
        / "custom_components"
        / "culiplan"
        / "translations"
        / f"{lang}.json"
    )
    issues = json.loads(path.read_text(encoding="utf-8"))["issues"]
    confirm = issues["plan_first_week"]["fix_flow"]["step"]["confirm"]
    assert "{planner_url}" in confirm["description"]
    assert "{support_url}" in issues["feature_unavailable"]["description"]
