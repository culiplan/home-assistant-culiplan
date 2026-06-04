"""
Tests for the Culiplan HA Repairs UI — premium upsell deep-link (task-1395).

AC coverage:
  AC#1 — Repairs flow registered: parses {feature, upgradeUrl} from 403 body.
  AC#2 — Repair issue copy is plain language.
  AC#3 — Action button opens upgradeUrl in browser; URL includes ha_install_id.
  AC#4 — Repair auto-resolves on next successful call.
  AC#5 — Tested by stubbing 403 from backend (via PremiumRequiredError in services).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.culiplan.repairs import (
    async_create_premium_repair,
    async_resolve_premium_repair,
    _repair_issue_id,
    _append_ha_install_id,
    _FEATURE_TITLES,
    _FEATURE_DESCRIPTIONS,
)
from custom_components.culiplan.services import (
    PremiumRequiredError,
    async_register_services,
    SUGGEST_MEAL_SCHEMA,
)
from custom_components.culiplan.const import (
    AI_MODE_CLOUD,
    CONF_AI_MODE,
    DOMAIN,
)


# ─── _repair_issue_id ─────────────────────────────────────────────────────────

class TestRepairIssueId:
    """Issue IDs are stable and safe for HA issue registry."""

    def test_dots_replaced_with_underscores(self):
        assert "." not in _repair_issue_id("ai.suggestion")

    def test_stable_output(self):
        assert _repair_issue_id("ai.suggestion") == _repair_issue_id("ai.suggestion")

    def test_unique_per_feature(self):
        assert _repair_issue_id("ai.suggestion") != _repair_issue_id("ai.shopping_fill")

    def test_prefix_matches_domain(self):
        assert _repair_issue_id("ai.suggestion").startswith("premium_required_")


# ─── _append_ha_install_id ────────────────────────────────────────────────────

class TestAppendHaInstallId:
    """AC#3: ha_install_id is appended to upgradeUrl."""

    def _make_hass(self, ha_id: str = "test-ha-uuid-1234") -> MagicMock:
        hass = MagicMock()
        hass.data = {"core.uuid": ha_id}
        return hass

    def test_appends_ha_install_id_to_clean_url(self):
        hass = self._make_hass("my-ha-id")
        result = _append_ha_install_id("https://culiplan.com/premium?ref=ha_gate", hass)
        assert "ha_install_id=my-ha-id" in result

    def test_appends_ha_install_id_to_url_without_params(self):
        hass = self._make_hass("my-ha-id")
        result = _append_ha_install_id("https://culiplan.com/premium", hass)
        assert "ha_install_id=my-ha-id" in result
        assert "?" in result

    def test_does_not_duplicate_ha_install_id(self):
        hass = self._make_hass("my-ha-id")
        url_with_id = "https://culiplan.com/premium?ha_install_id=existing-id"
        result = _append_ha_install_id(url_with_id, hass)
        assert result.count("ha_install_id=") == 1

    def test_no_ha_id_returns_original_url(self):
        hass = MagicMock()
        hass.data = {}
        url = "https://culiplan.com/premium?ref=ha_gate"
        result = _append_ha_install_id(url, hass)
        assert result == url

    def test_exception_in_hass_data_returns_original_url(self):
        hass = MagicMock()
        # Make hass.data.get raise to simulate edge case
        hass.data = MagicMock()
        hass.data.get.side_effect = RuntimeError("unexpected")
        url = "https://culiplan.com/premium"
        result = _append_ha_install_id(url, hass)
        assert result == url


# ─── async_create_premium_repair ─────────────────────────────────────────────

