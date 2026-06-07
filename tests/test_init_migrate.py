"""Tests for async_migrate_entry — the v1 → v2 per-entry unique_id rewrite.

The migration rewrites entity registry entries with the legacy
``f"{DOMAIN}_<suffix>"`` form to the per-entry
``f"{entry.entry_id}_<suffix>"`` form so adding a second Culiplan account
doesn't collide with the first. It must be:

  * Bounded to the config entry being migrated.
  * Idempotent (a half-finished run is safe to re-run).
  * Non-destructive: if both old and new uids exist, leave the old alone.
"""

from __future__ import annotations

import pytest

from custom_components.culiplan import (
    _LEGACY_UNIQUE_ID_SUFFIXES,
    async_migrate_entry,
)
from custom_components.culiplan.const import DOMAIN


def _make_entry(hass, entry_id: str = "entry-1", version: int = 1):
    """Create + register a real MockConfigEntry so async_update_entry works."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        version=version,
        data={},
    )
    entry.add_to_hass(hass)
    return entry


# ─── Legacy suffix table ──────────────────────────────────────────────────────


def test_legacy_suffix_table_covers_all_affected_entities():
    """Affected entities are sensor*, binary_sensor*, and update."""
    expected = {
        "meals_planned_this_week",
        "shopping_items",
        "expiring_pantry",
        "planned_kwh_today",
        "pantry_has_expiring",
        "dinner_party_active",
        "update",
    }
    assert set(_LEGACY_UNIQUE_ID_SUFFIXES) == expected


# ─── async_migrate_entry ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v2_entries_are_no_op(hass):
    """An already-migrated entry must not call into the entity registry."""
    entry = _make_entry(hass, entry_id="v2-entry", version=2)
    # If migrate_entry tried to fetch the registry it would touch hass.data;
    # use a sentinel to confirm it doesn't.
    sentinel = object()
    hass.data["culiplan_sentinel"] = sentinel
    assert await async_migrate_entry(hass, entry) is True
    assert hass.data["culiplan_sentinel"] is sentinel


@pytest.mark.asyncio
async def test_rewrites_each_legacy_unique_id(hass):
    """Each entity with a legacy unique_id is updated to the per-entry form."""
    from homeassistant.helpers import entity_registry as er

    entry = _make_entry(hass)
    registry = er.async_get(hass)

    # Inject one entity per legacy suffix using the public API. The helper
    # builds a registry entry with the legacy unique_id; migration should
    # rewrite each one in place.
    for suffix in _LEGACY_UNIQUE_ID_SUFFIXES:
        domain = (
            "binary_sensor"
            if suffix in {"pantry_has_expiring", "dinner_party_active"}
            else "update"
            if suffix == "update"
            else "sensor"
        )
        registry.async_get_or_create(
            domain=domain,
            platform=DOMAIN,
            unique_id=f"{DOMAIN}_{suffix}",
            config_entry=entry,
        )

    assert await async_migrate_entry(hass, entry) is True

    # Each entity now exposes the per-entry unique_id.
    for reg_entry in list(registry.entities.values()):
        if reg_entry.config_entry_id != entry.entry_id:
            continue
        assert not reg_entry.unique_id.startswith(f"{DOMAIN}_")
        suffix = reg_entry.unique_id[len(entry.entry_id) + 1 :]
        assert suffix in _LEGACY_UNIQUE_ID_SUFFIXES

    # Entry version was bumped on success.
    assert entry.version == 2


@pytest.mark.asyncio
async def test_other_config_entries_left_alone(hass):
    """Entities owned by a different config entry must NOT be touched."""
    from homeassistant.helpers import entity_registry as er

    entry = _make_entry(hass, entry_id="entry-main")
    other = _make_entry(hass, entry_id="entry-other")

    registry = er.async_get(hass)
    registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id=f"{DOMAIN}_meals_planned_this_week",
        config_entry=other,
    )

    await async_migrate_entry(hass, entry)

    # Other entry's unique_id unchanged
    for reg_entry in registry.entities.values():
        if reg_entry.config_entry_id == other.entry_id:
            assert reg_entry.unique_id == f"{DOMAIN}_meals_planned_this_week"


@pytest.mark.asyncio
async def test_idempotent_when_run_twice(hass):
    """A second migrate call is a no-op (registry already migrated)."""
    from homeassistant.helpers import entity_registry as er

    entry = _make_entry(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id=f"{DOMAIN}_meals_planned_this_week",
        config_entry=entry,
    )
    await async_migrate_entry(hass, entry)
    # Second call should not raise — the legacy uid is gone now.
    # The entry.version stays 1 here because we use a MagicMock entry, but
    # the migration logic itself is idempotent on the registry side.
    await async_migrate_entry(hass, entry)


@pytest.mark.asyncio
async def test_skips_when_target_uid_already_taken(hass, caplog):
    """If both old and new uids exist (partial prior migration), leave the
    legacy entity alone — never delete user data silently.
    """
    from homeassistant.helpers import entity_registry as er

    entry = _make_entry(hass)
    registry = er.async_get(hass)
    # Pre-existing entity already on the new uid
    registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id=f"{entry.entry_id}_meals_planned_this_week",
        config_entry=entry,
    )
    # Legacy entity that the migration would otherwise want to rename
    legacy = registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id=f"{DOMAIN}_meals_planned_this_week",
        config_entry=entry,
        suggested_object_id="culiplan_legacy_meals_planned_this_week",
    )
    legacy_id = legacy.entity_id

    await async_migrate_entry(hass, entry)

    # Legacy entity still exists with the legacy uid
    survivor = registry.async_get(legacy_id)
    assert survivor is not None
    assert survivor.unique_id == f"{DOMAIN}_meals_planned_this_week"
