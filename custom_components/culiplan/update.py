"""Update platform — native HA update entity backed by the GitHub self-updater.

Exposes a single ``update.culiplan_update`` entity so the integration's own
updates surface the standard Home Assistant way: an "Update available — Install"
card on the device page AND in Settings → Updates, with release notes. No HACS
required. ``Install`` reuses :func:`updater.async_perform_update` then restarts
HA to apply the new code. The entity polls GitHub for the latest release on
``SCAN_INTERVAL`` (and whenever HA refreshes it on demand).
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

from .const import DOMAIN
from .helpers import _build_device_info
from .updater import LatestRelease, async_check_latest, async_perform_update

_LOGGER = logging.getLogger(__name__)

# How often HA polls GitHub for a newer release (also refreshable on demand).
SCAN_INTERVAL = timedelta(hours=6)

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
        """Initialise from the config entry (device grouping + version)."""
        self._attr_unique_id = f"{DOMAIN}_update"
        self._attr_device_info = _build_device_info(entry)
        installed = _installed_version()
        self._attr_installed_version = installed
        # Until the first poll we report "no update" by mirroring installed.
        self._attr_latest_version = installed
        self._latest_release: LatestRelease | None = None

    async def async_update(self) -> None:
        """Poll GitHub for the latest release (silent on network failure)."""
        release = await async_check_latest(self.hass)
        if release is None:
            return
        self._latest_release = release
        self._attr_latest_version = release.version
        self._attr_release_url = release.html_url

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
