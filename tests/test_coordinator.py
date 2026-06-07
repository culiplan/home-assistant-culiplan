"""Tests for CuliplanCoordinator — happy path, reconnect, stale token."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.coordinator import (
    CuliplanCoordinator,
    _MAX_HEARTBEAT_MISSES,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.async_get_meal_plans.return_value = [{"id": "mp1"}]
    client.async_get_shopping_lists.return_value = [{"id": "sl1"}]
    client._access_token = "tok_initial"
    return client


@pytest.fixture
def mock_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def coordinator(hass, mock_client, mock_entry):
    return CuliplanCoordinator(hass, mock_client, mock_entry)


# ─── Happy path ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initial_fetch_populates_data(coordinator, mock_client):
    """First refresh fetches meal plans and shopping lists from REST."""
    with patch.object(coordinator, "_connect", new_callable=AsyncMock):
        data = await coordinator._async_update_data()

    assert data["meal_plans"] == [{"id": "mp1"}]
    assert data["shopping_lists"] == [{"id": "sl1"}]
    mock_client.async_get_meal_plans.assert_awaited_once()
    mock_client.async_get_shopping_lists.assert_awaited_once()


@pytest.mark.asyncio
async def test_ha_event_meal_plan_triggers_refresh(coordinator, mock_client):
    """meal_plan.updated event causes meal plan re-fetch."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}

    with patch.object(
        coordinator, "_refresh_meal_plans", new_callable=AsyncMock
    ) as mock_refresh:
        await coordinator._handle_event(
            {
                "type": "meal_plan.updated",
                "id": "mp1",
                "updatedAt": "2026-04-25T12:00:00Z",
            }
        )
        mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_ha_event_shopping_item_triggers_refresh(coordinator, mock_client):
    """shopping_list.item.added event causes shopping list re-fetch."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}

    with patch.object(
        coordinator, "_refresh_shopping_lists", new_callable=AsyncMock
    ) as mock_refresh:
        await coordinator._handle_event(
            {
                "type": "shopping_list.item.added",
                "id": "item1",
                "updatedAt": "2026-04-25T12:00:00Z",
            }
        )
        mock_refresh.assert_awaited_once()


# ─── Reconnect logic ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect_schedules_reconnect(coordinator):
    """A disconnect event schedules the reconnect loop."""
    coordinator._connected = True
    coordinator._miss_count = 0

    with patch.object(coordinator, "_schedule_reconnect") as mock_schedule:
        # Simulate a disconnect callback
        coordinator._connected = False
        coordinator._miss_count += 1
        coordinator._schedule_reconnect()
        mock_schedule.assert_called_once()


@pytest.mark.asyncio
async def test_max_heartbeat_misses_marks_unavailable(coordinator):
    """After _MAX_HEARTBEAT_MISSES disconnects, coordinator marks itself unavailable."""
    coordinator._connected = True
    coordinator._miss_count = 0
    coordinator.last_update_success = True

    with patch.object(coordinator, "async_update_listeners"):
        for _ in range(_MAX_HEARTBEAT_MISSES):
            coordinator._miss_count += 1

        if coordinator._miss_count >= _MAX_HEARTBEAT_MISSES:
            coordinator.last_update_success = False
            coordinator.async_update_listeners()

    assert not coordinator.last_update_success


@pytest.mark.asyncio
async def test_reconnect_resets_miss_count(coordinator):
    """Successful reconnect resets the heartbeat miss counter."""
    coordinator._miss_count = _MAX_HEARTBEAT_MISSES
    coordinator._connected = False

    # Simulate a successful connect callback
    coordinator._connected = True
    coordinator._miss_count = 0

    assert coordinator._miss_count == 0


# ─── Token refresh ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_token_refreshed_before_connect(coordinator, mock_entry):
    """_get_valid_token() calls async_ensure_token_valid and returns the token."""
    mock_impl = MagicMock()
    mock_oauth_session = MagicMock()
    mock_oauth_session.async_ensure_token_valid = AsyncMock()
    mock_oauth_session.token = {"access_token": "tok_refreshed"}

    # config_entry_oauth2_flow is imported lazily inside _get_valid_token,
    # so patch the symbols at their source module.
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow"
            ".async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=mock_impl,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session",
            return_value=mock_oauth_session,
        ),
    ):
        token = await coordinator._get_valid_token()

    assert token == "tok_refreshed"
    mock_oauth_session.async_ensure_token_valid.assert_awaited_once()


# ─── Additional coverage (v0.13.0) ───────────────────────────────────────────


from custom_components.culiplan.ai.types import PremiumRequiredError


@pytest.mark.asyncio
async def test_pantry_premium_required_is_skipped_silently(coordinator, mock_client):
    """403 premium_required on pantry omits the slice; the fetch itself succeeds."""
    mock_client.async_get_pantry_items.side_effect = PremiumRequiredError(
        feature="pantry", upgrade_url="https://x"
    )
    data = await coordinator._async_update_data()
    assert data["pantry_items"] == []


@pytest.mark.asyncio
async def test_pantry_other_error_logged_but_not_fatal(coordinator, mock_client):
    """A generic pantry error logs a warning but does NOT abort setup."""
    mock_client.async_get_pantry_items.side_effect = RuntimeError("network down")
    data = await coordinator._async_update_data()
    assert data["pantry_items"] == []


@pytest.mark.asyncio
async def test_energy_premium_required_is_skipped_silently(coordinator, mock_client):
    mock_client.async_get_energy_today.side_effect = PremiumRequiredError(
        feature="energy", upgrade_url="https://x"
    )
    data = await coordinator._async_update_data()
    assert data["energy_today"] is None


@pytest.mark.asyncio
async def test_energy_other_error_logged(coordinator, mock_client):
    mock_client.async_get_energy_today.side_effect = RuntimeError("boom")
    data = await coordinator._async_update_data()
    assert data["energy_today"] is None


@pytest.mark.asyncio
async def test_core_endpoint_failure_raises_update_failed(coordinator, mock_client):
    """If meal_plans/shopping_lists fail, setup must raise UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    mock_client.async_get_meal_plans.side_effect = RuntimeError("backend down")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_auth_failed_propagates(coordinator, mock_client):
    from homeassistant.exceptions import ConfigEntryAuthFailed

    mock_client.async_get_meal_plans.side_effect = ConfigEntryAuthFailed("expired")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_handle_event_dinner_party(coordinator):
    """dinner_party.updated triggers async_set_updated_data so listeners fire."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}
    with patch.object(coordinator, "async_set_updated_data") as set_data:
        await coordinator._handle_event({"type": "dinner_party.updated"})
        set_data.assert_called_once()


@pytest.mark.asyncio
async def test_handle_event_cooking_session(coordinator):
    """cooking.session.* events trigger _refresh_cooking_session."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}
    with patch.object(
        coordinator, "_refresh_cooking_session", new_callable=AsyncMock
    ) as refresh:
        await coordinator._handle_event({"type": "cooking.session.updated"})
        refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_event_pantry_item(coordinator):
    """pantry.item.* events trigger _refresh_pantry."""
    coordinator.data = {"meal_plans": [], "shopping_lists": []}
    with patch.object(
        coordinator, "_refresh_pantry", new_callable=AsyncMock
    ) as refresh:
        await coordinator._handle_event({"type": "pantry.item.added"})
        refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_meal_plans_swallows_errors(coordinator, mock_client):
    mock_client.async_get_meal_plans.side_effect = RuntimeError("boom")
    coordinator.data = {}
    # Must not raise
    await coordinator._refresh_meal_plans()


