"""
Debug-mode prompt logging with enforced 24h TTL (task-1410).

When the user enables AI debug mode, prompt content is logged client-side to
a dedicated rotating log file under HA's config directory.  Files older than
24 hours are automatically purged on a periodic timer.

Architecture (§13.2):
    - Logs are stored ONLY on the local HA install — never sent to Culiplan.
    - The file rotates at midnight; backupCount=1 keeps at most two files on disk
      (today's and yesterday's).
    - An HA async_track_time_interval job removes files older than 24h.
    - BYOK keys are NEVER written to these logs.

Privacy guarantee:
    - Prompt *content* is logged only when the user explicitly enables debug
      mode in the integration options.
    - Logs are purged automatically after 24h even if the user forgets to
      disable debug mode.
    - The purge mechanism runs hourly inside HA's event loop so it works
      without any external cron job.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Name prefix for debug log files inside the HA config directory
_DEBUG_LOG_FILENAME = "culiplan_ai_debug.log"

# How long before a debug log file is considered stale (in seconds)
_TTL_SECONDS: float = 24 * 3600  # 24 hours

# How often the purge job runs
_PURGE_INTERVAL_SECONDS: int = 3600  # 1 hour

# Internal cache: config_dir → FileHandler so we don't add duplicate
# handlers each time a dispatcher is created.
_debug_handler_cache: dict[str, logging.handlers.TimedRotatingFileHandler] = {}


def get_debug_logger(config_dir: str) -> logging.Logger:
    """
    Return a Logger that writes debug-tagged records to a dedicated rotating
    file under *config_dir*.

    The logger is named ``culiplan.ai.debug`` and writes to
    ``<config_dir>/culiplan_ai_debug.log``.  The handler rotates at midnight
    and keeps at most 1 backup (yesterday's file), giving a natural 24h window
    before files are rotated away.

    Args:
        config_dir: HA's config directory (``hass.config.config_dir``).

    Returns:
        The dedicated debug logger (separate from the integration's main logger
        so prompt content doesn't appear in the main HA log stream).
    """
    logger = logging.getLogger("culiplan.ai.debug")
    logger.setLevel(logging.DEBUG)
    # Prevent propagation to root logger — keep debug content off the main log
    logger.propagate = False

    if config_dir not in _debug_handler_cache:
        log_path = Path(config_dir) / _DEBUG_LOG_FILENAME
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_path),
            when="midnight",
            interval=1,
            backupCount=1,  # keep max 1 backup (yesterday); today rotates out
            encoding="utf-8",
            utc=True,
        )
        handler.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        _debug_handler_cache[config_dir] = handler

    return logger


def purge_old_debug_logs(config_dir: str) -> int:
    """
    Remove debug log files in *config_dir* that are older than 24 hours.

    Called by the periodic HA timer (see setup_debug_log_purge).  Also
    removes any rotated backup files that the TimedRotatingFileHandler
    left behind.

    Returns:
        Number of files deleted.
    """
    config_path = Path(config_dir)
    deleted = 0
    cutoff = time.time() - _TTL_SECONDS

    # Match both the active log and any rotated backups
    # TimedRotatingFileHandler names backups like: culiplan_ai_debug.log.2026-04-25
    for candidate in config_path.glob("culiplan_ai_debug.log*"):
        try:
            mtime = candidate.stat().st_mtime
            if mtime < cutoff:
                candidate.unlink()
                deleted += 1
                _LOGGER.debug(
                    "[culiplan][debug-logger] Purged stale debug log: %s (age=%.1fh)",
                    candidate.name,
                    (time.time() - mtime) / 3600,
                )
        except OSError as err:
            _LOGGER.warning(
                "[culiplan][debug-logger] Failed to purge %s: %s",
                candidate.name,
                err,
            )
    return deleted


def setup_debug_log_purge(hass: "HomeAssistant") -> None:
    """
    Register an HA periodic callback to purge stale debug log files.

    Called once from _run_byok_or_local_intent when debug AI mode is active.
    The callback fires every hour and removes any debug log files older than 24h.

    This function is safe to call multiple times — it checks if the tracker
    is already registered via hass.data.

    Args:
        hass: Home Assistant instance.
    """
    from homeassistant.helpers.event import async_track_time_interval

    marker = "culiplan_debug_purge_registered"
    if hass.data.get(marker):
        return

    config_dir = hass.config.config_dir

    def _purge_callback(now: datetime) -> None:  # type: ignore[type-arg]
        """Periodic callback to purge old debug logs."""
        deleted = purge_old_debug_logs(config_dir)
        if deleted:
            _LOGGER.info(
                "[culiplan][debug-logger] Purged %d stale debug log file(s) "
                "(TTL=24h)",
                deleted,
            )

    cancel = async_track_time_interval(
        hass,
        _purge_callback,
        timedelta(seconds=_PURGE_INTERVAL_SECONDS),
    )
    hass.data[marker] = cancel
    _LOGGER.debug(
        "[culiplan][debug-logger] Scheduled debug log purge every %dh.",
        _PURGE_INTERVAL_SECONDS // 3600,
    )
