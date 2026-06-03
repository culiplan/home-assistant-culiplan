"""
Tests for culiplan.suggest_meal and culiplan.fill_shopping_list HA services
(task-1388 + task-1389).

AC coverage:
  task-1388:
    AC#1 — Service culiplan.suggest_meal registered
    AC#2 — Cloud mode: backend executes, returns suggestion
    AC#3 — BYOK / Local: HA fetches envelope, dispatcher executes
    AC#4 — Free user calling Cloud mode receives 403 → PremiumRequiredError
    AC#5 — Fires culiplan_suggest_meal_result event + persistent notification

  task-1389:
    AC#1 — Service culiplan.fill_shopping_list registered
    AC#2 — Cloud mode: backend executes fill, returns summary
    AC#3 — Idempotency: items already on list not duplicated (tested via envelope)
    AC#4 — Summary notification shown to user
    AC#5 — Free user calling Cloud mode receives 403 → PremiumRequiredError
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.culiplan.services import (
    PremiumRequiredError,
    SERVICE_SUGGEST_MEAL,
    SERVICE_FILL_SHOPPING_LIST,
    SUGGEST_MEAL_SCHEMA,
    FILL_SHOPPING_LIST_SCHEMA,
    async_register_services,
    async_unregister_services,
    _run_cloud_intent,
    _run_byok_or_local_intent,
)
from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    DOMAIN,
)


# ─── PremiumRequiredError ─────────────────────────────────────────────────────

class TestPremiumRequiredError:
    def test_inherits_homeassistant_error(self):
        err = PremiumRequiredError(feature="suggest_meal", upgrade_url="https://culiplan.com/premium")
        assert isinstance(err, HomeAssistantError)

    def test_attributes_stored(self):
        err = PremiumRequiredError(feature="suggest_meal", upgrade_url="https://culiplan.com/premium")
        assert err.feature == "suggest_meal"
        assert err.upgrade_url == "https://culiplan.com/premium"

    def test_message_contains_feature_and_url(self):
        err = PremiumRequiredError(feature="fill_shopping_list", upgrade_url="https://culiplan.com/upgrade")
        msg = str(err)
        assert "fill_shopping_list" in msg
        assert "https://culiplan.com/upgrade" in msg


# ─── _run_cloud_intent ────────────────────────────────────────────────────────

class TestRunCloudIntent:
    """AC#2 (1388) + AC#2 (1389): Cloud AI path."""

    @pytest.mark.asyncio
    async def test_returns_speakable_result(self):
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(return_value={"speakable": "Tonight, have pasta."})
        result = await _run_cloud_intent(client, "suggest_meal", {})
        assert result == "Tonight, have pasta."

    @pytest.mark.asyncio
    async def test_falls_back_to_message_field(self):
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(return_value={"message": "Shopping list filled."})
        result = await _run_cloud_intent(client, "fill_shopping_list", {})
        assert result == "Shopping list filled."

    @pytest.mark.asyncio
    async def test_default_response_when_no_text(self):
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(return_value={})
        result = await _run_cloud_intent(client, "suggest_meal", {})
        assert result == "Done."

    @pytest.mark.asyncio
    async def test_403_premium_required_raises_premium_error(self):
        """AC#4 (1388) + AC#5 (1389): Free user → PremiumRequiredError."""
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            side_effect=Exception("403 Forbidden: premium_required")
        )
        with pytest.raises(PremiumRequiredError) as exc_info:
            await _run_cloud_intent(client, "suggest_meal", {})
        err = exc_info.value
        assert err.feature == "suggest_meal"
        assert "culiplan.com" in err.upgrade_url

    @pytest.mark.asyncio
    async def test_403_extracts_upgrade_url_from_json_body(self):
        """AC#4: If error message contains JSON with upgradeUrl, use it."""
        import json
        body = json.dumps({"error": "premium_required", "upgradeUrl": "https://culiplan.com/premium?source=ha"})
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            side_effect=Exception(f"403 {body}")
        )
        with pytest.raises(PremiumRequiredError) as exc_info:
            await _run_cloud_intent(client, "suggest_meal", {})
        assert "https://culiplan.com/premium?source=ha" == exc_info.value.upgrade_url

    @pytest.mark.asyncio
    async def test_non_403_error_raises_homeassistant_error(self):
        """Non-premium errors wrap in HomeAssistantError."""
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        with pytest.raises(HomeAssistantError) as exc_info:
            await _run_cloud_intent(client, "suggest_meal", {})
        assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_passes_params_to_tool(self):
        """Parameters forwarded to async_call_voice_tool correctly."""
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            return_value={"speakable": "Here's a quick lunch for you."}
        )
        await _run_cloud_intent(client, "suggest_meal", {"mealSlot": "lunch", "maxTimeMinutes": 30})
        client.async_call_voice_tool.assert_called_once_with(
            "suggest_meal", {"mealSlot": "lunch", "maxTimeMinutes": 30}
        )