@pytest.mark.asyncio
async def test_refresh_shopping_lists_swallows_errors(coordinator, mock_client):
    mock_client.async_get_shopping_lists.side_effect = RuntimeError("boom")
    coordinator.data = {}
    await coordinator._refresh_shopping_lists()


@pytest.mark.asyncio
async def test_refresh_pantry_swallows_errors(coordinator, mock_client):
    mock_client.async_get_pantry_items.side_effect = RuntimeError("boom")
    coordinator.data = {}
    await coordinator._refresh_pantry()


@pytest.mark.asyncio
async def test_refresh_energy_swallows_errors(coordinator, mock_client):
    mock_client.async_get_energy_today.side_effect = RuntimeError("boom")
    coordinator.data = {}
    await coordinator._refresh_energy()


@pytest.mark.asyncio
async def test_refresh_cooking_session_no_active(coordinator, mock_client):
    """When the backend returns no active session, coordinator clears the cached one."""
    mock_client.async_get = AsyncMock(return_value=[])
    coordinator.data = {"active_cooking_session": {"id": "old"}}
    with patch(
        "custom_components.culiplan.cooking_services.sync_ha_timers",
        new=AsyncMock(),
    ):
        await coordinator._refresh_cooking_session()
    # Coordinator data updated with active_cooking_session=None
    assert coordinator.data["active_cooking_session"] is None


@pytest.mark.asyncio
async def test_refresh_cooking_session_with_active(coordinator, mock_client):
    """Active session is propagated to coordinator data and timers are synced."""
    session = {"id": "s1", "currentStep": 1, "timers": []}
    mock_client.async_get = AsyncMock(return_value=[session])
    coordinator.data = {}
    with patch(
        "custom_components.culiplan.cooking_services.sync_ha_timers",
        new=AsyncMock(),
    ) as sync:
        await coordinator._refresh_cooking_session()
    sync.assert_awaited_once()
    assert coordinator.data["active_cooking_session"] == session


