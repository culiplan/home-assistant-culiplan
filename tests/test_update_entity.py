"""Tests for the native HA update entity (custom_components/culiplan/update.py).

The entity is Vincent's primary install/update path (no HACS on his HAOS),
so its install / auto-install / release-notes behaviour gets covered here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.update import (
    CuliplanUpdateEntity,
    _installed_version,
    async_setup_entry,
)
from custom_components.culiplan.updater import LatestRelease


# ─── _installed_version ───────────────────────────────────────────────────────


def test_installed_version_reads_manifest():
    """_installed_version reads the version from the integration manifest."""
    version = _installed_version()
    # Always a SemVer-ish string; never the "0.0.0" fallback in a real repo.
    assert version != "0.0.0"
    assert "." in version


def test_installed_version_fallback_on_manifest_failure():
    """Returns "0.0.0" if the manifest cannot be parsed."""
    with patch(
        "custom_components.culiplan.update._MANIFEST_PATH",
        MagicMock(read_text=MagicMock(side_effect=OSError("boom"))),
    ):
        assert _installed_version() == "0.0.0"


# ─── CuliplanUpdateEntity ─────────────────────────────────────────────────────


def _make_entry(options: dict | None = None):
    entry = MagicMock()
    entry.entry_id = "entry_test"
    entry.data = {}
    entry.options = options or {}
    return entry


def _make_release(version: str = "9.9.9", notes: str | None = "release notes"):
    return LatestRelease(
        version=version,
        zipball_url=f"https://example.test/v{version}.zip",
        html_url=f"https://example.test/releases/v{version}",
        notes=notes,
    )


class TestEntityConstruction:
    def test_unique_id_is_per_entry(self):
        entry = _make_entry()
        ent = CuliplanUpdateEntity(entry)
        assert ent.unique_id == "entry_test_update"

    def test_installed_version_set(self):
        ent = CuliplanUpdateEntity(_make_entry())
        assert ent.installed_version is not None
        assert ent.latest_version == ent.installed_version  # before first poll


class TestAutoUpdatePreference:
    def test_default_is_on(self):
        ent = CuliplanUpdateEntity(_make_entry())
        assert ent._auto_update_enabled() is True

    def test_options_override_to_off(self):
        ent = CuliplanUpdateEntity(_make_entry(options={"auto_update": False}))
        assert ent._auto_update_enabled() is False


class TestAsyncUpdate:
    @pytest.mark.asyncio
    async def test_no_release_keeps_state(self):
        ent = CuliplanUpdateEntity(_make_entry())
        with patch(
            "custom_components.culiplan.update.async_check_latest",
            new=AsyncMock(return_value=None),
        ):
            await ent.async_update()
        # Without a release we report no update
        assert ent.latest_version == ent.installed_version

    @pytest.mark.asyncio
    async def test_newer_release_updates_attrs(self):
        ent = CuliplanUpdateEntity(_make_entry(options={"auto_update": False}))
        ent._attr_installed_version = "0.0.1"
        release = _make_release("9.9.9")
        with patch(
            "custom_components.culiplan.update.async_check_latest",
            new=AsyncMock(return_value=release),
        ):
            await ent.async_update()
        assert ent.latest_version == "9.9.9"
        assert ent._attr_release_url == release.html_url

    @pytest.mark.asyncio
    async def test_auto_install_when_enabled(self):
        ent = CuliplanUpdateEntity(_make_entry(options={"auto_update": True}))
        ent._attr_installed_version = "0.0.1"
        ent.hass = MagicMock()
        ent.hass.services.async_call = AsyncMock()
        ent.async_write_ha_state = MagicMock()
        release = _make_release("9.9.9")

        with (
            patch(
                "custom_components.culiplan.update.async_check_latest",
                new=AsyncMock(return_value=release),
            ),
            patch(
                "custom_components.culiplan.update.async_perform_update",
                new=AsyncMock(),
            ) as perform,
        ):
            await ent.async_update()

        perform.assert_awaited_once()
        # Loop-guard set so a second poll for the same version is a no-op.
        assert ent._auto_installed_version == "9.9.9"

    @pytest.mark.asyncio
    async def test_auto_install_skipped_when_already_installed_this_release(self):
        ent = CuliplanUpdateEntity(_make_entry(options={"auto_update": True}))
        ent._attr_installed_version = "0.0.1"
        ent._auto_installed_version = "9.9.9"
        release = _make_release("9.9.9")

        with (
            patch(
                "custom_components.culiplan.update.async_check_latest",
                new=AsyncMock(return_value=release),
            ),
            patch(
                "custom_components.culiplan.update.async_perform_update",
                new=AsyncMock(),
            ) as perform,
        ):
            await ent.async_update()

        perform.assert_not_awaited()


class TestReleaseNotes:
    @pytest.mark.asyncio
    async def test_returns_notes_when_release_cached(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent._latest_release = _make_release("9.9.9", notes="line 1\nline 2")
        notes = await ent.async_release_notes()
        assert notes == "line 1\nline 2"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_release(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent._latest_release = None
        assert await ent.async_release_notes() is None

    @pytest.mark.asyncio
    async def test_returns_none_when_release_has_no_notes(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent._latest_release = _make_release("9.9.9", notes=None)
        assert await ent.async_release_notes() is None


class TestAsyncInstall:
    @pytest.mark.asyncio
    async def test_install_uses_cached_release(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent._latest_release = _make_release("9.9.9")
        ent.hass = MagicMock()
        ent.hass.services.async_call = AsyncMock()
        ent.async_write_ha_state = MagicMock()
        ent.hass.async_create_task = MagicMock()

        with patch(
            "custom_components.culiplan.update.async_perform_update",
            new=AsyncMock(),
        ) as perform:
            await ent.async_install(version=None, backup=False)
        perform.assert_awaited_once()
        ent.hass.async_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_falls_back_to_fresh_check(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent.hass = MagicMock()
        ent.hass.services.async_call = AsyncMock()
        ent.async_write_ha_state = MagicMock()
        ent.hass.async_create_task = MagicMock()

        release = _make_release("9.9.9")
        with (
            patch(
                "custom_components.culiplan.update.async_check_latest",
                new=AsyncMock(return_value=release),
            ),
            patch(
                "custom_components.culiplan.update.async_perform_update",
                new=AsyncMock(),
            ) as perform,
        ):
            await ent.async_install(version=None, backup=False)
        perform.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_install_raises_when_github_unreachable(self):
        from homeassistant.exceptions import HomeAssistantError

        ent = CuliplanUpdateEntity(_make_entry())
        with patch(
            "custom_components.culiplan.update.async_check_latest",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HomeAssistantError):
                await ent.async_install(version=None, backup=False)

    @pytest.mark.asyncio
    async def test_install_clears_in_progress_on_failure(self):
        from homeassistant.exceptions import HomeAssistantError

        ent = CuliplanUpdateEntity(_make_entry())
        ent._latest_release = _make_release("9.9.9")
        ent.hass = MagicMock()
        ent.async_write_ha_state = MagicMock()

        with patch(
            "custom_components.culiplan.update.async_perform_update",
            new=AsyncMock(side_effect=RuntimeError("zip-slip blocked")),
        ):
            with pytest.raises(HomeAssistantError):
                await ent.async_install(version=None, backup=False)
        assert ent._attr_in_progress is False


# ─── async_setup_entry / async_added_to_hass ─────────────────────────────────


class TestSetup:
    @pytest.mark.asyncio
    async def test_async_setup_entry_adds_one_entity(self):
        hass = MagicMock()
        entry = _make_entry()
        async_add_entities = MagicMock()
        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        added = async_add_entities.call_args[0][0]
        assert len(added) == 1
        assert isinstance(added[0], CuliplanUpdateEntity)

    @pytest.mark.asyncio
    async def test_async_added_to_hass_polls_immediately(self):
        ent = CuliplanUpdateEntity(_make_entry())
        ent.async_write_ha_state = MagicMock()
        with patch.object(ent, "async_update", new=AsyncMock()) as update:
            await ent.async_added_to_hass()
        update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_added_to_hass_swallows_network_error(self):
        """Startup must NEVER fail because GitHub is unreachable."""
        ent = CuliplanUpdateEntity(_make_entry())
        with patch.object(
            ent, "async_update", new=AsyncMock(side_effect=Exception("net"))
        ):
            # Should not raise
            await ent.async_added_to_hass()
