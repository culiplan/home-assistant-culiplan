"""Self-updater for the Culiplan Home Assistant integration.

Downloads the latest release from GitHub, replaces the integration's own
files on disk with a backup/rollback safety net, and lets the caller trigger
a HA restart to apply the new code.

Design notes
------------
* All blocking I/O (zipfile extraction, shutil operations, Path operations)
  runs via ``hass.async_add_executor_job`` so the event loop is never blocked.
* Network download uses the HA shared ``aiohttp.ClientSession`` obtained via
  ``async_get_clientsession(hass)`` (Platinum rule ``inject-websession``).
* Zip-slip is guarded by resolving every extracted entry path relative to
  the temp directory and asserting it stays inside.
* The integration directory is backed up to ``<dir>.bak`` before the swap;
  any failure after that point restores from ``.bak``.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

_GITHUB_LATEST_URL = (
    "https://api.github.com/repos/culiplan/home-assistant-culiplan/releases/latest"
)

# Timeout for the GitHub API call and the zip download
_API_TIMEOUT = aiohttp.ClientTimeout(total=15)
_DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120)

# Size of chunks written to disk during streaming download (64 KiB)
_CHUNK_SIZE = 65536


@dataclass
class LatestRelease:
    """Metadata for the latest GitHub release."""

    version: str
    html_url: str
    notes: str
    zipball_url: str


async def async_check_latest(hass: HomeAssistant) -> LatestRelease | None:
    """Fetch the latest release from GitHub.

    Returns a :class:`LatestRelease` if the API call succeeds and the
    response contains the expected fields, or ``None`` on any network /
    parse error (logged at DEBUG level so it does not clutter production
    logs).
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            _GITHUB_LATEST_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=_API_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug(
                    "[culiplan][updater] GitHub releases API returned HTTP %s",
                    resp.status,
                )
                return None
            data = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug(
            "[culiplan][updater] Could not reach GitHub releases API: %s", exc
        )
        return None

    try:
        tag: str = str(data["tag_name"])
        version = tag.lstrip("v")
        html_url: str = str(data.get("html_url", ""))
        notes: str = str(data.get("body") or "")
        zipball_url: str = str(data["zipball_url"])
    except (KeyError, TypeError) as exc:
        _LOGGER.debug(
            "[culiplan][updater] Unexpected GitHub API response shape: %s", exc
        )
        return None

    return LatestRelease(
        version=version,
        html_url=html_url,
        notes=notes,
        zipball_url=zipball_url,
    )


def is_newer(latest: str, current: str) -> bool:
    """Return True if *latest* is strictly newer than *current*.

    Compares dotted semver strings numerically (e.g. "0.6.0" > "0.5.0").
    Non-numeric segments are compared lexicographically so the function
    degrades gracefully rather than raising on pre-release suffixes.
    """

    def _to_tuple(v: str) -> tuple[int | str, ...]:
        parts: list[int | str] = []
        for seg in v.strip().split("."):
            try:
                parts.append(int(seg))
            except ValueError:
                parts.append(seg)
        return tuple(parts)

    try:
        return _to_tuple(latest) > _to_tuple(current)
    except TypeError:
        # Mixed int/str comparison fallback — compare raw strings
        return latest > current


async def async_perform_update(hass: HomeAssistant, zipball_url: str) -> None:
    """Download and apply the update from *zipball_url*.

    Steps
    -----
    1. Stream the zip to a temporary file (async, uses HA client session).
    2. Extract to a temp directory in the executor, locate the
       ``custom_components/culiplan/`` subtree inside the zip.
    3. Back up the current integration directory by renaming it to
       ``<dir>.bak`` (any stale ``.bak`` is removed first).
    4. Copy the extracted subtree into the target location.
    5. On success remove ``.bak``; on any failure restore from ``.bak``.

    Raises
    ------
    Exception
        Re-raised after rollback so the caller can surface an error to the UI.
    """
    target_dir = Path(__file__).parent
    backup_dir = target_dir.with_suffix(".bak")

    # ── 1. Download the zip to a temp file (async, non-blocking) ──────────────
    with tempfile.TemporaryDirectory() as tmp_root:
        tmp_root_path = Path(tmp_root)
        zip_path = tmp_root_path / "release.zip"

        session = async_get_clientsession(hass)
        _LOGGER.info(
            "[culiplan][updater] Downloading release zip from %s", zipball_url
        )
        try:
            async with session.get(
                zipball_url,
                timeout=_DOWNLOAD_TIMEOUT,
                allow_redirects=True,
            ) as resp:
                resp.raise_for_status()
                with zip_path.open("wb") as fh:
                    async for chunk in resp.content.iter_chunked(_CHUNK_SIZE):
                        fh.write(chunk)
        except Exception as exc:
            _LOGGER.error("[culiplan][updater] Download failed: %s", exc)
            raise

        # ── 2. Extract + locate custom_components/culiplan/ (executor) ────────
        extract_dir = tmp_root_path / "extracted"

        def _extract_and_locate() -> Path:
            """Blocking: extract zip and return path to culiplan component dir."""
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zf:
                # Zip-slip guard: every member must resolve to a path that
                # stays inside extract_dir. Use is_relative_to (not a string
                # prefix, which a sibling like ".../extractedX" could defeat).
                extract_root = extract_dir.resolve()
                for member in zf.infolist():
                    member_path = (extract_dir / member.filename).resolve()
                    if not member_path.is_relative_to(extract_root):
                        raise ValueError(
                            f"Zip-slip detected for member: {member.filename}"
                        )
                zf.extractall(extract_dir)

            # The top-level entry is something like
            # "culiplan-home-assistant-culiplan-<sha>/"
            top_level_dirs = [
                p for p in extract_dir.iterdir() if p.is_dir()
            ]
            if not top_level_dirs:
                raise ValueError("Zip archive appears to be empty")
            repo_root = top_level_dirs[0]

            component_src = repo_root / "custom_components" / "culiplan"
            if not component_src.is_dir():
                raise FileNotFoundError(
                    f"custom_components/culiplan/ not found inside zip at {component_src}"
                )
            return component_src

        try:
            component_src = await hass.async_add_executor_job(_extract_and_locate)
        except Exception as exc:
            _LOGGER.error("[culiplan][updater] Extraction failed: %s", exc)
            raise

        # ── 3. Backup current dir + 4. Copy new files (executor) ──────────────
        def _swap() -> None:
            """Blocking: back up current dir and replace with extracted files."""
            # Remove stale backup if it exists
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

            # Rename target → .bak (atomic on same filesystem)
            target_dir.rename(backup_dir)

            try:
                shutil.copytree(component_src, target_dir)
            except Exception:
                # Restore from backup
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                backup_dir.rename(target_dir)
                raise

            # Success — remove backup
            shutil.rmtree(backup_dir)

        try:
            await hass.async_add_executor_job(_swap)
        except Exception as exc:
            _LOGGER.error(
                "[culiplan][updater] File swap failed (rolled back to backup): %s",
                exc,
            )
            raise

    _LOGGER.info("[culiplan][updater] Update applied successfully. Restart required.")
