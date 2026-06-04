"""Tests for _register_intents — verifies executor offload (Bug 3 fix)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_hass_mock(language: str = "en") -> MagicMock:
    """Return a minimal hass mock sufficient for _register_intents."""
    hass = MagicMock()
    hass.config.language = language
    # async_add_executor_job must be awaitable (returns a coroutine).
    hass.async_add_executor_job = AsyncMock()
    # async_create_task schedules the inner coroutine immediately in tests.
    hass.async_create_task = MagicMock()
    return hass


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_register_intents_creates_task(hass, mock_config_entry):
    """_register_intents must schedule a background task, not block inline."""
    from custom_components.culiplan import _register_intents

    # Replace hass.async_create_task with a spy so we can confirm it was called.
    hass.async_create_task = MagicMock()

    _register_intents(hass, mock_config_entry)

    # Must have scheduled exactly one task (the async _do_register coroutine).
    hass.async_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_register_intents_uses_executor_for_yaml_load(hass, mock_config_entry):
    """The YAML read_text must be dispatched to async_add_executor_job, not called inline."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    # Capture the coroutine passed to async_create_task so we can await it.
    captured_coro = None

    def _capture_task(coro):
        nonlocal captured_coro
        captured_coro = coro

    hass.async_create_task = _capture_task

    # async_add_executor_job returns the YAML payload when called.
    sample_yaml: dict = {"intents": {"CuliplanWhatsDinnerTonight": {}}}
    hass.async_add_executor_job = AsyncMock(return_value=sample_yaml)

    with patch.object(ha_intent, "async_register"):
        _register_intents(hass, mock_config_entry)

        assert captured_coro is not None, "_register_intents must schedule a task"

        # Await the scheduled coroutine to exercise the executor path.
        await captured_coro

    # async_add_executor_job must have been called (offload happened).
    hass.async_add_executor_job.assert_awaited_once()
    # Confirm the callable passed is the blocking YAML loader, not a coroutine.
    load_callable = hass.async_add_executor_job.call_args[0][0]
    assert callable(load_callable), "First arg to async_add_executor_job must be a callable"


@pytest.mark.asyncio
async def test_register_intents_yaml_error_is_non_fatal(hass, mock_config_entry):
    """A broken YAML file must log an error but not raise."""
    from custom_components.culiplan import _register_intents

    captured_coro = None

    def _capture_task(coro):
        nonlocal captured_coro
        captured_coro = coro

    hass.async_create_task = _capture_task
    hass.async_add_executor_job = AsyncMock(side_effect=OSError("file missing"))

    _register_intents(hass, mock_config_entry)
    assert captured_coro is not None

    # Should not raise even though the executor job fails.
    await captured_coro


@pytest.mark.asyncio
async def test_register_intents_registers_known_intents(hass, mock_config_entry):
    """Known intents in the YAML are registered via intent.async_register."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    captured_coro = None

    def _capture_task(coro):
        nonlocal captured_coro
        captured_coro = coro

    hass.async_create_task = _capture_task

    yaml_data = {
        "intents": {
            "CuliplanWhatsDinnerTonight": {},
            "CuliplanGetWeekMeals": {},
        }
    }
    hass.async_add_executor_job = AsyncMock(return_value=yaml_data)

    with patch.object(ha_intent, "async_register") as mock_register:
        _register_intents(hass, mock_config_entry)
        await captured_coro

    # Two intents → two registrations
    assert mock_register.call_count == 2
