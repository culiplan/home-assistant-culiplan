"""
Culiplan HA Repairs: "feature unavailable" notices + the first-week hint.

Two kinds of issues live here:

1. ``feature_unavailable_<feature>`` (task-1395, reworded in v0.16.0).
   When the backend answers a call with a structured 403
   ``{error: 'premium_required', feature, ...}``, the integration raises a
   non-fixable Repairs issue that says the feature isn't available for the
   account and links to Culiplan support. Culiplan is free, so there is no
   upgrade path to offer; the backend's ``upgradeUrl`` is ignored. The issue
   auto-resolves on the next successful call to the same feature
   (``async_resolve_premium_repair``).

   Architecture note (§11.1.5): feature availability is decided EXCLUSIVELY
   on the backend. The integration never hardcodes it; it only reacts to the
   403.

2. ``plan_first_week_<entry_id>`` (v0.16.0, see ``first_week.py``).
   A fixable issue shown once to brand-new installs whose Culiplan account
   has no meals planned. The fix flow is a simple confirm step; finishing it
   records the hint as done so it never comes back.

This module is also HA's ``repairs`` platform for the integration, so it must
expose ``async_create_fix_flow``.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, SUPPORT_URL

_LOGGER = logging.getLogger(__name__)

FEATURE_UNAVAILABLE_PREFIX = "feature_unavailable_"
FIRST_WEEK_ISSUE_PREFIX = "plan_first_week_"

# ─── Feature id → human-readable name ────────────────────────────────────────

_FEATURE_NAMES: dict[str, str] = {
    "ai.suggestion": "AI meal suggestions",
    "ai.shopping_fill": "AI shopping list fill",
    "ai.blueprint": "AI automation blueprints",
    "cooking_mode": "Guided cooking mode",
    "smart_appliance": "Smart appliance integration",
    "recipe_image_gen": "Recipe image generation",
    "smart_pantry": "Smart pantry recommendations",
    "household.presence_scaling": "Presence-based serving scaling",
}


def _feature_name(feature: str) -> str:
    return _FEATURE_NAMES.get(feature, feature)


# ─── Issue ID helpers ──────────────────────────────────────────────────────────


def _repair_issue_id(feature: str) -> str:
    """Unique repair issue ID per feature (stable across HA restarts)."""
    # Replace dots/slashes with underscores to satisfy HA issue-id conventions
    safe_feature = feature.replace(".", "_").replace("/", "_").replace(" ", "_")
    return f"{FEATURE_UNAVAILABLE_PREFIX}{safe_feature}"


# ─── Public API: feature unavailable ──────────────────────────────────────────


def async_create_premium_repair(
    hass: HomeAssistant,
    feature: str,
    upgrade_url: str | None = None,
) -> None:
    """Create (or update) a "feature isn't available" Repairs issue.

    Called whenever the backend returns a 403 for a gated feature.
    Idempotent: calling it again for the same feature updates the existing
    issue instead of creating a duplicate.

    Args:
        hass:        HomeAssistant instance.
        feature:     Machine-readable feature id from the 403 body
                     (e.g. "ai.suggestion").
        upgrade_url: Ignored. Kept so callers that pass the 403's
                     ``upgradeUrl`` keep working; Culiplan has no paid tier,
                     so the issue links to support instead.
    """
    del upgrade_url  # Culiplan is free: there is nothing to upgrade to.
    issue_id = _repair_issue_id(feature)

    _LOGGER.info(
        "[culiplan] Feature '%s' is not available for this account (issue_id=%s)",
        feature,
        issue_id,
    )

    # HA 2025.4+ removed the ``is_persistent`` kwarg from async_create_issue
    # (default is False, which is what we want: the issue resolves on the
    # next successful call, not on HA restart). Don't pass it.
    ir.async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="feature_unavailable",
        translation_placeholders={
            "feature": _feature_name(feature),
            "support_url": SUPPORT_URL,
        },
        learn_more_url=SUPPORT_URL,
    )


def async_resolve_premium_repair(
    hass: HomeAssistant,
    feature: str,
) -> None:
    """Remove the "feature isn't available" issue for a feature.

    Safe to call even if no issue exists for the feature.
    """
    issue_id = _repair_issue_id(feature)

    _LOGGER.debug(
        "[culiplan] Resolving feature-unavailable issue for '%s' (issue_id=%s)",
        feature,
        issue_id,
    )

    ir.async_delete_issue(hass, DOMAIN, issue_id)


# ─── Repairs platform: fix flows ─────────────────────────────────────────────


class FirstWeekRepairFlow(ConfirmRepairFlow):
    """Confirm step for the "Plan your first week" hint.

    Submitting it records the hint as done for this entry, so it is never
    shown again even if the meal plan is still empty (no nagging).
    """

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self._entry_id = entry_id

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> Any:
        """Show the hint; on submit, record it as done and close the issue."""
        if user_input is not None:
            from .first_week import async_mark_first_week_done  # noqa: PLC0415

            await async_mark_first_week_done(self.hass, self._entry_id)
        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a fixable Culiplan issue."""
    if issue_id.startswith(FIRST_WEEK_ISSUE_PREFIX):
        return FirstWeekRepairFlow(issue_id.removeprefix(FIRST_WEEK_ISSUE_PREFIX))
    return ConfirmRepairFlow()