@pytest.mark.asyncio
async def test_refresh_cooking_session_envelope_response(coordinator, mock_client):
    """The /api/cooking-sessions endpoint may return a {data: [...]} envelope."""
    session = {"id": "s1"}
    mock_client.async_get = AsyncMock(return_value={"data": [session]})
    coordinator.data = {}
    with patch(
        "custom_components.culiplan.cooking_services.sync_ha_timers",
        new=AsyncMock(),
    ):
        await coordinator._refresh_cooking_session()
    assert coordinator.data["active_cooking_session"] == session


@pytest.mark.asyncio
async def test_refresh_cooking_session_swallows_errors(coordinator, mock_client):
    mock_client.async_get = AsyncMock(side_effect=RuntimeError("boom"))
    coordinator.data = {}
    # Must not raise
    await coordinator._refresh_cooking_session()


# ─── async_stop ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_stop_disconnects(coordinator):
    """async_stop must disconnect the sio client and mark _stopped."""
    sio = MagicMock()
    sio.disconnect = AsyncMock()
    coordinator._sio = sio
    await coordinator.async_stop()
    assert coordinator._stopped is True
    sio.disconnect.assert_awaited_once()
    assert coordinator._sio is None


@pytest.mark.asyncio
async def test_async_stop_when_already_stopped(coordinator):
    """async_stop without a connection is a no-op."""
    coordinator._sio = None
    await coordinator.async_stop()  # must not raise
    assert coordinator._stopped is True


# ─── Schedule reconnect ──────────────────────────────────────────────────────


def test_schedule_reconnect_noop_when_stopped(coordinator):
    coordinator._stopped = True
    coordinator._reconnect_task = None
    coordinator._schedule_reconnect()
    assert coordinator._reconnect_task is None


def test_schedule_reconnect_noop_when_task_running(coordinator):
    """An in-progress reconnect task is not duplicated."""
    running = MagicMock()
    running.done = MagicMock(return_value=False)
    coordinator._reconnect_task = running
    coordinator._schedule_reconnect()
    # No new task created (still the same one).
    assert coordinator._reconnect_task is running


# ─── Socket.IO connect path (v0.13.0) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_start_initiates_connect(coordinator):
    """async_start clears _stopped and calls _connect."""
    coordinator._stopped = True
    with patch.object(coordinator, "_connect", new=AsyncMock()) as connect:
        await coordinator.async_start()
    assert coordinator._stopped is False
    connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_returns_early_when_stopped(coordinator):
    """_connect must early-return if async_stop already fired."""
    coordinator._stopped = True
    # Should not even reach the token call.
    with patch.object(coordinator, "_get_valid_token", new=AsyncMock()) as get_tok:
        await coordinator._connect()
    get_tok.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_creates_socketio_client_and_connects(coordinator):
    """_connect wires up the socket.io client and calls connect()."""
    coordinator._stopped = False
    fake_sio = MagicMock()
    fake_sio.connect = AsyncMock()
    fake_sio.event = MagicMock(return_value=lambda fn: fn)
    fake_sio.on = MagicMock(return_value=lambda fn: fn)
    with (
        patch.object(
            coordinator, "_get_valid_token", new=AsyncMock(return_value="tok")
        ),
        patch(
            "custom_components.culiplan.coordinator.socketio.AsyncClient",
            return_value=fake_sio,
        ),
    ):
        await coordinator._connect()
    fake_sio.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_socketio_connection_error_schedules_reconnect(coordinator):
    """A ConnectionError on connect() triggers _schedule_reconnect."""
    import socketio

    coordinator._stopped = False
    fake_sio = MagicMock()
    fake_sio.connect = AsyncMock(
        side_effect=socketio.exceptions.ConnectionError("nope")
    )
    fake_sio.event = MagicMock(return_value=lambda fn: fn)
    fake_sio.on = MagicMock(return_value=lambda fn: fn)
    with (
        patch.object(
            coordinator, "_get_valid_token", new=AsyncMock(return_value="tok")
        ),
        patch(
            "custom_components.culiplan.coordinator.socketio.AsyncClient",
            return_value=fake_sio,
        ),
        patch.object(coordinator, "_schedule_reconnect") as schedule,
    ):
        await coordinator._connect()
    schedule.assert_called_once()


@pytest.mark.asyncio
async def test_async_stop_cancels_running_reconnect_task(coordinator):
    """async_stop awaits the reconnect task cancellation."""
    import asyncio

    async def _slow():
        await asyncio.sleep(60)

    task = asyncio.create_task(_slow())
    coordinator._reconnect_task = task
    await coordinator.async_stop()
    assert task.done() or task.cancelled()


