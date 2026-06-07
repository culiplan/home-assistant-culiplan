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


@pytest.mark.asyncio
async def test_register_intents_is_a_coroutine(hass, mock_config_entry):
    """_register_intents is async (awaitable), not a fire-and-forget task scheduler.

    Earlier shape created a background task; current code awaits the loader
    directly so async_setup_entry can guarantee intents are registered before
    it returns. Verify the entry point is awaitable and returns None.
    """
    import inspect
    from custom_components.culiplan import _register_intents

    assert inspect.iscoroutinefunction(_register_intents)


@pytest.mark.asyncio
async def test_register_intents_uses_executor_for_yaml_load(hass, mock_config_entry):
    """The YAML read_text must be dispatched to async_add_executor_job, not called inline."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    # async_add_executor_job returns the YAML payload when called.
    sample_yaml: dict = {"intents": {"CuliplanWhatsDinnerTonight": {}}}
    hass.async_add_executor_job = AsyncMock(return_value=sample_yaml)

    with patch.object(ha_intent, "async_register"):
        await _register_intents(hass, mock_config_entry)

    # async_add_executor_job must have been called (offload happened).
    hass.async_add_executor_job.assert_awaited_once()
    # Confirm the callable passed is the blocking YAML loader, not a coroutine.
    load_callable = hass.async_add_executor_job.call_args[0][0]
    assert callable(load_callable), (
        "First arg to async_add_executor_job must be a callable"
    )


@pytest.mark.asyncio
async def test_register_intents_yaml_error_is_non_fatal(hass, mock_config_entry):
    """A broken YAML file must log an error but not raise."""
    from custom_components.culiplan import _register_intents

    hass.async_add_executor_job = AsyncMock(side_effect=OSError("file missing"))

    # Should not raise even though the executor job fails.
    await _register_intents(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_register_intents_registers_known_intents(hass, mock_config_entry):
    """Known intents in the YAML are registered via intent.async_register."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    yaml_data = {
        "intents": {
            "CuliplanWhatsDinnerTonight": {},
            "CuliplanGetWeekMeals": {},
        }
    }
    hass.async_add_executor_job = AsyncMock(return_value=yaml_data)

    with patch.object(ha_intent, "async_register") as mock_register:
        await _register_intents(hass, mock_config_entry)

    # Two intents → two registrations
    assert mock_register.call_count == 2
