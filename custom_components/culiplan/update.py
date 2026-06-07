"""Update platform — native HA update entity backed by the GitHub self-updater.

Exposes a single ``update.culiplan_update`` entity so the integration's own
updates surface the standard Home Assistant way: an "Update available — Install"
card on the device page AND in Settings → Updates, with release notes. No HACS
required. ``Install`` reuses :func:`updater.async_perform_update` then restarts
HA to apply the new code. The entity polls GitHub for the latest release on
``SCAN_INTERVAL`` (and whenever HA refreshes it on demand).

v0.9.0 additions
----------------
* Polls every 1 hour instead of 6 (faster detection of new releases).
* Performs an immediate GitHub check on HA restart via ``async_added_to_hass``
  so the entity never shows "up-to-date" on startup when a newer release exists.
* Reads the ``auto_update`` preference from config-entry options (persisted via
  the Options flow). When enabled (default) the entity auto-installs each new
  version exactly once per version string, then restarts HA.

v0.12.0 change
--------------
* The HA UpdateEntity ``auto_update`` property is **no longer overridden** here.
  Previously we returned the persisted preference, which surfaced an
  ``auto_update`` switch in the entity's more-info dialog — but that switch is
  read-only at the framework level, so taps appeared to do nothing and then
  reverted. Auto-update behavior is unchanged (silent install on next poll if
  the persisted preference is on, default on); the persistent on/off control
  is the Options-flow checkbox at Settings → Devices & Services → Culiplan →
  Configure → "Update Culiplan automatically". This matters on Core/venv
  installs where the automatic HA restart leaves HA down — those users need
  the opt-out path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers import _build_device_info
from .updater import LatestRelease, async_check_latest, async_perform_update, is_newer

_LOGGER = logging.getLogger(__name__)

# How often HA polls GitHub for a newer release (also refreshable on demand).
SCAN_INTERVAL = timedelta(hours=1)

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"


def _installed_version() -> str:
    """Read the running integration version from manifest.json."""
    try:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return str(data["version"])
    except Exception:  # noqa: BLE001
        return "0.0.0"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Culiplan self-update entity."""
    async_add_entities([CuliplanUpdateEntity(entry)])


class CuliplanUpdateEntity(UpdateEntity):
    """Reports installed vs latest GitHub release and self-installs on demand."""

    _attr_has_entity_name = True
    _attr_name = "Update"
    _attr_title = "Culiplan"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise from the config entry (device grouping + version).

        Per-entry unique_id (v0.13.0) — pre-v0.13.0 entries used the legacy
        ``f"{DOMAIN}_update"`` form; ``__init__.async_migrate_entry`` rewrites
        those in the entity registry on first load after upgrade.
        """
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update"
        self._attr_device_info = _build_device_info(entry)
        installed = _installed_version()
        self._attr_installed_version = installed
        # Until the first poll we report "no update" by mirroring installed.
        self._attr_latest_version = installed
        self._latest_release: LatestRelease | None = None
        # Loop-guard: track the latest version for which we already triggered
        # an auto-install so we never fire twice for the same release.
        self._auto_installed_version: str | None = None

    # ------------------------------------------------------------------
    # Auto-update preference (read live from config-entry options)
    # ------------------------------------------------------------------

    def _auto_update_enabled(self) -> bool:
        """Return whether auto-update is enabled (persisted in options, default True).

        Intentionally NOT exposed as the ``auto_update`` property because the
        HA UpdateEntity framework renders that as a read-only switch — taps
        appear to toggle but revert on the next state write. Users change the
        preference via the Options flow instead. See module docstring (v0.12.0).
        """
        return bool(self._entry.options.get("auto_update", True))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Run an immediate GitHub check on startup so we never show a false 'up-to-date'."""
        await super().async_added_to_hass()
        try:
            await self.async_update()
            self.async_write_ha_state()
        except Exception:  # noqa: BLE001
            # Never let a startup network failure break the entity setup.
            pass

    async def async_update(self) -> None:
        """Poll GitHub for the latest release (silent on network failure).

        If auto-update is enabled (Options flow, default on) and a genuinely
        newer version is found that we have not yet auto-installed, trigger
        installation immediately. The ``_auto_installed_version`` guard ensures
        each version fires at most once (across the lifetime of the entity
        object; a restart resets the guard, but by then installed==latest so
        the condition won't re-fire).
        """
        release = await async_check_latest(self.hass)
        if release is None:
            return
        self._latest_release = release
        self._attr_latest_version = release.version
        self._attr_release_url = release.html_url

        installed = self._attr_installed_version or _installed_version()

        if (
            self._auto_update_enabled()
            and is_newer(release.version, installed)
            and not self._attr_in_progress
            and self._auto_installed_version != release.version
        ):
            _LOGGER.info(
                "[culiplan][update] Auto-update: installing %s (installed: %s)",
                release.version,
                installed,
            )
            # Mark before the await so a concurrent poll can't double-trigger.
            self._auto_installed_version = release.version
            await self.async_install(None, False)

    async def async_release_notes(self) -> str | None:
        """Return the latest release's notes for the update dialog."""
        if self._latest_release is None:
            return None
        return self._latest_release.notes or None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Download + apply the latest release, then restart Home Assistant.

        ``version``/``backup`` from the HA framework are ignored: this entity
        always installs the latest release and always takes its own internal
        backup (see :func:`updater.async_perform_update`).
        """
        release = self._latest_release or await async_check_latest(self.hass)
        if release is None:
            raise HomeAssistantError(
                "Could not reach GitHub to fetch the latest Culiplan release"
            )

        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            await async_perform_update(self.hass, release.zipball_url)
        except Exception as exc:  # noqa: BLE001
            self._attr_in_progress = False
            self.async_write_ha_state()
            raise HomeAssistantError(f"Culiplan update failed: {exc}") from exc

        _LOGGER.info(
            "[culiplan][update] Update to %s applied — restarting Home Assistant",
            release.version,
        )

        async def _restart() -> None:
            # Brief delay so the install result returns to the UI before HA
            # shuts down (HAOS/Supervised/Docker bring it back automatically).
            await asyncio.sleep(2)
            await self.hass.services.async_call(
                "homeassistant", "restart", blocking=False
            )

        self.hass.async_create_task(_restart())
