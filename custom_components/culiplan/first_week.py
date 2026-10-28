"""One-time "Plan your first week" hint for brand-new, empty accounts (v0.16.0).

Most people who link Culiplan to Home Assistant are new to Culiplan. When the
account has no meals planned, the calendar and meal sensors are empty and
nothing explains why. This module raises a single fixable Repairs issue that
points to the Culiplan planner and says the calendar fills automatically.

Rules (no nagging):

* Only entries created by the v0.16.0+ setup flow are eligible
  (``CONF_FIRST_WEEK_HINT`` in ``entry.data``). Existing installs never see it.
* The coordinator already fetches the backend's default window (last 7 days
  plus the next 14). Any meal in it means the account has planned, so the
  hint is marked done for good and any open issue is removed.
* Before raising, a one-off history check (last year) makes sure accounts
  that planned before, just not recently, are never shown the hint.
* The issue waits a short grace period after setup, so a first week the
  backend seeds on link can arrive over the push channel first.
* Once done (meals appeared, or the user submitted the Repairs dialog) the
  entry id is stored in ``.storage/culiplan.first_week_hint`` and the hint is
  never raised again for that install.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CONF_FIRST_WEEK_HINT, DOMAIN, PLANNER_URL
from .coordinator import CuliplanCoordinator
from .repairs import FIRST_WEEK_ISSUE_PREFIX

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.first_week_hint"
STORAGE_VERSION = 1
_STORE_DATA_KEY = f"{DOMAIN}_first_week_store"
_HINTS_DATA_KEY = f"{DOMAIN}_first_week_hints"

# Seconds to wait after setup before the issue may be raised.
GRACE_PERIOD_SECONDS = 120
# How far back the one-off "planned before?" check looks.
HISTORY_LOOKBACK_DAYS = 365


def first_week_issue_id(entry_id: str) -> str:
    """Return the Repairs issue id for an entry."""
    return f"{FIRST_WEEK_ISSUE_PREFIX}{entry_id}"


def has_planned_meals(data: dict[str, Any] | None) -> bool:
    """Return True if the coordinator payload holds at least one meal."""
    for plan in (data or {}).get("meal_plans") or []:
        if isinstance(plan, dict) and plan.get("slots"):
            return True
    return False


def _store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    store: Store[dict[str, Any]] | None = hass.data.get(_STORE_DATA_KEY)
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        hass.data[_STORE_DATA_KEY] = store
    return store


async def _async_done_ids(hass: HomeAssistant) -> set[str]:
    data = await _store(hass).async_load() or {}
    return set(data.get("done", []))


async def async_mark_first_week_done(hass: HomeAssistant, entry_id: str) -> None:
    """Record the hint as done for an entry and remove its issue."""
    done = await _async_done_ids(hass)
    if entry_id not in done:
        done.add(entry_id)
        await _store(hass).async_save({"done": sorted(done)})
    ir.async_delete_issue(hass, DOMAIN, first_week_issue_id(entry_id))
    hint: FirstWeekHint | None = hass.data.get(_HINTS_DATA_KEY, {}).get(entry_id)
    if hint is not None:
        hint.async_stop()


async def async_forget_first_week(hass: HomeAssistant, entry_id: str) -> None:
    """Clean up when a config entry is removed."""
    ir.async_delete_issue(hass, DOMAIN, first_week_issue_id(entry_id))
    done = await _async_done_ids(hass)
    if entry_id in done:
        done.discard(entry_id)
        await _store(hass).async_save({"done": sorted(done)})


class FirstWeekHint:
    """Watches the coordinator and raises / clears the first-week issue."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: CuliplanCoordinator,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._active = False
        self._grace_over = False
        self._evaluating = False
        # None = not checked yet (or the check failed and should be retried).
        self._planned_before: bool | None = None
        self._unsubs: list[CALLBACK_TYPE] = []

    @property
    def active(self) -> bool:
        """Return True while the hint is still watching this entry."""
        return self._active

    async def async_start(self) -> None:
        """Start watching, unless this entry is not eligible or already done."""
        entry_id = self._entry.entry_id
        if not self._entry.data.get(CONF_FIRST_WEEK_HINT):
            return
        if entry_id in await _async_done_ids(self._hass):
            return
        self._active = True
        self._hass.data.setdefault(_HINTS_DATA_KEY, {})[entry_id] = self
        self._unsubs.append(self._coordinator.async_add_listener(self._handle_update))
        self._unsubs.append(
            async_call_later(self._hass, GRACE_PERIOD_SECONDS, self._handle_grace_over)
        )
        # Meals may already be there: mark done straight away in that case.
        await self.async_evaluate()

    @callback
    def async_stop(self) -> None:
        """Stop watching (entry unloaded, or the hint is done)."""
        self._active = False
        while self._unsubs:
            self._unsubs.pop()()
        hints: dict[str, FirstWeekHint] = self._hass.data.get(_HINTS_DATA_KEY, {})
        if hints.get(self._entry.entry_id) is self:
            hints.pop(self._entry.entry_id)

    @callback
    def _handle_update(self) -> None:
        if self._active:
            self._hass.async_create_task(self.async_evaluate())

    @callback
    def _handle_grace_over(self, _now: datetime) -> None:
        self._grace_over = True
        self._handle_update()

    async def async_evaluate(self) -> None:
        """Raise, keep, or clear the issue based on the current meal plan."""
        if not self._active or self._evaluating:
            return
        self._evaluating = True
        try:
            await self._async_evaluate()
        finally:
            self._evaluating = False

    async def _async_evaluate(self) -> None:
        entry_id = self._entry.entry_id
        if has_planned_meals(self._coordinator.data):
            await async_mark_first_week_done(self._hass, entry_id)
            return
        if (
            not self._grace_over
            or self._coordinator.data is None
            or not self._coordinator.last_update_success
        ):
            return
        if self._planned_before is None:
            self._planned_before = await self._async_planned_before()
            if self._planned_before is None:
                return
        if self._planned_before or has_planned_meals(self._coordinator.data):
            await async_mark_first_week_done(self._hass, entry_id)
            return
        if not self._active:
            return
        ir.async_create_issue(
            self._hass,
            domain=DOMAIN,
            issue_id=first_week_issue_id(entry_id),
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="plan_first_week",
            translation_placeholders={"planner_url": PLANNER_URL},
            learn_more_url=PLANNER_URL,
            data={"entry_id": entry_id},
        )

    async def _async_planned_before(self) -> bool | None:
        """Return True if the account has any meal in the last year.

        Returns None when the check could not be made, so it is retried on
        the next coordinator update instead of guessing.
        """
        today = dt_util.now().date()
        try:
            plans = await self._coordinator.client.async_get_meal_plans(
                today - timedelta(days=HISTORY_LOOKBACK_DAYS),
                today + timedelta(days=7),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("[culiplan][first_week] History check failed: %s", err)
            return None
        return has_planned_meals({"meal_plans": plans})
