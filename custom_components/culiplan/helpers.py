"""Shared helpers for the Culiplan integration."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"


def _build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return a canonical DeviceInfo for all Culiplan entities.

    Reads ``version`` from ``manifest.json`` so sw_version stays in sync
    automatically when the manifest is bumped.
    """
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        sw_version: str | None = manifest.get("version")
    except Exception:  # noqa: BLE001
        sw_version = None

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Culiplan",
        manufacturer="Culiplan",
        model="Meal Planner",
        sw_version=sw_version,
        configuration_url="https://culiplan.com",
        entry_type="service",
    )


def parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 date or datetime string into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.combine(
            date.fromisoformat(value), datetime.min.time(), tzinfo=UTC
        )
