"""DataUpdateCoordinator placeholder — implemented in task-1365."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import FlavorplanApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)


class FlavorplanCoordinator(DataUpdateCoordinator):
    """Coordinator stub; WebSocket-backed implementation added in task-1365."""

    def __init__(self, hass: HomeAssistant, client: FlavorplanApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        # task-1365: replace polling with Socket.IO push + REST refetch
        return {}