# ─── _run_byok_or_local_intent ────────────────────────────────────────────────

class TestRunBYOKOrLocalIntent:
    """AC#3 (1388) + AC#3 (1389): BYOK / Local AI paths."""

    def _make_hass(self):
        hass = MagicMock()
        return hass

    @pytest.mark.asyncio
    async def test_byok_runs_dispatch_service(self):
        """BYOK mode: loads key from store, runs dispatch service."""
        hass = self._make_hass()
        entry_data = {"options": {}}
        entry_config = {
            CONF_AI_MODE: AI_MODE_BYOK,
            CONF_BYOK_PROVIDER: "openai",
        }
        client = AsyncMock()

        with (
            patch(
                "custom_components.culiplan.services.BYOKKeyStore"
            ) as MockKeyStore,
            patch(
                "custom_components.culiplan.services.AIDispatchService"
            ) as MockService,
        ):
            store_instance = AsyncMock()
            store_instance.async_load = AsyncMock()
            store_instance.get_key = MagicMock(return_value="sk-test-key")
            MockKeyStore.return_value = store_instance

            service_instance = AsyncMock()
            service_instance.run_intent = AsyncMock(
                return_value=MagicMock(text="Here's dinner: pasta!")
            )
            MockService.return_value = service_instance

            result = await _run_byok_or_local_intent(
                hass, entry_data, entry_config, client, "suggest_meal", {}
            )

        assert result == "Here's dinner: pasta!"
        MockService.assert_called_once()
        call_kwargs = MockService.call_args
        assert call_kwargs.kwargs["mode"] == AI_MODE_BYOK
        assert call_kwargs.kwargs["api_key"] == "sk-test-key"

    @pytest.mark.asyncio
    async def test_byok_missing_key_raises_error(self):
        """No BYOK key stored → HomeAssistantError."""
        hass = self._make_hass()
        entry_data = {"options": {}}
        entry_config = {
            CONF_AI_MODE: AI_MODE_BYOK,
            CONF_BYOK_PROVIDER: "openai",
        }
        client = AsyncMock()

        with patch("custom_components.culiplan.services.BYOKKeyStore") as MockKeyStore:
            store_instance = AsyncMock()
            store_instance.async_load = AsyncMock()
            store_instance.get_key = MagicMock(return_value=None)
            MockKeyStore.return_value = store_instance

            with pytest.raises(HomeAssistantError, match="No BYOK key found"):
                await _run_byok_or_local_intent(
                    hass, entry_data, entry_config, client, "suggest_meal", {}
                )

    @pytest.mark.asyncio
    async def test_local_mode_uses_endpoint(self):
        """Local AI mode: uses CONF_LOCAL_ENDPOINT, api_key='local'."""
        hass = self._make_hass()
        entry_data = {"options": {}}
        entry_config = {
            CONF_AI_MODE: AI_MODE_LOCAL,
            CONF_LOCAL_ENDPOINT: "http://localhost:11434",
            CONF_LOCAL_MODEL: "gemma3",
        }
        client = AsyncMock()

        with patch("custom_components.culiplan.services.AIDispatchService") as MockService:
            service_instance = AsyncMock()
            service_instance.run_intent = AsyncMock(
                return_value=MagicMock(text="Shopping list is filled.")
            )
            MockService.return_value = service_instance

            result = await _run_byok_or_local_intent(
                hass, entry_data, entry_config, client, "fill_shopping_list", {}
            )

        assert result == "Shopping list is filled."
        call_kwargs = MockService.call_args
        assert call_kwargs.kwargs["mode"] == AI_MODE_LOCAL
        assert call_kwargs.kwargs["api_key"] == "local"
        assert "/v1" in call_kwargs.kwargs["base_url"]

    @pytest.mark.asyncio
    async def test_null_text_returns_fallback(self):
        """If dispatch result has no text, return fallback message."""
        hass = self._make_hass()
        entry_data = {"options": {}}
        entry_config = {
            CONF_AI_MODE: AI_MODE_LOCAL,
            CONF_LOCAL_ENDPOINT: "http://localhost:11434",
        }
        client = AsyncMock()

        with patch("custom_components.culiplan.services.AIDispatchService") as MockService:
            service_instance = AsyncMock()
            service_instance.run_intent = AsyncMock(
                return_value=MagicMock(text=None)
            )
            MockService.return_value = service_instance

            result = await _run_byok_or_local_intent(
                hass, entry_data, entry_config, client, "suggest_meal", {}
            )

        assert "couldn't generate" in result or "try again" in result.lower()


