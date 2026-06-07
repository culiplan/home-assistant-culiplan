"""Coverage for cooking_services.py helpers + error paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.culiplan.ai.types import PremiumRequiredError


# ─── _get_active_session ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_active_session_returns_first_from_list():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(return_value=[{"id": "s1"}])
    result = await _get_active_session(client)
    assert result["id"] == "s1"


@pytest.mark.asyncio
async def test_get_active_session_unwraps_envelope():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(return_value={"sessions": [{"id": "s1"}]})
    result = await _get_active_session(client)
    assert result["id"] == "s1"


@pytest.mark.asyncio
async def test_get_active_session_data_envelope():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(return_value={"data": [{"id": "s1"}]})
    result = await _get_active_session(client)
    assert result["id"] == "s1"


@pytest.mark.asyncio
async def test_get_active_session_no_session_raises():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(return_value=[])
    with pytest.raises(HomeAssistantError) as excinfo:
        await _get_active_session(client)
    assert getattr(excinfo.value, "translation_key", "") == "no_active_cooking_session"


@pytest.mark.asyncio
async def test_get_active_session_unexpected_type_raises():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(return_value="garbage")
    with pytest.raises(HomeAssistantError):
        await _get_active_session(client)


@pytest.mark.asyncio
async def test_get_active_session_premium_required_propagates():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(
        side_effect=PremiumRequiredError(feature="cooking", upgrade_url="https://x")
    )
    with pytest.raises(PremiumRequiredError):
        await _get_active_session(client)


@pytest.mark.asyncio
async def test_get_active_session_other_error_wraps():
    from custom_components.culiplan.cooking_services import _get_active_session

    client = MagicMock()
    client.async_get = AsyncMock(side_effect=RuntimeError("backend down"))
    with pytest.raises(HomeAssistantError) as excinfo:
        await _get_active_session(client)
    assert (
        getattr(excinfo.value, "translation_key", "")
        == "cooking_session_fetch_failed"
    )


# ─── _patch_session ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_session_success():
    from custom_components.culiplan.cooking_services import _patch_session

    client = MagicMock()
    client._patch = AsyncMock(return_value={"id": "s1", "currentStep": 2})
    result = await _patch_session(client, "s1", {"currentStep": 2})
    assert result["currentStep"] == 2


@pytest.mark.asyncio
async def test_patch_session_premium_required_propagates():
    from custom_components.culiplan.cooking_services import _patch_session

    client = MagicMock()
    client._patch = AsyncMock(
        side_effect=PremiumRequiredError(feature="cooking", upgrade_url="https://x")
    )
    with pytest.raises(PremiumRequiredError):
        await _patch_session(client, "s1", {})


@pytest.mark.asyncio
async def test_patch_session_other_error_wraps():
    from custom_components.culiplan.cooking_services import _patch_session

    client = MagicMock()
    client._patch = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HomeAssistantError) as excinfo:
        await _patch_session(client, "s1", {})
    assert (
        getattr(excinfo.value, "translation_key", "")
        == "cooking_session_update_failed"
    )


# ─── _ha_timer_start / _ha_timer_cancel ──────────────────────────────────────


@pytest.mark.asyncio
async def test_ha_timer_start_swallows_errors():
    from custom_components.culiplan.cooking_services import _ha_timer_start

    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("no entity"))
    # Must not raise — timer entity may not exist on the first call.
    await _ha_timer_start(hass, "timer.x", 60)


@pytest.mark.asyncio
async def test_ha_timer_start_formats_duration():
    from custom_components.culiplan.cooking_services import _ha_timer_start

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    await _ha_timer_start(hass, "timer.x", 3725)  # 1h 02m 05s
    call_args = hass.services.async_call.call_args[0]
    payload = call_args[2]
    assert payload["duration"] == "01:02:05"


@pytest.mark.asyncio
async def test_ha_timer_cancel_swallows_errors():
    from custom_components.culiplan.cooking_services import _ha_timer_cancel

    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("no entity"))
    await _ha_timer_cancel(hass, "timer.x")


@pytest.mark.asyncio
async def test_ha_timer_cancel_calls_service():
    from custom_components.culiplan.cooking_services import _ha_timer_cancel

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    await _ha_timer_cancel(hass, "timer.x")
    hass.services.async_call.assert_awaited_once()


# ─── sync_ha_timers ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_ha_timers_starts_running_timers():
    from custom_components.culiplan.cooking_services import sync_ha_timers

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    session = {
        "id": "s1",
        "timers": [
            {"label": "pasta", "durationSec": 600, "status": "running"},
        ],
    }
    await sync_ha_timers(hass, session)
    # The pasta timer should have been started.
    assert hass.services.async_call.await_count >= 1


@pytest.mark.asyncio
async def test_sync_ha_timers_no_timers_is_noop():
    from custom_components.culiplan.cooking_services import sync_ha_timers

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    await sync_ha_timers(hass, {"id": "s1", "timers": []})
    hass.services.async_call.assert_not_awaited()


# ─── async_unregister_cooking_services ───────────────────────────────────────


def test_async_unregister_cooking_services_removes_each():
    from custom_components.culiplan.cooking_services import (
        COOKING_SERVICES,
        async_unregister_cooking_services,
    )

    hass = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_remove = MagicMock()
    async_unregister_cooking_services(hass)
    assert hass.services.async_remove.call_count == len(COOKING_SERVICES)


def test_async_unregister_cooking_services_skips_missing():
    """Already-removed services are skipped."""
    from custom_components.culiplan.cooking_services import (
        async_unregister_cooking_services,
    )

    hass = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_remove = MagicMock()
    async_unregister_cooking_services(hass)
    hass.services.async_remove.assert_not_called()
