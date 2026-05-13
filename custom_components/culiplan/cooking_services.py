"""
Culiplan HA cooking-mode services — Phase 3 (task-1397).

Seven services that wrap the /api/cooking-sessions backend:
    culiplan.start_cooking_mode     — POST /api/cooking-sessions
    culiplan.advance_cooking_step   — PATCH /api/cooking-sessions/:id  (+1 step)
    culiplan.set_recipe_timer       — PATCH /api/cooking-sessions/:id  (append timer)
    culiplan.cancel_recipe_timer    — PATCH /api/cooking-sessions/:id  (remove timer)
    culiplan.pause_cooking_mode     — PATCH /api/cooking-sessions/:id  (status=paused)
    culiplan.resume_cooking_mode    — PATCH /api/cooking-sessions/:id  (status=active)
    culiplan.complete_cooking_mode  — PATCH /api/cooking-sessions/:id  (status=completed)

Timer mirroring contract (§6.2):
    - On session start or step advance the coordinator re-fetches and calls
      _sync_ha_timers() to create/cancel HA timer entities.
    - Backend owns start/cancel source of truth; HA owns the countdown UI.
    - Timer entity IDs: timer.culiplan_session_<short_id>_<label_slug>

Architecture:
    - 403 premium_required → async_create_premium_repair (same Repairs UI as task-1395).
    - No active session → HomeAssistantError for services that require one.
    - Tier enforcement lives ONLY on the backend (§11.1.5).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .api import CuliplanApiClient
from .ai.types import PremiumRequiredError
from .const import DOMAIN
from .repairs import async_create_premium_repair, async_resolve_premium_repair

_LOGGER = logging.getLogger(__name__)

# ─── Service names ────────────────────────────────────────────────────────────

SERVICE_START_COOKING_MODE = "start_cooking_mode"
SERVICE_ADVANCE_COOKING_STEP = "advance_cooking_step"
SERVICE_SET_RECIPE_TIMER = "set_recipe_timer"
SERVICE_CANCEL_RECIPE_TIMER = "cancel_recipe_timer"
SERVICE_PAUSE_COOKING_MODE = "pause_cooking_mode"
SERVICE_RESUME_COOKING_MODE = "resume_cooking_mode"
SERVICE_COMPLETE_COOKING_MODE = "complete_cooking_mode"

COOKING_SERVICES = (
    SERVICE_START_COOKING_MODE,
    SERVICE_ADVANCE_COOKING_STEP,
    SERVICE_SET_RECIPE_TIMER,
    SERVICE_CANCEL_RECIPE_TIMER,
    SERVICE_PAUSE_COOKING_MODE,
    SERVICE_RESUME_COOKING_MODE,
    SERVICE_COMPLETE_COOKING_MODE,
)

# ─── Voluptuous schemas ───────────────────────────────────────────────────────

START_COOKING_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("recipe_id"): str,
        vol.Optional("servings"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)

ADVANCE_COOKING_STEP_SCHEMA = vol.Schema({})

SET_RECIPE_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required("label"): str,
        vol.Required("duration_sec"): vol.All(vol.Coerce(int), vol.Range(min=1, max=86400)),
        vol.Optional("step_index"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)

CANCEL_RECIPE_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required("label_or_id"): str,
    }
)

PAUSE_COOKING_MODE_SCHEMA = vol.Schema({})
RESUME_COOKING_MODE_SCHEMA = vol.Schema({})
COMPLETE_COOKING_MODE_SCHEMA = vol.Schema({})


# ─── Active-session helpers ───────────────────────────────────────────────────


async def _get_active_session(
    client: CuliplanApiClient,
) -> dict[str, Any]:
    """
    Fetch the active cooking session for the authenticated user.

    Raises HomeAssistantError if none exists.
    """
    try:
        sessions = await client.async_get("/api/cooking-sessions?status=active&limit=1")
    except PremiumRequiredError:
        raise
    except Exception as exc:
        raise HomeAssistantError(f"Failed to fetch cooking session: {exc}") from exc

    # The backend returns either a list or {sessions: [...]}
    if isinstance(sessions, list):
        items = sessions
    elif isinstance(sessions, dict):
        items = sessions.get("sessions", sessions.get("data", []))
    else:
        items = []

    if not items:
        raise HomeAssistantError(
            "No active cooking session. Call culiplan.start_cooking_mode first."
        )
    return items[0]


async def _patch_session(
    client: CuliplanApiClient,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """PATCH /api/cooking-sessions/:id and handle structured errors."""
    try:
        result = await client._patch(  # noqa: SLF001
            f"/api/cooking-sessions/{session_id}", payload
        )
        return result
    except PremiumRequiredError:
        raise
    except HomeAssistantError:
        raise
    except Exception as exc:
        raise HomeAssistantError(f"Cooking session update failed: {exc}") from exc


# ─── HA timer entity helpers ──────────────────────────────────────────────────


def _timer_entity_id(session_id: str, label: str) -> str:
    """Build deterministic HA timer entity ID from session ID and label."""
    short_id = session_id[:8]
    label_slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"timer.culiplan_session_{short_id}_{label_slug}"


async def _ha_timer_start(
    hass: HomeAssistant,
    entity_id: str,
    duration_sec: int,
) -> None:
    """Create / start a HA timer entity for the given duration."""
    hours, remainder = divmod(duration_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    try:
        await hass.services.async_call(
            "timer",
            "start",
            {
                "entity_id": entity_id,
                "duration": duration_str,
            },
            blocking=False,
        )
        _LOGGER.debug("[culiplan] HA timer started: %s (%s)", entity_id, duration_str)
    except Exception as exc:
        # Non-fatal: HA timer entity may not exist yet (first call).
        # Log and continue — the Lovelace card can still show backend timer data.
        _LOGGER.warning("[culiplan] Could not start HA timer %s: %s", entity_id, exc)


async def _ha_timer_cancel(hass: HomeAssistant, entity_id: str) -> None:
    """Cancel a HA timer entity."""
    try:
        await hass.services.async_call(
            "timer",
            "cancel",
            {"entity_id": entity_id},
            blocking=False,
        )
        _LOGGER.debug("[culiplan] HA timer cancelled: %s", entity_id)
    except Exception as exc:
        _LOGGER.warning("[culiplan] Could not cancel HA timer %s: %s", entity_id, exc)


async def sync_ha_timers(
    hass: HomeAssistant,
    session: dict[str, Any],
) -> None:
    """
    Mirror session.timers[] to HA timer entities.

    Called after any session mutation that may have changed the timer list.
    Idempotent — starts timers that are not yet running; does not restart
    already-running ones (remainingSec approximation avoids false restarts).
    """
    session_id: str = session.get("id", "")
    timers: list[dict[str, Any]] = session.get("timers", [])

    for timer in timers:
        label = timer.get("label", "timer")
        duration_sec = int(timer.get("durationSec", 0))
        remaining_sec = int(timer.get("remainingSec", duration_sec))
        entity_id = _timer_entity_id(session_id, label)

        if remaining_sec > 0 and duration_sec > 0:
            # Start with the remaining duration so cross-surface handoff is smooth.
            await _ha_timer_start(hass, entity_id, remaining_sec)


# ─── Service registration ─────────────────────────────────────────────────────


def async_register_cooking_services(hass: HomeAssistant) -> None:
    """Register all cooking-mode HA services."""

    def _get_client(entry_id: str | None) -> CuliplanApiClient:
        if not entry_id:
            raise HomeAssistantError("Culiplan is not configured.")
        return hass.data[DOMAIN][entry_id]["client"]

    def _find_entry_id() -> str | None:
        return next(iter(hass.data.get(DOMAIN, {})), None)

    # ── 1. start_cooking_mode ─────────────────────────────────────────────────

    async def handle_start_cooking_mode(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        recipe_id: str = call.data["recipe_id"]
        servings: int | None = call.data.get("servings")

        payload: dict[str, Any] = {"recipeId": recipe_id}
        if servings is not None:
            payload["servings"] = servings

        try:
            session = await client.async_post("/api/cooking-sessions", payload)
            async_resolve_premium_repair(hass, "cooking_mode")
            _LOGGER.info(
                "[culiplan] Cooking session started: id=%s recipe=%s step=%d/%d",
                session.get("id"),
                recipe_id,
                session.get("currentStep", 0),
                session.get("totalSteps", 0),
            )
            await sync_ha_timers(hass, session)
            hass.bus.async_fire(
                f"{DOMAIN}_cooking_session_started",
                {
                    "session_id": session.get("id"),
                    "recipe_id": recipe_id,
                    "current_step": session.get("currentStep", 0),
                    "total_steps": session.get("totalSteps", 0),
                },
            )
        except PremiumRequiredError as exc:
            async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
            raise

    # ── 2. advance_cooking_step ───────────────────────────────────────────────

    async def handle_advance_cooking_step(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        session = await _get_active_session(client)
        current_step: int = session.get("currentStep", 0)
        total_steps: int = session.get("totalSteps", 1)

        if current_step >= total_steps - 1:
            raise HomeAssistantError(
                f"Already at the last step ({current_step + 1}/{total_steps}). "
                "Use culiplan.complete_cooking_mode to finish."
            )

        updated = await _patch_session(
            client,
            session["id"],
            {"currentStep": current_step + 1},
        )
        _LOGGER.info(
            "[culiplan] Cooking step advanced: session=%s step=%d→%d",
            session["id"],
            current_step,
            current_step + 1,
        )
        await sync_ha_timers(hass, updated)
        hass.bus.async_fire(
            f"{DOMAIN}_cooking_step_advanced",
            {
                "session_id": session["id"],
                "previous_step": current_step,
                "current_step": current_step + 1,
                "total_steps": total_steps,
            },
        )

    # ── 3. set_recipe_timer ───────────────────────────────────────────────────

    async def handle_set_recipe_timer(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        session = await _get_active_session(client)
        label: str = call.data["label"]
        duration_sec: int = call.data["duration_sec"]
        step_index: int | None = call.data.get("step_index")

        import datetime
        new_timer: dict[str, Any] = {
            "label": label,
            "durationSec": duration_sec,
            "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if step_index is not None:
            new_timer["stepIndex"] = step_index

        existing_timers: list[dict[str, Any]] = list(session.get("timers", []))
        # Replace any timer with the same label (idempotent restart)
        existing_timers = [t for t in existing_timers if t.get("label") != label]
        existing_timers.append(new_timer)

        updated = await _patch_session(
            client,
            session["id"],
            {"timers": existing_timers},
        )
        entity_id = _timer_entity_id(session["id"], label)
        await _ha_timer_start(hass, entity_id, duration_sec)
        _LOGGER.info(
            "[culiplan] Recipe timer set: session=%s label=%s duration=%ds entity=%s",
            session["id"],
            label,
            duration_sec,
            entity_id,
        )
        hass.bus.async_fire(
            f"{DOMAIN}_recipe_timer_started",
            {
                "session_id": session["id"],
                "label": label,
                "duration_sec": duration_sec,
                "entity_id": entity_id,
            },
        )
        _ = updated  # session kept in sync via sync_ha_timers on next event

    # ── 4. cancel_recipe_timer ────────────────────────────────────────────────

    async def handle_cancel_recipe_timer(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        session = await _get_active_session(client)
        label_or_id: str = call.data["label_or_id"]

        existing_timers: list[dict[str, Any]] = list(session.get("timers", []))
        # Match by id or label
        to_cancel = [
            t for t in existing_timers
            if t.get("id") == label_or_id or t.get("label") == label_or_id
        ]
        if not to_cancel:
            raise HomeAssistantError(
                f"No timer with label or id '{label_or_id}' found in the active session."
            )

        remaining_timers = [
            t for t in existing_timers
            if t.get("id") != label_or_id and t.get("label") != label_or_id
        ]
        await _patch_session(client, session["id"], {"timers": remaining_timers})

        for timer in to_cancel:
            entity_id = _timer_entity_id(session["id"], timer.get("label", label_or_id))
            await _ha_timer_cancel(hass, entity_id)
            _LOGGER.info(
                "[culiplan] Recipe timer cancelled: session=%s label=%s entity=%s",
                session["id"],
                timer.get("label"),
                entity_id,
            )
        hass.bus.async_fire(
            f"{DOMAIN}_recipe_timer_cancelled",
            {
                "session_id": session["id"],
                "label_or_id": label_or_id,
            },
        )

    # ── 5. pause_cooking_mode ─────────────────────────────────────────────────

    async def handle_pause_cooking_mode(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        session = await _get_active_session(client)
        await _patch_session(client, session["id"], {"status": "paused"})
        _LOGGER.info("[culiplan] Cooking session paused: %s", session["id"])
        hass.bus.async_fire(
            f"{DOMAIN}_cooking_session_paused", {"session_id": session["id"]}
        )

    # ── 6. resume_cooking_mode ────────────────────────────────────────────────

    async def handle_resume_cooking_mode(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        # For resume the session might be in paused status, so query both
        try:
            sessions = await client.async_get(
                "/api/cooking-sessions?status=paused&limit=1"
            )
        except Exception as exc:
            raise HomeAssistantError(f"Failed to fetch paused session: {exc}") from exc

        if isinstance(sessions, list):
            items = sessions
        elif isinstance(sessions, dict):
            items = sessions.get("sessions", sessions.get("data", []))
        else:
            items = []

        if not items:
            raise HomeAssistantError(
                "No paused cooking session found. Nothing to resume."
            )

        session = items[0]
        updated = await _patch_session(client, session["id"], {"status": "active"})
        await sync_ha_timers(hass, updated)
        _LOGGER.info("[culiplan] Cooking session resumed: %s", session["id"])
        hass.bus.async_fire(
            f"{DOMAIN}_cooking_session_resumed", {"session_id": session["id"]}
        )

    # ── 7. complete_cooking_mode ──────────────────────────────────────────────

    async def handle_complete_cooking_mode(call: ServiceCall) -> None:
        client = _get_client(_find_entry_id())
        session = await _get_active_session(client)
        await _patch_session(client, session["id"], {"status": "completed"})

        # Cancel all remaining HA timers
        for timer in session.get("timers", []):
            entity_id = _timer_entity_id(session["id"], timer.get("label", "timer"))
            await _ha_timer_cancel(hass, entity_id)

        _LOGGER.info("[culiplan] Cooking session completed: %s", session["id"])
        hass.bus.async_fire(
            f"{DOMAIN}_cooking_session_completed", {"session_id": session["id"]}
        )

    # ─── Register all seven ───────────────────────────────────────────────────

    registrations = [
        (SERVICE_START_COOKING_MODE, handle_start_cooking_mode, START_COOKING_MODE_SCHEMA),
        (SERVICE_ADVANCE_COOKING_STEP, handle_advance_cooking_step, ADVANCE_COOKING_STEP_SCHEMA),
        (SERVICE_SET_RECIPE_TIMER, handle_set_recipe_timer, SET_RECIPE_TIMER_SCHEMA),
        (SERVICE_CANCEL_RECIPE_TIMER, handle_cancel_recipe_timer, CANCEL_RECIPE_TIMER_SCHEMA),
        (SERVICE_PAUSE_COOKING_MODE, handle_pause_cooking_mode, PAUSE_COOKING_MODE_SCHEMA),
        (SERVICE_RESUME_COOKING_MODE, handle_resume_cooking_mode, RESUME_COOKING_MODE_SCHEMA),
        (SERVICE_COMPLETE_COOKING_MODE, handle_complete_cooking_mode, COMPLETE_COOKING_MODE_SCHEMA),
    ]
    for name, handler, schema in registrations:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)

    _LOGGER.debug("[culiplan] Registered %d cooking-mode services", len(registrations))


def async_unregister_cooking_services(hass: HomeAssistant) -> None:
    """Unregister all cooking-mode HA services."""
    for name in COOKING_SERVICES:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