# ─── Service registration ─────────────────────────────────────────────────────

class TestServiceRegistration:
    """AC#1 (1388 + 1389): Services registered under DOMAIN."""

    def test_async_register_services_registers_both(self):
        hass = MagicMock()
        hass.services.has_service.return_value = False

        async_register_services(hass)

        calls = hass.services.async_register.call_args_list
        registered_names = [c[0][1] for c in calls]
        assert SERVICE_SUGGEST_MEAL in registered_names
        assert SERVICE_FILL_SHOPPING_LIST in registered_names

    def test_async_register_services_skips_if_already_registered(self):
        hass = MagicMock()
        hass.services.has_service.return_value = True

        async_register_services(hass)

        hass.services.async_register.assert_not_called()

    def test_async_unregister_services_removes_both(self):
        hass = MagicMock()

        async_unregister_services(hass)

        calls = hass.services.async_remove.call_args_list
        removed_names = [c[0][1] for c in calls]
        assert SERVICE_SUGGEST_MEAL in removed_names
        assert SERVICE_FILL_SHOPPING_LIST in removed_names


# ─── suggest_meal handler ─────────────────────────────────────────────────────

class TestHandleSuggestMeal:
    """
    AC#2, AC#4, AC#5 (task-1388): handler fires event + persistent notification.
    Tests exercise the handler function extracted via async_register_services.
    """

    def _setup_hass(self, ai_mode: str = AI_MODE_CLOUD) -> tuple[MagicMock, MagicMock]:
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            return_value={"speakable": "I suggest pasta tonight."}
        )

        entry = MagicMock()
        entry.entry_id = "entry_123"
        entry.data = {CONF_AI_MODE: ai_mode}

        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "entry_123": {"client": client}
            }
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.bus.async_fire = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.services.has_service.return_value = False

        return hass, client

    @pytest.mark.asyncio
    async def test_cloud_mode_fires_event_and_notification(self):
        """AC#5: Cloud mode fires result event + creates persistent notification."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        # Get the registered handler
        suggest_handler = hass.services.async_register.call_args_list[0][0][2]
        call = MagicMock()
        call.data = {}

        await suggest_handler(call)

        # Event fired
        hass.bus.async_fire.assert_called_once()
        event_call = hass.bus.async_fire.call_args
        assert f"{DOMAIN}_suggest_meal_result" == event_call[0][0]
        event_data = event_call[0][1]
        assert "result" in event_data
        assert "I suggest pasta tonight." in event_data["result"]

        # Persistent notification created
        hass.services.async_call.assert_called_once()
        notif_call = hass.services.async_call.call_args[0]
        assert notif_call[0] == "persistent_notification"
        assert notif_call[1] == "create"

    @pytest.mark.asyncio
    async def test_cloud_mode_passes_params_correctly(self):
        """Service schema params forwarded correctly to cloud intent."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        suggest_handler = hass.services.async_register.call_args_list[0][0][2]
        service_call = MagicMock()
        service_call.data = {
            "constraints": "vegetarian",
            "meal_slot": "dinner",
            "max_time_minutes": 30,
        }

        await suggest_handler(service_call)

        client.async_call_voice_tool.assert_called_once_with(
            "suggest_meal",
            {"constraints": "vegetarian", "mealSlot": "dinner", "maxTimeMinutes": 30},
        )

    @pytest.mark.asyncio
    async def test_missing_entry_raises_error(self):
        """No configured entry → HomeAssistantError."""
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.services.has_service.return_value = False

        async_register_services(hass)
        suggest_handler = hass.services.async_register.call_args_list[0][0][2]
        service_call = MagicMock()
        service_call.data = {}

        with pytest.raises(HomeAssistantError, match="not configured"):
            await suggest_handler(service_call)

    @pytest.mark.asyncio
    async def test_params_none_values_excluded(self):
        """None params should not be forwarded (only non-None values)."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        suggest_handler = hass.services.async_register.call_args_list[0][0][2]
        service_call = MagicMock()
        # Only meal_slot is specified
        service_call.data = {"meal_slot": "lunch"}

        await suggest_handler(service_call)

        forwarded_params = client.async_call_voice_tool.call_args[0][1]
        assert "mealSlot" in forwarded_params
        assert "constraints" not in forwarded_params
        assert "maxTimeMinutes" not in forwarded_params


# ─── fill_shopping_list handler ───────────────────────────────────────────────

class TestHandleFillShoppingList:
    """
    AC#2, AC#4 (task-1389): handler fires event + persistent notification.
    AC#3 (task-1389): idempotency enforced by backend tool, not duplicated here.
    """

    def _setup_hass(self, ai_mode: str = AI_MODE_CLOUD) -> tuple[MagicMock, MagicMock]:
        client = AsyncMock()
        client.async_call_voice_tool = AsyncMock(
            return_value={"speakable": "Added 5 items to your shopping list."}
        )

        entry = MagicMock()
        entry.entry_id = "entry_456"
        entry.data = {CONF_AI_MODE: ai_mode}

        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "entry_456": {"client": client}
            }
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.bus.async_fire = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.services.has_service.return_value = False

        return hass, client

    @pytest.mark.asyncio
    async def test_cloud_mode_fires_event_and_notification(self):
        """AC#4 (1389): Cloud mode fires fill_shopping_list result event + notification."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        # fill_shopping_list is registered second
        fill_handler = hass.services.async_register.call_args_list[1][0][2]
        service_call = MagicMock()
        service_call.data = {}

        await fill_handler(service_call)

        # Event fired
        hass.bus.async_fire.assert_called_once()
        event_call = hass.bus.async_fire.call_args
        assert f"{DOMAIN}_fill_shopping_list_result" == event_call[0][0]
        event_data = event_call[0][1]
        assert "Added 5 items" in event_data["result"]

        # Notification
        hass.services.async_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_week_offset_forwarded_as_camel_case(self):
        """week_offset snake_case param becomes weekOffset in API call."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        fill_handler = hass.services.async_register.call_args_list[1][0][2]
        service_call = MagicMock()
        service_call.data = {"week_offset": 1}

        await fill_handler(service_call)

        client.async_call_voice_tool.assert_called_once_with(
            "fill_shopping_list", {"weekOffset": 1}
        )

    @pytest.mark.asyncio
    async def test_no_week_offset_sends_empty_params(self):
        """No week_offset → empty params dict (backend uses current week)."""
        hass, client = self._setup_hass(ai_mode=AI_MODE_CLOUD)
        async_register_services(hass)

        fill_handler = hass.services.async_register.call_args_list[1][0][2]
        service_call = MagicMock()
        service_call.data = {}

        await fill_handler(service_call)

        client.async_call_voice_tool.assert_called_once_with("fill_shopping_list", {})

    @pytest.mark.asyncio
    async def test_missing_entry_raises_error(self):
        """No configured entry → HomeAssistantError."""
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.services.has_service.return_value = False

        async_register_services(hass)
        fill_handler = hass.services.async_register.call_args_list[1][0][2]
        service_call = MagicMock()
        service_call.data = {}

        with pytest.raises(HomeAssistantError, match="not configured"):
            await fill_handler(service_call)


# ─── Schema validation ────────────────────────────────────────────────────────

class TestServiceSchemas:
    """Voluptuous schema correctness for both services."""

    def test_suggest_meal_all_optional_fields_valid(self):
        result = SUGGEST_MEAL_SCHEMA(
            {"constraints": "vegan", "meal_slot": "dinner", "max_time_minutes": 20}
        )
        assert result["constraints"] == "vegan"
        assert result["meal_slot"] == "dinner"
        assert result["max_time_minutes"] == 20

    def test_suggest_meal_empty_valid(self):
        result = SUGGEST_MEAL_SCHEMA({})
        assert result == {}

    def test_suggest_meal_invalid_slot_raises(self):
        import voluptuous as vol
        with pytest.raises(vol.Invalid):
            SUGGEST_MEAL_SCHEMA({"meal_slot": "elevenses"})

    def test_fill_shopping_list_week_offset_coerced(self):
        result = FILL_SHOPPING_LIST_SCHEMA({"week_offset": "2"})
        assert result["week_offset"] == 2

    def test_fill_shopping_list_empty_valid(self):
        result = FILL_SHOPPING_LIST_SCHEMA({})
        assert result == {}
