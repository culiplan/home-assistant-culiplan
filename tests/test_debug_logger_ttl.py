"""
Tests for debug-mode prompt logging with enforced 24h TTL (task-1410).

Covers:
  AC#1 — get_debug_logger returns a Logger with a TimedRotatingFileHandler
          and propagate=False.
  AC#2 — purge_old_debug_logs deletes files older than 24h and leaves
          recent files untouched.
  AC#3 — strings.json contains accurate 24h-TTL description copy.
  AC#4 — setup_debug_log_purge is idempotent (does not register twice).
  AC#5 — get_debug_logger is idempotent (same config_dir returns same
          handler, not a duplicate).
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import pathlib
import time
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STRINGS_JSON = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "culiplan"
    / "strings.json"
)


# ---------------------------------------------------------------------------
# AC#1 — get_debug_logger attaches TimedRotatingFileHandler
# ---------------------------------------------------------------------------


def test_get_debug_logger_returns_logger_with_file_handler(tmp_path):
    """get_debug_logger() must return a Logger with a TimedRotatingFileHandler."""
    from custom_components.culiplan.ai.debug_logger import (
        _debug_handler_cache,
        get_debug_logger,
    )

    # Clear the module-level cache so we get a fresh handler
    _debug_handler_cache.clear()

    logger = get_debug_logger(str(tmp_path))

    assert logger.name == "culiplan.ai.debug"
    assert logger.propagate is False

    file_handlers = [
        h
        for h in logger.handlers
        if isinstance(h, logging.handlers.TimedRotatingFileHandler)
    ]
    assert len(file_handlers) >= 1, "Expected at least one TimedRotatingFileHandler"

    handler = file_handlers[0]
    assert "culiplan_ai_debug" in handler.baseFilename
    assert handler.when.upper() == "MIDNIGHT"
    assert handler.backupCount == 1


# ---------------------------------------------------------------------------
# AC#5 — get_debug_logger is idempotent
# ---------------------------------------------------------------------------


def test_get_debug_logger_idempotent(tmp_path):
    """Calling get_debug_logger twice with the same dir must not add a second handler."""
    from custom_components.culiplan.ai.debug_logger import (
        _debug_handler_cache,
        get_debug_logger,
    )

    _debug_handler_cache.clear()

    logger1 = get_debug_logger(str(tmp_path))
    handler_count_after_first = len(
        [
            h
            for h in logger1.handlers
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        ]
    )

    logger2 = get_debug_logger(str(tmp_path))
    handler_count_after_second = len(
        [
            h
            for h in logger2.handlers
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        ]
    )

    assert logger1 is logger2
    assert handler_count_after_second == handler_count_after_first


# ---------------------------------------------------------------------------
# AC#2 — purge_old_debug_logs deletes stale files, keeps recent ones
# ---------------------------------------------------------------------------


def test_purge_old_debug_logs_deletes_stale_files(tmp_path):
    """purge_old_debug_logs() must delete files older than 24h."""
    from custom_components.culiplan.ai.debug_logger import purge_old_debug_logs

    stale = tmp_path / "culiplan_ai_debug.log.2026-01-01"
    stale.write_text("old log content")
    # Set mtime to 25 hours ago
    old_mtime = time.time() - (25 * 3600)
    os.utime(stale, (old_mtime, old_mtime))

    deleted = purge_old_debug_logs(str(tmp_path))

    assert deleted == 1
    assert not stale.exists()


def test_purge_old_debug_logs_keeps_recent_files(tmp_path):
    """purge_old_debug_logs() must NOT delete files younger than 24h."""
    from custom_components.culiplan.ai.debug_logger import purge_old_debug_logs

    recent = tmp_path / "culiplan_ai_debug.log"
    recent.write_text("recent log content")
    # mtime is now (file was just created)

    deleted = purge_old_debug_logs(str(tmp_path))

    assert deleted == 0
    assert recent.exists()


def test_purge_old_debug_logs_returns_correct_count(tmp_path):
    """purge_old_debug_logs() returns the number of deleted files."""
    from custom_components.culiplan.ai.debug_logger import purge_old_debug_logs

    # Two stale files
    for name in (
        "culiplan_ai_debug.log.2026-01-01",
        "culiplan_ai_debug.log.2026-01-02",
    ):
        f = tmp_path / name
        f.write_text("stale")
        old_mtime = time.time() - (30 * 3600)
        os.utime(f, (old_mtime, old_mtime))

    # One fresh file
    fresh = tmp_path / "culiplan_ai_debug.log"
    fresh.write_text("fresh")

    deleted = purge_old_debug_logs(str(tmp_path))
    assert deleted == 2
    assert fresh.exists()


# ---------------------------------------------------------------------------
# AC#4 — setup_debug_log_purge is idempotent
# ---------------------------------------------------------------------------


def test_setup_debug_log_purge_idempotent():
    """setup_debug_log_purge() must not register a second callback if already done."""
    from custom_components.culiplan.ai import debug_logger

    hass = MagicMock()
    hass.config.config_dir = "/tmp/ha_config"

    call_count = 0

    def fake_track(hass_arg, callback, interval):
        nonlocal call_count
        call_count += 1
        return MagicMock()  # cancel handle

    with patch(
        "custom_components.culiplan.ai.debug_logger.async_track_time_interval",
        side_effect=fake_track,
    ):
        # First call: marker absent — should register
        hass.data = {}
        debug_logger.setup_debug_log_purge(hass)
        # Second call: marker present — should be a no-op
        debug_logger.setup_debug_log_purge(hass)

    assert call_count == 1, (
        "async_track_time_interval must be called exactly once even if "
        "setup_debug_log_purge is called multiple times"
    )


# ---------------------------------------------------------------------------
# AC#3 — strings.json contains accurate 24h-TTL copy
# ---------------------------------------------------------------------------


def test_strings_json_has_24h_ttl_description():
    """strings.json ai_provider description must mention '24 hours' or '24h'."""
    assert STRINGS_JSON.exists(), f"strings.json not found at {STRINGS_JSON}"
    data = json.loads(STRINGS_JSON.read_text(encoding="utf-8"))
    description = (
        data.get("config", {})
        .get("step", {})
        .get("ai_provider", {})
        .get("description", "")
    )
    assert "24" in description, (
        "ai_provider description in strings.json must mention the 24-hour TTL"
    )
    # Also check that the log file name is mentioned
    assert "culiplan_ai_debug" in description, (
        "ai_provider description must mention the debug log file name"
    )
