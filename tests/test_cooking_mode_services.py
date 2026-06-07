"""
Tests for Culiplan cooking-mode HA services (task-1397).

AC coverage:
  AC#1 — Seven services registered with proper schemas
  AC#2 — Service calls update the backend session and reflect in HA via event channel
  AC#3 — HA timer entity created per session.timers[] entry; cancellation propagates
  AC#4 — Voice 'next step' / 'start the pasta timer' work via HA Assist (intent handler)
  AC#5 — Cross-surface handoff tested via mock active-session fetch
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.culiplan.cooking_services import (
    COOKING_SERVICES,
    async_register_cooking_services,
    async_unregister_cooking_services,
    _timer_entity_id,
    sync_ha_timers,
)
from custom_components.culiplan.const import DOMAIN

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_hass(entry_id: str = "test_entry_id") -> MagicMock:
    """Build a minimal hass mock with service registry."""
    hass = MagicMock()
    hass.data = {DOMAIN: {entry_id: {"client": None}}}  # client patched per test
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    # Minimal service registry: has_service → False so all register calls go through
    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register = MagicMock()
    hass.services.async_remove = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _make_session(
    session_id: str = "sess_abc12345",
    current_step: int = 1,
    total_steps: int = 5,
    status: str = "active",
    timers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": session_id,
        "recipeId": "recipe_001",
        "servings": 4,
        "currentStep": current_step,
        "totalSteps": total_steps,
        "status": status,
        "timers": timers or [],
    }


def _make_client(
    session: dict[str, Any] | None = None,
    session_list: list[dict[str, Any]] | None = None,
    post_return: dict[str, Any] | None = None,
    patch_return: dict[str, Any] | None = None,
) -> AsyncMock:
    client = AsyncMock()
    # GET /api/cooking-sessions?status=active&limit=1
    default_session = session or _make_session()
    client.async_get.return_value = (
        session_list if session_list is not None else [default_session]
    )
    client.async_post.return_value = post_return or default_session
    client._patch = AsyncMock(return_value=patch_return or default_session)
    return client


# ─── Unit helpers ─────────────────────────────────────────────────────────────


class TestTimerEntityId:
    def test_basic_label(self) -> None:
        # Session ID is truncated to 8 chars and slugified; "session_id_abc"[:8]
        # is "session_" which collapses to "session" after the trailing
        # underscore is stripped.
        eid = _timer_entity_id("session_id_abc", "pasta")
        assert eid == "timer.culiplan_session_session_pasta"

    def test_label_normalisation(self) -> None:
        eid = _timer_entity_id("session_id_abc", "Sauce Reduce")
        assert eid == "timer.culiplan_session_session_sauce_reduce"

    def test_short_session_id(self) -> None:
        eid = _timer_entity_id("s1", "pasta")
        assert eid == "timer.culiplan_session_s1_pasta"

    def test_special_chars_stripped(self) -> None:
        eid = _timer_entity_id("abc12345def", "garlic & herb")
        assert "garlic" in eid
        assert "herb" in eid
        assert "&" not in eid


# ─── Service registration ─────────────────────────────────────────────────────


class TestServiceRegistration:
    def test_all_seven_registered(self) -> None:
        hass = _make_hass()
        async_register_cooking_services(hass)
        assert hass.services.async_register.call_count == len(COOKING_SERVICES)
        registered_names = {
            c[0][1]  # positional arg: service name
            for c in hass.services.async_register.call_args_list
        }
        assert registered_names == set(COOKING_SERVICES)

    def test_idempotent_registration(self) -> None:
        hass = _make_hass()
        hass.services.has_service.return_value = True  # already registered
        async_register_cooking_services(hass)
        hass.services.async_register.assert_not_called()

    def test_unregister_removes_all(self) -> None:
        hass = _make_hass()
        hass.services.has_service.return_value = True
        async_unregister_cooking_services(hass)
        assert hass.services.async_remove.call_count == len(COOKING_SERVICES)


# ─── start_cooking_mode ───────────────────────────────────────────────────────


class TestStartCookingMode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_post(self) -> None:
        session = _make_session()
        client = _make_client(post_return=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = hass.services.async_register.call_args_list[0][0][2]

        call_obj = MagicMock()
        call_obj.data = {"recipe_id": "recipe_001", "servings": 4}
        await handler(call_obj)

        client.async_post.assert_awaited_once_with(
            "/api/cooking-sessions",
            {"recipeId": "recipe_001", "servings": 4},
        )

    @pytest.mark.asyncio
    async def test_fires_event_on_success(self) -> None:
        session = _make_session()
        client = _make_client(post_return=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = hass.services.async_register.call_args_list[0][0][2]

        call_obj = MagicMock()
        call_obj.data = {"recipe_id": "recipe_001"}
        await handler(call_obj)

        hass.bus.async_fire.assert_called_once()
        event_type = hass.bus.async_fire.call_args[0][0]
        assert event_type == f"{DOMAIN}_cooking_session_started"

    @pytest.mark.asyncio
    async def test_premium_required_creates_repair(self) -> None:
        from custom_components.culiplan.ai.types import PremiumRequiredError

        client = _make_client()
        client.async_post.side_effect = PremiumRequiredError(
            feature="cooking_mode",
            upgrade_url="https://culiplan.com/premium?source=ha",
        )
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        with patch(
            "custom_components.culiplan.cooking_services.async_create_premium_repair"
        ) as mock_repair:
            async_register_cooking_services(hass)
            handler = hass.services.async_register.call_args_list[0][0][2]
            call_obj = MagicMock()
            call_obj.data = {"recipe_id": "recipe_001"}

            with pytest.raises(PremiumRequiredError):
                await handler(call_obj)

            mock_repair.assert_called_once()
            repair_args = mock_repair.call_args[0]
            assert repair_args[1] == "cooking_mode"  # feature


# ─── advance_cooking_step ─────────────────────────────────────────────────────


class TestAdvanceCookingStep:
    def _get_handler(self, hass: MagicMock) -> Any:
        """Return the second registered handler (advance_cooking_step)."""
        return hass.services.async_register.call_args_list[1][0][2]

    @pytest.mark.asyncio
    async def test_advances_step(self) -> None:
        session = _make_session(current_step=1, total_steps=5)
        updated_session = dict(session, currentStep=2)
        client = _make_client(session=session, patch_return=updated_session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {}
        await handler(call_obj)

        client._patch.assert_awaited_once_with(
            f"/api/cooking-sessions/{session['id']}",
            {"currentStep": 2},
        )

    @pytest.mark.asyncio
    async def test_fires_step_advanced_event(self) -> None:
        session = _make_session(current_step=2, total_steps=5)
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {}
        await handler(call_obj)

        event_type = hass.bus.async_fire.call_args[0][0]
        assert event_type == f"{DOMAIN}_cooking_step_advanced"

    @pytest.mark.asyncio
    async def test_raises_on_last_step(self) -> None:
        session = _make_session(current_step=4, total_steps=5)
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {}
        with pytest.raises(HomeAssistantError) as excinfo:
            await handler(call_obj)
        # Error surfaces via translation_key (HA-canonical pattern); message
        # text is locale-dependent and not available in unit tests.
        assert getattr(excinfo.value, "translation_key", "") == (
            "cooking_already_last_step"
        )

    @pytest.mark.asyncio
    async def test_raises_when_no_active_session(self) -> None:
        client = _make_client(session_list=[])  # empty list → no active session
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {}
        with pytest.raises(HomeAssistantError) as excinfo:
            await handler(call_obj)
        assert getattr(excinfo.value, "translation_key", "") in (
            "cooking_no_active_session",
            "no_active_cooking_session",
        )


# ─── set_recipe_timer ─────────────────────────────────────────────────────────


class TestSetRecipeTimer:
    def _get_handler(self, hass: MagicMock) -> Any:
        return hass.services.async_register.call_args_list[2][0][2]

    @pytest.mark.asyncio
    async def test_appends_timer_and_starts_ha_timer(self) -> None:
        session = _make_session(timers=[])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label": "pasta", "duration_sec": 600}

        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_start",
            new_callable=AsyncMock,
        ) as mock_start:
            await handler(call_obj)

        mock_start.assert_awaited_once()
        start_args = mock_start.call_args[0]
        # session_id[:8] = "sess_abc"; trailing/no-op underscore stripped.
        assert start_args[1] == "timer.culiplan_session_sess_abc_pasta"
        assert start_args[2] == 600

    @pytest.mark.asyncio
    async def test_replaces_existing_timer_same_label(self) -> None:
        existing_timer = {"label": "pasta", "durationSec": 300, "id": "t1"}
        session = _make_session(timers=[existing_timer])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label": "pasta", "duration_sec": 600}

        with patch("custom_components.culiplan.cooking_services._ha_timer_start"):
            await handler(call_obj)

        # Should patch with a timers list that has only ONE pasta entry
        patch_payload = client._patch.call_args[0][1]
        pasta_timers = [t for t in patch_payload["timers"] if t["label"] == "pasta"]
        assert len(pasta_timers) == 1
        assert pasta_timers[0]["durationSec"] == 600

    @pytest.mark.asyncio
    async def test_fires_timer_started_event(self) -> None:
        session = _make_session()
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label": "sauce", "duration_sec": 180}

        with patch("custom_components.culiplan.cooking_services._ha_timer_start"):
            await handler(call_obj)

        event_type = hass.bus.async_fire.call_args[0][0]
        assert event_type == f"{DOMAIN}_recipe_timer_started"


# ─── cancel_recipe_timer ──────────────────────────────────────────────────────


class TestCancelRecipeTimer:
    def _get_handler(self, hass: MagicMock) -> Any:
        return hass.services.async_register.call_args_list[3][0][2]

    @pytest.mark.asyncio
    async def test_removes_timer_and_cancels_ha_timer(self) -> None:
        timer = {"id": "t1", "label": "pasta", "durationSec": 600}
        session = _make_session(timers=[timer])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label_or_id": "pasta"}

        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_cancel",
            new_callable=AsyncMock,
        ) as mock_cancel:
            await handler(call_obj)

        mock_cancel.assert_awaited_once()
        # Patch should have been called with empty timers list
        patch_payload = client._patch.call_args[0][1]
        assert patch_payload["timers"] == []

    @pytest.mark.asyncio
    async def test_raises_when_timer_not_found(self) -> None:
        session = _make_session(timers=[])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label_or_id": "nonexistent"}

        # The error is raised with translation_key="timer_not_found".
        # HomeAssistantError stringifies to the key on test infrastructure
        # without a loaded translation cache; assert on the key.
        with pytest.raises(HomeAssistantError) as excinfo:
            await handler(call_obj)
        assert getattr(excinfo.value, "translation_key", "") == "timer_not_found"

    @pytest.mark.asyncio
    async def test_fires_timer_cancelled_event(self) -> None:
        timer = {"id": "t2", "label": "garlic", "durationSec": 60}
        session = _make_session(timers=[timer])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        handler = self._get_handler(hass)

        call_obj = MagicMock()
        call_obj.data = {"label_or_id": "garlic"}

        with patch("custom_components.culiplan.cooking_services._ha_timer_cancel"):
            await handler(call_obj)

        event_type = hass.bus.async_fire.call_args[0][0]
        assert event_type == f"{DOMAIN}_recipe_timer_cancelled"


# ─── pause / resume / complete ───────────────────────────────────────────────


class TestPauseResumComplete:
    @pytest.mark.asyncio
    async def test_pause_patches_status_paused(self) -> None:
        session = _make_session(status="active")
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        # pause is index 4
        handler = hass.services.async_register.call_args_list[4][0][2]

        call_obj = MagicMock()
        call_obj.data = {}
        await handler(call_obj)

        client._patch.assert_awaited_once_with(
            f"/api/cooking-sessions/{session['id']}",
            {"status": "paused"},
        )

    @pytest.mark.asyncio
    async def test_resume_patches_status_active(self) -> None:
        session = _make_session(status="paused")
        client = _make_client(session_list=[session])  # query returns paused sessions
        # resume handler queries paused sessions, so mock async_get for both paths
        client.async_get.return_value = [session]
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        # resume is index 5
        handler = hass.services.async_register.call_args_list[5][0][2]

        call_obj = MagicMock()
        call_obj.data = {}
        await handler(call_obj)

        client._patch.assert_awaited_once_with(
            f"/api/cooking-sessions/{session['id']}",
            {"status": "active"},
        )

    @pytest.mark.asyncio
    async def test_complete_patches_status_completed_and_cancels_timers(self) -> None:
        timer = {"id": "t1", "label": "pasta", "durationSec": 600}
        session = _make_session(status="active", timers=[timer])
        client = _make_client(session=session)
        hass = _make_hass()
        hass.data[DOMAIN]["test_entry_id"]["client"] = client

        async_register_cooking_services(hass)
        # complete is index 6
        handler = hass.services.async_register.call_args_list[6][0][2]

        call_obj = MagicMock()
        call_obj.data = {}

        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_cancel",
            new_callable=AsyncMock,
        ) as mock_cancel:
            await handler(call_obj)

        client._patch.assert_awaited_once_with(
            f"/api/cooking-sessions/{session['id']}",
            {"status": "completed"},
        )
        mock_cancel.assert_awaited_once()


# ─── Timer mirroring via sync_ha_timers ──────────────────────────────────────


class TestSyncHaTimers:
    @pytest.mark.asyncio
    async def test_starts_ha_timer_for_each_active_timer(self) -> None:
        session = _make_session(
            session_id="abcdef12",
            timers=[
                {"label": "pasta", "durationSec": 600, "remainingSec": 450},
                {"label": "sauce", "durationSec": 300, "remainingSec": 200},
            ],
        )
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_start",
            new_callable=AsyncMock,
        ) as mock_start:
            await sync_ha_timers(hass, session)

        assert mock_start.call_count == 2
        # Verify remaining seconds (not full duration) are used for cross-surface handoff
        calls = mock_start.call_args_list
        durations = {c[0][2] for c in calls}
        assert 450 in durations
        assert 200 in durations

    @pytest.mark.asyncio
    async def test_no_timers_no_ha_calls(self) -> None:
        session = _make_session(timers=[])
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_start",
            new_callable=AsyncMock,
        ) as mock_start:
            await sync_ha_timers(hass, session)
        mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_remaining_skipped(self) -> None:
        """Timer with remainingSec=0 (already elapsed) must not restart."""
        session = _make_session(
            timers=[{"label": "pasta", "durationSec": 600, "remainingSec": 0}]
        )
        hass = MagicMock()
        with patch(
            "custom_components.culiplan.cooking_services._ha_timer_start",
            new_callable=AsyncMock,
        ) as mock_start:
            await sync_ha_timers(hass, session)
        mock_start.assert_not_called()


# ─── Voice intent → service dispatch (AC#4) ──────────────────────────────────


class TestCookingIntentDispatch:
    """Verify that the cooking intent handler wires to the correct service."""

    @pytest.mark.asyncio
    async def test_next_step_intent_calls_advance_service(self) -> None:

        # Patch __init__ import name
        with patch(
            "custom_components.culiplan.__init__._COOKING_INTENT_TO_SERVICE",
            {"CuliplanNextCookingStep": "advance_cooking_step"},
        ):
            from custom_components.culiplan.__init__ import (
                _make_cooking_intent_handler as mkh,
            )  # noqa: PLC0415

            entry = MagicMock()
            entry.entry_id = "test_entry_id"
            handler = mkh("CuliplanNextCookingStep", entry)

        intent_obj = MagicMock()
        intent_obj.slots = {}
        intent_obj.hass = MagicMock()
        intent_obj.hass.services = MagicMock()
        intent_obj.hass.services.async_call = AsyncMock()
        intent_obj.create_response = MagicMock()
        response_mock = MagicMock()
        response_mock.async_set_speech = MagicMock()
        intent_obj.create_response.return_value = response_mock

        await handler.async_handle(intent_obj)

        intent_obj.hass.services.async_call.assert_awaited_once()
        service_call_args = intent_obj.hass.services.async_call.call_args
        assert service_call_args[0][0] == DOMAIN
        assert service_call_args[0][1] == "advance_cooking_step"
