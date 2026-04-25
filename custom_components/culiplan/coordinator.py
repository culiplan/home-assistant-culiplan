"""WebSocket-backed DataUpdateCoordinator for the Flavorplan integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import socketio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FlavorplanApiClient
from .const import BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Socket.IO namespace and event names (matches haEventPublisher.ts)
HA_NAMESPACE = "/ha-events"
HA_EVENT = "ha:event"
HA_ERROR = "ha:error"

# Heartbeat: backend sends Socket.IO pings every 25 s.
# We track missed pings via disconnect events rather than raw ping/pong.
_MAX_HEARTBEAT_MISSES = 2

# Reconnect: exponential backoff between 2 s and 120 s.
_RECONNECT_INITIAL_DELAY = 2.0
_RECONNECT_MAX_DELAY = 120.0
_RECONNECT_FACTOR = 2.0


class FlavorplanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push-first coordinator backed by the /ha-events Socket.IO namespace.

    Flow:
    1. async_start() connects to Socket.IO and does an initial REST fetch.
    2. On ha:event, the relevant resource is re-fetched via REST and
       async_set_updated_data() triggers entity updates.
    3. On disconnect, the reconnect loop re-establishes the connection with
       exponential backoff, then does a full REST refresh.
    4. After _MAX_HEARTBEAT_MISSES consecutive failures the coordinator marks
       itself unavailable via UpdateFailed.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: FlavorplanApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # No periodic polling; all updates arrive via push.
            update_interval=None,
        )
        self.client = client
        self.entry = entry
        self._sio: socketio.AsyncClient | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
        self._miss_count = 0

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Connect to Socket.IO and perform the initial data fetch."""
        await self._connect()

    async def async_stop(self) -> None:
        """Disconnect Socket.IO and cancel background tasks."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._sio:
            await self._sio.disconnect()
            self._sio = None

    # ─── DataUpdateCoordinator protocol ─────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch full state from REST; called on start and after reconnect."""
        try:
            meal_plans = await self.client.async_get_meal_plans()
            shopping_lists = await self.client.async_get_shopping_lists()
            pantry_items = await self.client.async_get_pantry_items()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Flavorplan REST fetch failed: {err}") from err

        return {
            "meal_plans": meal_plans,
            "shopping_lists": shopping_lists,
            "pantry_items": pantry_items,
        }

    # ─── Socket.IO connection ─────────────────────────────────────────────────

    async def _connect(self) -> None:
        """Create the Socket.IO client and connect to the HA namespace."""
        access_token = await self._get_valid_token()

        sio = socketio.AsyncClient(
            reconnection=False,  # We manage reconnection ourselves.
            logger=False,
            engineio_logger=False,
        )
        self._sio = sio

        @sio.event(namespace=HA_NAMESPACE)
        async def connect() -> None:
            _LOGGER.info("Connected to Flavorplan /ha-events namespace")
            self._connected = True
            self._miss_count = 0
            # Full state refresh on (re)connect.
            await self.async_refresh()

        @sio.event(namespace=HA_NAMESPACE)
        async def disconnect(reason: str | None = None) -> None:
            _LOGGER.warning("Disconnected from Flavorplan /ha-events: %s", reason)
            self._connected = False
            self._miss_count += 1
            if self._miss_count >= _MAX_HEARTBEAT_MISSES:
                self.last_update_success = False
                self.async_update_listeners()
            self._schedule_reconnect()

        @sio.on(HA_EVENT, namespace=HA_NAMESPACE)
        async def on_ha_event(payload: dict[str, Any]) -> None:
            await self._handle_event(payload)

        @sio.on(HA_ERROR, namespace=HA_NAMESPACE)
        async def on_ha_error(payload: dict[str, Any]) -> None:
            _LOGGER.warning("HA gateway error: %s", payload.get("message"))

        try:
            await sio.connect(
                BASE_URL,
                namespaces=[HA_NAMESPACE],
                auth={"token": access_token},
                transports=["websocket"],
                wait_timeout=15,
            )
        except socketio.exceptions.ConnectionError as err:
            _LOGGER.error("Failed to connect to /ha-events: %s", err)
            self._connected = False
            self._schedule_reconnect()

    async def _handle_event(self, payload: dict[str, Any]) -> None:
        """Process an inbound ha:event by refetching the changed resource."""
        event_type: str = payload.get("type", "")
        resource_id: str = payload.get("id", "")

        _LOGGER.debug("ha:event type=%s id=%s", event_type, resource_id)

        if event_type == "meal_plan.updated":
            await self._refresh_meal_plans()
        elif event_type.startswith("shopping_list.item."):
            await self._refresh_shopping_lists()
        elif event_type.startswith("pantry.item."):
            await self._refresh_pantry()

    async def _refresh_meal_plans(self) -> None:
        try:
            meal_plans = await self.client.async_get_meal_plans()
            current = dict(self.data or {})
            current["meal_plans"] = meal_plans
            self.async_set_updated_data(current)
        except Exception as err:
            _LOGGER.error("Failed to refresh meal plans: %s", err)

    async def _refresh_shopping_lists(self) -> None:
        try:
            shopping_lists = await self.client.async_get_shopping_lists()
            current = dict(self.data or {})
            current["shopping_lists"] = shopping_lists
            self.async_set_updated_data(current)
        except Exception as err:
            _LOGGER.error("Failed to refresh shopping lists: %s", err)

    async def _refresh_pantry(self) -> None:
        try:
            pantry_items = await self.client.async_get_pantry_items()
            current = dict(self.data or {})
            current["pantry_items"] = pantry_items
            self.async_set_updated_data(current)
        except Exception as err:
            _LOGGER.error("Failed to refresh pantry items: %s", err)

    # ─── Reconnect logic ─────────────────────────────────────────────────────

    def _schedule_reconnect(self, delay: float = _RECONNECT_INITIAL_DELAY) -> None:
        """Schedule a reconnect attempt using exponential backoff."""
        if self._reconnect_task and not self._reconnect_task.done():
            return

        async def _reconnect_loop(initial_delay: float) -> None:
            wait = initial_delay
            while not self._connected:
                _LOGGER.info("Reconnecting to Flavorplan in %.0f s…", wait)
                await asyncio.sleep(wait)
                try:
                    if self._sio:
                        await self._sio.disconnect()
                    await self._connect()
                    if self._connected:
                        return
                except Exception as err:
                    _LOGGER.warning("Reconnect attempt failed: %s", err)
                wait = min(wait * _RECONNECT_FACTOR, _RECONNECT_MAX_DELAY)

        self._reconnect_task = self.hass.loop.create_task(
            _reconnect_loop(delay),
            name=f"{DOMAIN}_reconnect",
        )

    # ─── Token helpers ───────────────────────────────────────────────────────

    async def _get_valid_token(self) -> str:
        """Return a valid OAuth access token, refreshing if necessary."""
        from homeassistant.helpers import config_entry_oauth2_flow

        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                self.hass, self.entry
            )
        )
        session = config_entry_oauth2_flow.OAuth2Session(
            self.hass, self.entry, implementation
        )
        await session.async_ensure_token_valid()
        token = session.token.get("access_token", "")
        # Update client with the refreshed token.
        self.client._access_token = token  # noqa: SLF001
        return token
