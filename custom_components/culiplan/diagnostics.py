"""Diagnostics support for the Culiplan integration (task-1501, Gold target).

Returns integration health data for troubleshooting while deliberately
redacting sensitive values (OAuth tokens, personal data).

The returned dict is structured per the HA diagnostics contract:
  https://developers.home-assistant.io/docs/diagnostics/

Error tracking:
  A module-level deque records (timestamp, entry_id) pairs for every error
  captured via ``record_error()``.  ``async_get_config_entry_diagnostics``
  counts entries for the past 24 h so the value is always fresh.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# ── Module-level 24-h error ring buffer ────────────────────────────────────────
# Each element: (unix_timestamp: float, entry_id: str)
_ERROR_BUFFER: deque[tuple[float, str]] = deque(maxlen=10_000)

_24H_SECONDS = 86_400.0


def record_error(entry_id: str) -> None:
    """Record an error occurrence for *entry_id*.

    Call this from exception handlers anywhere in the integration so the
    diagnostics snapshot can surface an error-rate summary.
    """
    _ERROR_BUFFER.append((time.monotonic(), entry_id))


def _count_errors_last_24h(entry_id: str) -> int:
    """Return the number of errors recorded in the last 24 h for *entry_id*."""
    now = time.monotonic()
    cutoff = now - _24H_SECONDS
    return sum(1 for ts, eid in _ERROR_BUFFER if eid == entry_id and ts >= cutoff)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics data for *entry* — tokens and PII are redacted."""

    data: dict[str, Any] = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    # ── OAuth token age (seconds since issue — value itself is NOT exposed) ──
    token: dict[str, Any] = entry.data.get("token", {})
    token_issued_at: float | None = token.get("issued_at")  # epoch seconds
    if token_issued_at is not None:
        token_age_seconds = int(time.time() - token_issued_at)
    else:
        token_age_seconds = None

    # ── Premium status from entry data (non-sensitive config flag) ───────────
    premium: bool | None = entry.data.get("premium")

    # ── Coordinator health snapshot ──────────────────────────────────────────
    if coordinator is not None:
        last_update_success: bool = coordinator.last_update_success
        last_exception: str | None = (
            repr(coordinator.last_exception)
            if coordinator.last_exception is not None
            else None
        )
        connected: bool = getattr(coordinator, "_connected", False)
    else:
        last_update_success = False
        last_exception = "coordinator not initialised"
        connected = False

    # ── Error counter ────────────────────────────────────────────────────────
    errors_last_24h = _count_errors_last_24h(entry.entry_id)

    return {
        "entry_id": entry.entry_id,
        "domain": DOMAIN,
        "token_age_seconds": token_age_seconds,
        "token_value": "**REDACTED**",
        "premium": premium,
        "coordinator": {
            "last_update_success": last_update_success,
            "last_exception": last_exception,
            "connected": connected,
        },
        "errors_last_24h": errors_last_24h,
        "diagnostics_captured_at": datetime.now(UTC).isoformat(),
    }