class TestAsyncCreatePremiumRepair:
    """AC#1, AC#2, AC#3: issue is created with correct copy and upgrade URL."""

    def _make_hass(self) -> MagicMock:
        hass = MagicMock()
        hass.data = {"core.uuid": "test-uuid-abc"}
        return hass

    def test_creates_issue_for_ai_suggestion(self):
        hass = self._make_hass()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(
                hass, "ai.suggestion", "https://culiplan.com/premium?ref=ha_gate"
            )
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["domain"] == DOMAIN
            assert call_kwargs["issue_id"] == _repair_issue_id("ai.suggestion")
            assert call_kwargs["is_fixable"] is True

    def test_issue_title_is_plain_language(self):
        """AC#2: Issue copy is human-readable, not machine-readable."""
        hass = self._make_hass()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(
                hass, "ai.suggestion", "https://culiplan.com/premium?ref=ha_gate"
            )
            placeholders = mock_create.call_args[1]["translation_placeholders"]
            title = placeholders["title"]
            # Must be human-readable (not the raw feature key)
            assert "Premium" in title
            assert "AI" in title

    def test_upgrade_url_includes_ha_install_id(self):
        """AC#3: upgrade_url in placeholders contains ha_install_id."""
        hass = self._make_hass()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(
                hass, "ai.suggestion", "https://culiplan.com/premium?ref=ha_gate"
            )
            placeholders = mock_create.call_args[1]["translation_placeholders"]
            upgrade_url = placeholders["upgrade_url"]
            assert "ha_install_id=test-uuid-abc" in upgrade_url

    def test_learn_more_url_set_to_upgrade_url(self):
        """AC#3: learn_more_url is the billing deep-link."""
        hass = self._make_hass()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(
                hass, "ai.suggestion", "https://culiplan.com/premium?ref=ha_gate"
            )
            learn_url = mock_create.call_args[1]["learn_more_url"]
            assert "culiplan.com" in learn_url

    def test_unknown_feature_uses_fallback_copy(self):
        """AC#2: Unknown features get reasonable fallback copy."""
        hass = self._make_hass()
        with patch(
            "custom_components.culiplan.repairs.ir.async_create_issue"
        ) as mock_create:
            async_create_premium_repair(
                hass, "some.unknown_feature", "https://culiplan.com/premium"
            )
            placeholders = mock_create.call_args[1]["translation_placeholders"]
            title = placeholders["title"]
            assert "Premium" in title

    def test_all_known_features_have_human_copy(self):
        """AC#2: All documented features have dedicated copy."""
        known_features = list(_FEATURE_TITLES.keys())
        assert len(known_features) >= 2  # At minimum ai.suggestion and ai.shopping_fill
        for feature in known_features:
            assert len(_FEATURE_TITLES[feature]) > 10
            assert len(_FEATURE_DESCRIPTIONS.get(feature, "")) > 20

    def test_fill_shopping_list_feature_has_copy(self):
        """AC#2: fill_shopping_list feature has plain language copy."""
        assert "ai.shopping_fill" in _FEATURE_TITLES
        title = _FEATURE_TITLES["ai.shopping_fill"]
        assert "shopping" in title.lower() or "list" in title.lower()


# ─── async_resolve_premium_repair ────────────────────────────────────────────

class TestAsyncResolvePremiumRepair:
    """AC#4: Repair auto-resolves on next successful call."""

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
        """AC#4: Resolving a non-existent issue should not raise."""
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.repairs.ir.async_delete_issue"
        ):
            # Should not raise
            async_resolve_premium_repair(hass, "ai.suggestion")


# ─── Integration with services.py ────────────────────────────────────────────

class TestServicesRepairIntegration:
    """
    AC#5: Stub 403 from backend and confirm HA Repairs issue is created.
    Tests the full flow: service call → 403 → PremiumRequiredError → Repairs issue.
    """

    def _setup_hass_with_cloud_mode(self) -> tuple[MagicMock, MagicMock]:
        """Set up a mock hass with Cloud AI mode and a client that returns 403."""
        client = AsyncMock()
        # Simulate 403 premium_required from backend
        import json
        body = json.dumps({
            "error": "premium_required",
            "feature": "ai.suggestion",
            "upgradeUrl": "https://culiplan.com/settings/billing?ref=ha_gate&client=ha-core",
        })
        client.async_call_voice_tool = AsyncMock(
            side_effect=Exception(f"403 {body}")
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
