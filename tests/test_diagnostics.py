"""Tests for the Culiplan diagnostics module (task-1501)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.culiplan.diagnostics import (
    _ERROR_BUFFER,
    async_get_config_entry_diagnostics,
    record_error,
)
from custom_components.culiplan.const import DOMAIN


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(entry_id: str = "test_entry_id", premium: bool = True) -> MagicMock:
    """Return a minimal mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {
        "token": {
            "access_token": "super-secret-token",
            "refresh_token": "another-secret",
            "token_type": "Bearer",
            "expires_in": 3600,
            "issued_at": time.time() - 1000,
        },
        "premium": premium,
    }
    return entry


def _make_coordinator(connected: bool = True) -> MagicMock:
    coord = MagicMock()
    coord.last_update_success = True
    coord.last_exception = None
    coord._connected = connected
    return coord


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDiagnosticsRedaction:
    """Token value must never appear in the diagnostics output."""

    @pytest.mark.asyncio
    async def test_token_value_is_redacted(self, hass, mock_config_entry):
        """The raw access_token must not appear in the diagnostics dict."""
        entry = _make_entry()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": _make_coordinator(),
        }

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["token_value"] == "**REDACTED**"
        # Flatten the whole dict and check the raw token is absent.
        flat = str(result)
        assert "super-secret-token" not in flat

    @pytest.mark.asyncio
    async def test_token_age_is_a_positive_integer(self, hass, mock_config_entry):
        entry = _make_entry()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": _make_coordinator(),
        }
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert isinstance(result["token_age_seconds"], int)
        assert result["token_age_seconds"] > 0


class TestCoordinatorHealthSnapshot:
    """Coordinator state must be reflected in diagnostics."""

    @pytest.mark.asyncio
    async def test_connected_coordinator_reflected(self, hass):
        entry = _make_entry()
        coord = _make_coordinator(connected=True)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["coordinator"]["last_update_success"] is True
        assert result["coordinator"]["last_exception"] is None
        assert result["coordinator"]["connected"] is True

    @pytest.mark.asyncio
    async def test_disconnected_coordinator_reflected(self, hass):
        entry = _make_entry()
        coord = _make_coordinator(connected=False)
        coord.last_update_success = False
        coord.last_exception = RuntimeError("timeout")
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["coordinator"]["connected"] is False
        assert result["coordinator"]["last_update_success"] is False
        assert "RuntimeError" in result["coordinator"]["last_exception"]

    @pytest.mark.asyncio
    async def test_missing_coordinator_does_not_raise(self, hass):
        """Diagnostics must not crash when the coordinator is absent."""
        entry = _make_entry()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}  # no coordinator key

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["coordinator"]["connected"] is False


class TestErrorCounter:
    """24-h error counter must count and respect the time window."""

    def setup_method(self) -> None:
        """Clear the shared buffer before each test."""
        _ERROR_BUFFER.clear()

    @pytest.mark.asyncio
    async def test_error_count_zero_by_default(self, hass):
        entry = _make_entry("no_errors_entry")
        hass.data.setdefault(DOMAIN, {})["no_errors_entry"] = {
            "coordinator": _make_coordinator(),
        }
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["errors_last_24h"] == 0

    @pytest.mark.asyncio
    async def test_error_count_increments(self, hass):
        entry = _make_entry("counting_entry")
        hass.data.setdefault(DOMAIN, {})["counting_entry"] = {
            "coordinator": _make_coordinator(),
        }
        record_error("counting_entry")
        record_error("counting_entry")
        record_error("counting_entry")

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["errors_last_24h"] == 3

    @pytest.mark.asyncio
    async def test_error_count_excludes_other_entries(self, hass):
        """Errors for a different entry must not be counted."""
        entry = _make_entry("my_entry")
        hass.data.setdefault(DOMAIN, {})["my_entry"] = {
            "coordinator": _make_coordinator(),
        }
        record_error("other_entry")
        record_error("other_entry")

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["errors_last_24h"] == 0


class TestPremiumStatus:
    """Premium flag must pass through to diagnostics."""

    @pytest.mark.asyncio
    async def test_premium_true(self, hass):
        entry = _make_entry(premium=True)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": _make_coordinator(),
        }
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["premium"] is True

    @pytest.mark.asyncio
    async def test_premium_false(self, hass):
        entry = _make_entry(premium=False)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": _make_coordinator(),
        }
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["premium"] is False