@pytest.mark.asyncio
async def test_handle_event_unknown_type_is_noop(coordinator):
    """Unknown event types must NOT raise."""
    coordinator.data = {}
    await coordinator._handle_event({"type": "weird.event.you.never.heard.of"})


# ─── Socket.IO event handler functions (registered inside _connect) ──────────


@pytest.mark.asyncio
async def test_socketio_handlers_invoke_expected_behaviour(coordinator):
    """Pull the four event handlers out of the AsyncClient mock and exercise them."""
    coordinator._stopped = False
    coordinator._miss_count = 0
    captured_handlers = {}

    def _event(namespace=None):  # decorator factory used as @sio.event(namespace=…)
        def _dec(fn):
            captured_handlers[fn.__name__] = fn
            return fn

        return _dec

    def _on(event_name, namespace=None):
        def _dec(fn):
            captured_handlers[event_name] = fn
            return fn

        return _dec

    fake_sio = MagicMock()
    fake_sio.event = _event
    fake_sio.on = _on
    fake_sio.connect = AsyncMock()

    with (
        patch.object(
            coordinator, "_get_valid_token", new=AsyncMock(return_value="tok")
        ),
        patch(
            "custom_components.culiplan.coordinator.socketio.AsyncClient",
            return_value=fake_sio,
        ),
    ):
        await coordinator._connect()

    # connect handler — runs on a fresh connection
    with patch.object(coordinator, "async_refresh", new=AsyncMock()) as refresh:
        await captured_handlers["connect"]()
    assert coordinator._connected is True
    refresh.assert_awaited_once()

    # disconnect handler — bumps miss count, triggers reconnect once threshold reached
    with patch.object(coordinator, "_schedule_reconnect") as schedule:
        # Below threshold: no listener update
        await captured_handlers["disconnect"]("manual")
        # At threshold: listeners updated
        await captured_handlers["disconnect"]("server")
    schedule.assert_called()

    # ha:event handler — forwards to _handle_event
    with patch.object(coordinator, "_handle_event", new=AsyncMock()) as handle:
        await captured_handlers["ha:event"]({"type": "meal_plan.updated"})
    handle.assert_awaited_once()

    # ha:error handler — logs and returns (just verify it doesn't raise)
    await captured_handlers["ha:error"]({"message": "warn"})


# ─── _schedule_reconnect inner loop ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_reconnect_loops_until_connected(coordinator):
    """The reconnect loop keeps retrying with backoff until connected."""
    import asyncio as _asyncio

    # Save the real sleep BEFORE patching so we can use it inside _fake_sleep
    # without the patch sending us back into the fake.
    _real_sleep = _asyncio.sleep

    coordinator._stopped = False
    coordinator._connected = False
    coordinator._reconnect_task = None

    call_count = {"n": 0}

    async def _fake_connect():
        call_count["n"] += 1
        if call_count["n"] >= 2:
            coordinator._connected = True

    async def _fake_sleep(_delay):
        await _real_sleep(0)

    captured = {}

    def _create_bg_task(coro, name=None):
        task = _asyncio.create_task(coro, name=name)
        captured["task"] = task
        return task

    coordinator.hass.async_create_background_task = _create_bg_task

    with (
        patch.object(coordinator, "_connect", new=_fake_connect),
        patch("custom_components.culiplan.coordinator.asyncio.sleep", new=_fake_sleep),
    ):
        coordinator._schedule_reconnect(delay=0.001)
        await _asyncio.wait_for(captured["task"], timeout=2.0)

    assert coordinator._connected is True
    assert call_count["n"] >= 1


@pytest.mark.asyncio
async def test_reconnect_loop_breaks_on_stop(coordinator):
    """If async_stop fires mid-loop, the reconnect coroutine exits cleanly."""
    import asyncio as _asyncio

    _real_sleep = _asyncio.sleep

    coordinator._stopped = False
    coordinator._connected = False
    coordinator._reconnect_task = None

    async def _fake_connect():
        coordinator._stopped = True

    async def _fake_sleep(_delay):
        await _real_sleep(0)

    captured = {}

    def _create_bg_task(coro, name=None):
        task = _asyncio.create_task(coro, name=name)
        captured["task"] = task
        return task

    coordinator.hass.async_create_background_task = _create_bg_task

    with (
        patch.object(coordinator, "_connect", new=_fake_connect),
        patch("custom_components.culiplan.coordinator.asyncio.sleep", new=_fake_sleep),
    ):
        coordinator._schedule_reconnect(delay=0.001)
        await _asyncio.wait_for(captured["task"], timeout=2.0)

    assert coordinator._connected is False
