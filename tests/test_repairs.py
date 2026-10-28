"""
Tests for the Culiplan HA Repairs platform.

- "feature isn't available" issue (task-1395, reworded in v0.16.0: Culiplan is
  free, so no upgrade / billing wording and no upgrade link; it links to
  support instead).
- ``async_create_fix_flow`` (the repairs platform hook), including the
  first-week hint's fix flow.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from custom_components.culiplan.repairs import (
    FirstWeekRepairFlow,
    async_create_fix_flow,
    async_create_premium_repair,
    async_resolve_premium_repair,
    _repair_issue_id,
    _FEATURE_NAMES,
)
from custom_components.culiplan.services import (
    PremiumRequiredError,
    async_register_services,
)
from custom_components.culiplan.const import (
    AI_MODE_CLOUD,
    CONF_AI_MODE,
    DOMAIN,
    SUPPORT_URL,
)

_COMPONENT = Path(__file__).parent.parent / "custom_components" / "culiplan"


# ─── _repair_issue_id ─────────────────────────────────────────────────────────


class TestRepairIssueId:
    """Issue IDs are stable and safe for HA issue registry."""

    def test_dots_replaced_with_underscores(self):
        assert "." not in _repair_issue_id("ai.suggestion")

    def test_stable_output(self):
        assert _repair_issue_id("ai.suggestion") == _repair_issue_id("ai.suggestion")

    def test_unique_per_feature(self):
        assert _repair_issue_id("ai.suggestion") != _repair_issue_id("ai.shopping_fill")

    def test_prefix_is_neutral(self):
        assert _repair_issue_id("ai.suggestion").startswith("feature_unavailable_")


# ─── async_create_premium_repair (feature unavailable) ───────────────────────


class TestFeatureUnavailableRepair:
    """The 403 issue is neutral, non-fixable and links to support."""

    def _create(self, feature: str, url: str | None = "https://x/premium"):
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(hass, feature, url)
        mock_create.assert_called_once()
        return mock_create.call_args[1]

    def test_creates_non_fixable_issue(self):
        kwargs = self._create("ai.suggestion")
        assert kwargs["domain"] == DOMAIN
        assert kwargs["issue_id"] == _repair_issue_id("ai.suggestion")
        assert kwargs["is_fixable"] is False
        assert kwargs["translation_key"] == "feature_unavailable"

    def test_links_to_support_not_upgrade(self):
        kwargs = self._create("ai.suggestion", "https://culiplan.com/premium?x=1")
        assert kwargs["learn_more_url"] == SUPPORT_URL
        placeholders = kwargs["translation_placeholders"]
        assert placeholders["support_url"] == SUPPORT_URL
        assert "premium" not in json.dumps(placeholders).lower()

    def test_known_feature_gets_human_name(self):
        kwargs = self._create("ai.shopping_fill")
        assert kwargs["translation_placeholders"]["feature"] == "AI shopping list fill"

    def test_unknown_feature_falls_back_to_id(self):
        kwargs = self._create("some.unknown_feature", None)
        assert kwargs["translation_placeholders"]["feature"] == "some.unknown_feature"

    def test_feature_names_have_no_tier_wording(self):
        for name in _FEATURE_NAMES.values():
            assert "premium" not in name.lower()


# ─── Copy guard: no tier / upgrade wording anywhere user-facing ──────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "strings.json",
        "services.yaml",
        "translations/en.json",
        "translations/de.json",
        "translations/es.json",
        "translations/fr.json",
        "translations/nl.json",
    ],
)
def test_no_premium_or_upgrade_wording_in_copy(rel_path):
    text = (_COMPONENT / rel_path).read_text(encoding="utf-8").lower()
    for word in ("premium", "upgrade", "billing", "free tier", "abonnement", "suscrip"):
        assert word not in text, f"{word!r} found in {rel_path}"


def test_premium_required_error_message_is_neutral():
    err = PremiumRequiredError("ai.suggestion", "https://culiplan.com/premium")
    assert "premium" not in str(err).lower()
    assert "isn't available" in str(err)


# ─── async_resolve_premium_repair ────────────────────────────────────────────


class TestAsyncResolvePremiumRepair:
    """Repair auto-resolves on next successful call."""

    def test_deletes_issue_for_feature(self):
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.repairs.ir.async_delete_issue"
        ) as mock_delete:
            async_resolve_premium_repair(hass, "ai.suggestion")
            mock_delete.assert_called_once_with(
                hass, DOMAIN, _repair_issue_id("ai.suggestion")
            )

    def test_safe_when_no_issue_exists(self):
        hass = MagicMock()
        with patch("custom_components.culiplan.repairs.ir.async_delete_issue"):
            async_resolve_premium_repair(hass, "ai.suggestion")


# ─── async_create_fix_flow (repairs platform) ────────────────────────────────


@pytest.mark.asyncio
async def test_fix_flow_for_first_week_issue(hass):
    flow = await async_create_fix_flow(hass, "plan_first_week_entry123", None)
    assert isinstance(flow, FirstWeekRepairFlow)
    assert flow._entry_id == "entry123"


@pytest.mark.asyncio
async def test_fix_flow_for_other_issue_is_plain_confirm(hass):
    from homeassistant.components.repairs import ConfirmRepairFlow

    flow = await async_create_fix_flow(hass, "pantry_barcode_not_found_123", None)
    assert type(flow) is ConfirmRepairFlow


@pytest.mark.asyncio
async def test_first_week_fix_flow_submit_marks_done(hass):
    flow = FirstWeekRepairFlow("entry123")
    flow.hass = hass
    flow.handler = DOMAIN
    flow.issue_id = "plan_first_week_entry123"
    flow.flow_id = "abc"

    with patch(
        "custom_components.culiplan.first_week.async_mark_first_week_done",
        AsyncMock(),
    ) as mock_done:
        shown = await flow.async_step_init()
        assert shown["step_id"] == "confirm"
        mock_done.assert_not_called()

        result = await flow.async_step_confirm({})
    mock_done.assert_awaited_once_with(hass, "entry123")
    assert result["type"] == "create_entry"


# ─── Integration with services.py ────────────────────────────────────────────


class TestServicesRepairIntegration:
    """
    AC#5: Stub 403 from backend and confirm HA Repairs issue is created.
    Tests the full flow: service call → 403 → PremiumRequiredError → Repairs issue.
    """

    def _setup_hass_with_cloud_mode(self) -> tuple[MagicMock, MagicMock]:
        """Set up a mock hass with Cloud AI mode and a client that returns 403.

        api.py now parses the 403 envelope and raises a typed
        ``PremiumRequiredError`` directly (task-1416 — no more string
        parsing in services.py). The mock raises the typed error so the
        end-to-end behaviour matches what the real client does.
        """
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            side_effect=PremiumRequiredError(
                feature="ai.suggestion",
                upgrade_url=(
                    "https://culiplan.com/settings/billing?ref=ha_gate&client=ha-core"
                ),
            )
        )

        entry = MagicMock()
        entry.entry_id = "entry_test"
        entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

        hass = MagicMock()
        hass.data = {
            DOMAIN: {"entry_test": {"client": client}},
            "core.uuid": "ha-test-uuid",
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.bus.async_fire = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.services.has_service.return_value = False

        return hass, client

    @pytest.mark.asyncio
    async def test_403_creates_repairs_issue(self):
        """AC#5: 403 from backend creates a Repairs issue via async_create_premium_repair."""
        hass, client = self._setup_hass_with_cloud_mode()

        with patch(
            "custom_components.culiplan.services.async_create_premium_repair"
        ) as mock_create_repair:
            async_register_services(hass)
            suggest_handler = hass.services.async_register.call_args_list[0][0][2]
            service_call = MagicMock()
            service_call.data = {}

            with pytest.raises(PremiumRequiredError):
                await suggest_handler(service_call)

            mock_create_repair.assert_called_once()
            call_args = mock_create_repair.call_args
            # hass is first positional arg
            assert call_args[0][0] is hass
            # feature from 403 body
            assert call_args[0][1] == "ai.suggestion"
            # upgrade_url from 403 body
            assert "culiplan.com" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_success_resolves_repairs_issue(self):
        """AC#4: Successful call after upgrade resolves the Repairs issue."""
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            return_value={"speakable": "Have pasta tonight!"}
        )

        entry = MagicMock()
        entry.entry_id = "entry_success"
        entry.data = {CONF_AI_MODE: AI_MODE_CLOUD}

        hass = MagicMock()
        hass.data = {
            DOMAIN: {"entry_success": {"client": client}},
            "core.uuid": "ha-test-uuid",
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.bus.async_fire = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.culiplan.services.async_resolve_premium_repair"
        ) as mock_resolve:
            async_register_services(hass)
            suggest_handler = hass.services.async_register.call_args_list[0][0][2]
            service_call = MagicMock()
            service_call.data = {}

            await suggest_handler(service_call)

            # AC#4: resolve called after success
            mock_resolve.assert_called_once_with(hass, "ai.suggestion")

    @pytest.mark.asyncio
    async def test_403_does_not_create_notification(self):
        """Premium errors should not create success notifications."""
        hass, client = self._setup_hass_with_cloud_mode()

        with patch("custom_components.culiplan.services.async_create_premium_repair"):
            async_register_services(hass)
            suggest_handler = hass.services.async_register.call_args_list[0][0][2]
            service_call = MagicMock()
            service_call.data = {}

            with pytest.raises(PremiumRequiredError):
                await suggest_handler(service_call)

        # persistent_notification should NOT have been called (error raised before it)
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_fill_shopping_list_403_creates_repairs_issue(self):
        """AC#5: fill_shopping_list 403 also creates a Repairs issue."""
        hass, client = self._setup_hass_with_cloud_mode()

        with patch(
            "custom_components.culiplan.services.async_create_premium_repair"
        ) as mock_create_repair:
            async_register_services(hass)
            fill_handler = hass.services.async_register.call_args_list[1][0][2]
            service_call = MagicMock()
            service_call.data = {}

            with pytest.raises(PremiumRequiredError):
                await fill_handler(service_call)

            mock_create_repair.assert_called_once()
