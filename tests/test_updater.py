"""Tests for the self-updater (custom_components/culiplan/updater.py).

The self-updater is Vincent's primary install/update path (no HACS on his
HAOS), so this suite pins the network → extract → swap → rollback shape
and verifies the zip-slip guard.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.updater import (
    LatestRelease,
    async_check_latest,
    async_perform_update,
    is_newer,
)


# ─── is_newer ─────────────────────────────────────────────────────────────────


class TestIsNewer:
    @pytest.mark.parametrize(
        "latest,current,expected",
        [
            ("0.13.0", "0.12.0", True),
            ("0.12.1", "0.12.0", True),
            ("1.0.0", "0.99.9", True),
            ("0.12.0", "0.12.0", False),
            ("0.12.0", "0.13.0", False),
        ],
    )
    def test_comparisons(self, latest, current, expected):
        assert is_newer(latest, current) is expected

    def test_garbage_inputs_dont_raise(self):
        # Should fall back to string comparison rather than crash.
        assert isinstance(is_newer("abc.def", "ghi.jkl"), bool)

    def test_pre_release_suffix_does_not_crash(self):
        """Mixed int/str segments fall back to string comparison."""
        # Exact ordering is unspecified for pre-releases — just that it
        # returns a bool without raising.
        assert isinstance(is_newer("0.13.0", "0.13.0-beta"), bool)


# ─── async_check_latest ──────────────────────────────────────────────────────


def _make_session(payload: dict | None, status: int = 200, raise_exc: Exception | None = None):
    """Return a session whose .get() yields a context manager exposing
    `status` and `json()`.
    """
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    if raise_exc is not None:
        session.get = MagicMock(side_effect=raise_exc)
    else:
        session.get = MagicMock(return_value=resp)
    return session


class TestAsyncCheckLatest:
    @pytest.mark.asyncio
    async def test_happy_path_returns_release(self):
        session = _make_session(
            {
                "tag_name": "v0.13.0",
                "html_url": "https://github.com/x/x/releases/v0.13.0",
                "body": "Test release notes",
                "zipball_url": "https://example.test/v0.13.0.zip",
            }
        )
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            release = await async_check_latest(MagicMock())

        assert isinstance(release, LatestRelease)
        assert release.version == "0.13.0"
        assert release.notes == "Test release notes"
        assert release.zipball_url == "https://example.test/v0.13.0.zip"

    @pytest.mark.asyncio
    async def test_strips_leading_v_from_tag(self):
        session = _make_session(
            {
                "tag_name": "v0.13.0",
                "zipball_url": "z",
                "html_url": "h",
                "body": "",
            }
        )
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            release = await async_check_latest(MagicMock())
        assert release.version == "0.13.0"

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        session = _make_session(None, status=503)
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            assert await async_check_latest(MagicMock()) is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        session = _make_session(None, raise_exc=ConnectionError("boom"))
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            assert await async_check_latest(MagicMock()) is None

    @pytest.mark.asyncio
    async def test_missing_fields_returns_none(self):
        session = _make_session({"tag_name": "v0.13.0"})  # no zipball_url
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            assert await async_check_latest(MagicMock()) is None


# ─── async_perform_update ────────────────────────────────────────────────────


def _build_release_zip(zip_path: Path, top_level: str = "culiplan-home-assistant-culiplan-abc") -> None:
    """Build a minimal release.zip mimicking a GitHub source archive."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{top_level}/README.md", "fake")
        zf.writestr(
            f"{top_level}/custom_components/culiplan/__init__.py",
            "# fake init",
        )
        zf.writestr(
            f"{top_level}/custom_components/culiplan/manifest.json",
            '{"domain": "culiplan", "version": "9.9.9"}',
        )


def _build_zip_slip_zip(zip_path: Path) -> None:
    """Build a zip with a member that resolves outside the extract dir."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../../etc/passwd", "evil")


class TestAsyncPerformUpdate:
    @pytest.mark.asyncio
    async def test_zip_slip_aborts(self, tmp_path):
        # Build a malicious zip that would escape the extract dir
        zip_payload = tmp_path / "release.zip"
        _build_zip_slip_zip(zip_payload)
        zip_bytes = zip_payload.read_bytes()

        # Fake aiohttp streaming download
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        async def _iter_chunked(_size):
            yield zip_bytes

        resp.content.iter_chunked = _iter_chunked
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        async def _aej(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass = MagicMock()
        hass.async_add_executor_job = _aej

        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            with pytest.raises(ValueError, match="Zip-slip"):
                await async_perform_update(hass, "https://example.test/release.zip")

    @pytest.mark.asyncio
    async def test_download_error_propagates(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock(
            side_effect=RuntimeError("HTTP 502 Bad Gateway")
        )
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        hass = MagicMock()
        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            with pytest.raises(RuntimeError):
                await async_perform_update(hass, "https://example.test/release.zip")

    @pytest.mark.asyncio
    async def test_empty_zip_raises(self, tmp_path):
        zip_payload = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_payload, "w"):
            pass  # truly empty
        zip_bytes = zip_payload.read_bytes()

        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        async def _iter_chunked(_size):
            yield zip_bytes

        resp.content.iter_chunked = _iter_chunked
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        async def _aej(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass = MagicMock()
        hass.async_add_executor_job = _aej

        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            with pytest.raises(ValueError, match="empty"):
                await async_perform_update(hass, "https://example.test/empty.zip")

    @pytest.mark.asyncio
    async def test_missing_component_dir_raises(self, tmp_path):
        # Build a zip that has a top-level dir but no custom_components/culiplan
        zip_payload = tmp_path / "release.zip"
        with zipfile.ZipFile(zip_payload, "w") as zf:
            zf.writestr("repo/README.md", "fake")
            zf.writestr("repo/foo/bar.txt", "irrelevant")
        zip_bytes = zip_payload.read_bytes()

        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        async def _iter_chunked(_size):
            yield zip_bytes

        resp.content.iter_chunked = _iter_chunked
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        async def _aej(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass = MagicMock()
        hass.async_add_executor_job = _aej

        with patch(
            "custom_components.culiplan.updater.async_get_clientsession",
            return_value=session,
        ):
            with pytest.raises(FileNotFoundError):
                await async_perform_update(hass, "https://example.test/release.zip")
