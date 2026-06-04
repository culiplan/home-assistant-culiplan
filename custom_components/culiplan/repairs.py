"""
Culiplan HA Repairs UI — premium upsell deep-link (task-1395).

When the Culiplan backend returns a 403 {error: 'premium_required', feature, upgradeUrl}
response, the integration creates a HA Repairs issue that:

  1. Shows a plain-language title and description for the blocked feature.
  2. Offers an 'Upgrade on Culiplan' action that opens upgradeUrl in the user's
     browser, with an `ha_install_id` query parameter so the billing page can
     identify the install.
  3. Auto-resolves when the same feature call succeeds (caller invokes
     async_resolve_premium_repair()).

Architecture note (§11.1.5):
  - Tier enforcement lives EXCLUSIVELY on the backend.
  - The integration never hardcodes feature availability; it only parses the 403
    response and surfaces the repair issue.
  - upgradeUrl comes from the backend; we only append ha_install_id.

AC#1 — Repairs flow registered: parses {feature, upgradeUrl} from 403 body.
AC#2 — Repair issue copy is plain language.
AC#3 — Action button opens upgradeUrl in browser with ha_install_id param.
AC#4 — Repair auto-resolves on next successful call to the same feature.
AC#5 — Tested by stubbing 403 from backend.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse, parse_qs

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ─── Feature-to-human-readable copy ───────────────────────────────────────────

_FEATURE_TITLES: dict[str, str] = {
    "ai.suggestion": "AI meal suggestions need Culiplan Premium",
    "ai.shopping_fill": "AI shopping list fill needs Culiplan Premium",
    "ai.blueprint": "AI automation blueprints need Culiplan Premium",
    "cooking_mode": "Guided cooking mode needs Culiplan Premium",
    "smart_appliance": "Smart appliance integration needs Culiplan Premium",
    "recipe_image_gen": "Recipe image generation needs Culiplan Premium",
    "smart_pantry": "Smart pantry recommendations need Culiplan Premium",
}

_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "ai.suggestion": (
        "You asked Culiplan for an AI meal suggestion, but this feature requires "
        "a Culiplan Premium subscription. Upgrade to unlock AI-powered meal ideas "
        "in Home Assistant."
    ),
    "ai.shopping_fill": (
        "You asked Culiplan to fill your shopping list automatically, but this feature "
        "requires a Culiplan Premium subscription. Upgrade to let AI handle your "
        "grocery planning."
    ),
    "ai.blueprint": (
        "AI-composed Home Assistant automation blueprints require a Culiplan Premium "
        "subscription. Upgrade to create custom kitchen automations with AI."
    ),
    "cooking_mode": (
        "Guided step-by-step voice cooking mode requires a Culiplan Premium "
        "subscription. Upgrade to get hands-free cooking guidance in Home Assistant."
    ),
    "smart_appliance": (
        "Smart appliance integration requires a Culiplan Premium subscription. "
        "Upgrade to connect your kitchen appliances."
    ),
    "recipe_image_gen": (
        "Recipe image generation requires a Culiplan Premium subscription."
    ),
    "smart_pantry": (
        "Smart pantry recommendations require a Culiplan Premium subscription."
    ),
}


def _default_title(feature: str) -> str:
    return f"'{feature}' requires Culiplan Premium"


def _default_description(feature: str) -> str:
    return (
        f"The feature '{feature}' requires a Culiplan Premium subscription. "
        "Upgrade to unlock this capability in Home Assistant."
    )


# ─── Issue ID helpers ──────────────────────────────────────────────────────────


def _repair_issue_id(feature: str) -> str:
    """Unique repair issue ID per feature (stable across HA restarts)."""
    # Replace dots/slashes with underscores to satisfy HA issue-id conventions
    safe_feature = feature.replace(".", "_").replace("/", "_").replace(" ", "_")
    return f"premium_required_{safe_feature}"


# ─── URL helper ───────────────────────────────────────────────────────────────


def _append_ha_install_id(upgrade_url: str, hass: HomeAssistant) -> str:
    """
    Append ha_install_id to the upgrade URL so the Culiplan billing page
    can identify the Home Assistant install and show context-aware messaging.

    Uses hass.data["core.uuid"] if available (set by HA core since 2022.6);
    falls back to an empty string which still opens the billing page.
    """
    try:
        ha_id = str(hass.data.get("core.uuid", ""))
    except Exception:
        ha_id = ""

    if not ha_id:
        return upgrade_url

    parsed = urlparse(upgrade_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)

    # Only append if not already present
    if "ha_install_id" not in existing_params:
        separator = "&" if parsed.query else "?"
        upgrade_url = f"{upgrade_url}{separator}ha_install_id={ha_id}"

    return upgrade_url


# ─── Public API ───────────────────────────────────────────────────────────────


def async_create_premium_repair(
    hass: HomeAssistant,
    feature: str,
    upgrade_url: str,
) -> None:
    """
    Create (or update) a HA Repairs issue for a premium-gated feature.

    Called whenever the backend returns 403 premium_required.
    Idempotent: calling multiple times for the same feature updates
    the existing issue rather than creating duplicates (AC#1).

    Args:
        hass:         HomeAssistant instance.
        feature:      Machine-readable feature id from the 403 body
                      (e.g. "ai.suggestion").
        upgrade_url:  Billing deep-link from the 403 body.
    """
    issue_id = _repair_issue_id(feature)
    title = _FEATURE_TITLES.get(feature, _default_title(feature))
    description = _FEATURE_DESCRIPTIONS.get(feature, _default_description(feature))

    # Append HA install id for billing-page UX (AC#3)
    full_upgrade_url = _append_ha_install_id(upgrade_url, hass)

    _LOGGER.info(
        "[culiplan] Creating premium repair issue for feature '%s' (issue_id=%s)",
        feature,
        issue_id,
    )

    ir.async_create_issue(
        hass,
        domain=DOMAIN,
        issue_id=issue_id,
        is_fixable=True,
        is_persistent=False,  # Resolves when user upgrades (not on HA restart)
        severity=ir.IssueSeverity.WARNING,
        translation_key="premium_required",
        translation_placeholders={
            "feature": feature,
            "title": title,
            "description": description,
            "upgrade_url": full_upgrade_url,
        },
        learn_more_url=full_upgrade_url,
    )


def async_resolve_premium_repair(
    hass: HomeAssistant,
    feature: str,
) -> None:
    """
    Remove the premium repair issue for a feature (AC#4 — auto-resolve on
    next successful call after upgrading).

    Safe to call even if no issue exists for the feature.

    Args:
        hass:    HomeAssistant instance.
        feature: Machine-readable feature id (e.g. "ai.suggestion").
    """
    issue_id = _repair_issue_id(feature)

    _LOGGER.debug(
        "[culiplan] Resolving premium repair issue for feature '%s' (issue_id=%s)",
        feature,
        issue_id,
    )

    ir.async_delete_issue(hass, DOMAIN, issue_id)
