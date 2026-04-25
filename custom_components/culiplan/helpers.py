"""Shared helpers for the Flavorplan integration."""

from __future__ import annotations

from datetime import UTC, date, datetime


def parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 date or datetime string into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.combine(
            date.fromisoformat(value), datetime.min.time(), tzinfo=UTC
        )
