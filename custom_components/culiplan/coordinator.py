"""WebSocket-backed DataUpdateCoordinator for the Culiplan integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import socketio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CuliplanApiClient
from .const import BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

HA_NAMESPACE = "/ha-events"
HA_EVENT = "ha:event"
HA_ERROR = "ha:error"

_MAX_HEARTBEAT_MISSES = 2
_RECONNECT_INITIAL_DELAY = 2.0
_RECONNECT_MAX_DELAY = 120.0
_RECONNECT_FACTOR = 2.0


class CuliplanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push-first coordinator backed by the /ha-events Socket.IO namespace."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CuliplanApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.client = client
        self.entry = entry
        self._sio: socketio.AsyncClient | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
        self._miss_count = 0
        self._stopped = (
            False  # set by async_stop(); guards against post-unload reconnects
        )

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Connect to Socket.IO."""
        self._stopped = False
        await self._connect()

    async def async_stop(self) -> None:
        """Disconnect Socket.IO and cancel background tasks."""
        self._stopped = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._sio:
            try:
                await self._sio.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._sio = None

    # ─── DataUpdateCoordinator protocol ─────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch full state from REST; called on start and after reconnect."""
        try:
            meal_plans = await self.client.async_get_meal_plans()
            shopping_lists = await self.client.async_get_shopping_lists()
            pantry_items = await self.client.async_get_pantry_items()
            energy_today = await self.client.async_get_energy_today()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Culiplan REST fetch failed: {err}") from err

        return {
            "meal_plans": meal_plans,
            "shopping_lists": shopping_lists,
            "pantry_items": pantry_items,
            "energy_today": energy_today,
        }

    # ─── Socket.IO connection ─────────────────────────────────────────────────

    async def _connect(self) -> None:
        """Create the Socket.IO client and connect to the HA namespace."""
        if self._stopped:
            return

        access_token = await self._get_valid_token()

        sio = socketio.AsyncClient(
            reconnection=False,
            logger=False,
            engineio_logger=False,
        )
        self._sio = sio

        @sio.event(namespace=HA_NAMESPACE)
        async def connect() -> None:
            _LOGGER.info("Connected to Culiplan /ha-events")
            self._connected = True
            self._miss_count = 0
            await self.async_refresh()

        @sio.event(namespace=HA_NAMESPACE)
        async def disconnect(reason: str | None = None) -> None:
            _LOGGER.warning("Disconnected from Culiplan /ha-events: %s", reason)
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
        event_type: str = payload.get("type", "")
        _LOGGER.debug("ha:event type=%s id=%s", event_type, payload.get("id"))

        if event_type == "meal_plan.updated":
            await self._refresh_meal_plans()
            # Energy estimate depends on today's meal plans — refresh together.
            await self._refresh_energy()
        elif event_type.startswith("shopping_list.item."):
            await self._refresh_shopping_lists()
        elif event_type.startswith("pantry.item."):
            await self._refresh_pantry()
        elif event_type == "dinner_party.updated":
            # task-1380 AC#3 — live update; trigger coordinator listeners so
            # DinnerPartyActiveBinarySensor.async_update() is scheduled.
            self.async_set_updated_data(self.data or {})
        elif event_type in (
            "cooking.session.updated",
            "cooking.session.started",
            "cooking.session.completed",
        ):
            # task-1397 — re-fetch active session and sync HA timer entities.
            # ID-only payload (§14.3); the full session is re-fetched here.
            await self._refresh_cooking_session()

    async def _refresh_meal_plans(self) -> None:
        try:
            meal_plans = await self.client.async_get_meal_plans()
            self.async_set_updated_data({**(self.data or {}), "meal_plans": meal_plans})
        except Exception as err:
            _LOGGER.error("Failed to refresh meal plans: %s", err)

    async def _refresh_shopping_lists(self) -> None:
        try:
            shopping_lists = await self.client.async_get_shopping_lists()
            self.async_set_updated_data(
                {**(self.data or {}), "shopping_lists": shopping_lists}
            )
        except Exception as err:
            _LOGGER.error("Failed to refresh shopping lists: %s", err)

    async def _refresh_pantry(self) -> None:
        try:
            pantry_items = await self.client.async_get_pantry_items()
            self.async_set_updated_data(
                {**(self.data or {}), "pantry_items": pantry_items}
            )
        except Exception as err:
            _LOGGER.error("Failed to refresh pantry items: %s", err)

    async def _refresh_cooking_session(self) -> None:
        """Re-fetch the active cooking session and sync HA timer entities.

        Called when the coordinator receives a cooking.session.* event.
        Timer sync is a best-effort operation; failures are logged, not raised.
        """
        try:
            # Import here to avoid circular imports between coordinator and
            # cooking_services (cooking_services imports from api, not coordinator).
            from .cooking_services import sync_ha_timers  # noqa: PLC0415

            sessions = await self.client.async_get(
                "/api/cooking-sessions?status=active&limit=1"
            )
            if isinstance(sessions, list):
                items = sessions
            elif isinstance(sessions, dict):
                items = sessions.get("sessions", sessions.get("data", []))
            else:
                items = []

            if items:
                session = items[0]
                await sync_ha_timers(self.hass, session)
                # Update coordinator data so Lovelace card can refresh.
                self.async_set_updated_data(
                    {**(self.data or {}), "active_cooking_session": session}
                )
            else:
                # Session ended — clear from coordinator data.
                self.async_set_updated_data(
                    {**(self.data or {}), "active_cooking_session": None}
                )
        except Exception as err:
            _LOGGER.error("Failed to refresh cooking session: %s", err)

    async def _refresh_energy(self) -> None:
        """Re-fetch today's kWh estimate (task-1399). Called after meal_plan.updated."""
        try:
            energy_today = await self.client.async_get_energy_today()
            self.async_set_updated_data(
                {**(self.data or {}), "energy_today": energy_today}
            )
        except Exception as err:
            _LOGGER.error("Failed to refresh energy today: %s", err)

    # ─── Reconnect logic ─────────────────────────────────────────────────────

    def _schedule_reconnect(self, delay: float = _RECONNECT_INITIAL_DELAY) -> None:
        """Schedule reconnect with exponential backoff. No-op if stopped."""
        if self._stopped:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return

        async def _reconnect_loop(initial_delay: float) -> None:
            wait = initial_delay
            while not self._connected and not self._stopped:
                _LOGGER.info("Reconnecting to Culiplan in %.0f s…", wait)
                await asyncio.sleep(wait)
                if self._stopped:
                    return
                try:
                    if self._sio:
                        await self._sio.disconnect()
                    await self._connect()
                    if self._connected:
                        return
                except Exception as err:
                    _LOGGER.warning("Reconnect attempt failed: %s", err)
                wait = min(wait * _RECONNECT_FACTOR, _RECONNECT_MAX_DELAY)

        # Use HA-managed background task so HA can cancel it on shutdown.
        self._reconnect_task = self.hass.async_create_background_task(
            _reconnect_loop(delay),
            name=f"{DOMAIN}_reconnect",
        )

    # ─── Token helpers ───────────────────────────────────────────────────────

    async def _get_valid_token(self) -> str:
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
        token = cast(str, session.token.get("access_token", ""))
        self.client._access_token = token  # noqa: SLF001
        return token
