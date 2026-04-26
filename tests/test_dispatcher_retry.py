"""
Unit tests for task-1411: retry-once on provider 5xx in dispatchers.

AC#1 — All three dispatchers retry once on 5xx with 1s backoff
AC#2 — No retry on 4xx (fail fast)
AC#3 — Retry logged at WARN for audit visibility
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ─── _retry_once_on_5xx helper ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_once_on_5xx_succeeds_on_second_attempt():
    """Should return the result of the second call if the first raises 5xx."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import ProviderUnavailableError

    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ProviderUnavailableError("503 service unavailable")
        return "success"

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await _retry_once_on_5xx(factory, provider="test")

    assert result == "success"
    assert call_count == 2
    # Must wait the configured backoff before retrying (AC#1)
    mock_sleep.assert_called_once_with(1.0)


@pytest.mark.asyncio
async def test_retry_once_on_5xx_raises_on_second_5xx():
    """If both attempts return 5xx, the second exception should propagate."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import ProviderUnavailableError

    async def factory():
        raise ProviderUnavailableError("503 still down")

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ProviderUnavailableError):
            await _retry_once_on_5xx(factory, provider="test")


@pytest.mark.asyncio
async def test_retry_once_no_retry_on_auth_error():
    """4xx ProviderAuthError must NOT be retried (AC#2 fail fast)."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import ProviderAuthError

    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        raise ProviderAuthError("401 invalid key")

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(ProviderAuthError):
            await _retry_once_on_5xx(factory, provider="test")

    # Must have been called exactly once — no retry (AC#2)
    assert call_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_retry_once_no_retry_on_rate_limit_error():
    """429 ProviderRateLimitError must NOT be retried (AC#2 fail fast)."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import ProviderRateLimitError

    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        raise ProviderRateLimitError("429 rate limited")

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(ProviderRateLimitError):
            await _retry_once_on_5xx(factory, provider="test")

    assert call_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_retry_once_no_retry_on_dispatcher_error():
    """Generic DispatcherError (e.g. 400 bad request) must NOT be retried."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import DispatcherError

    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        raise DispatcherError("400 bad request")

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(DispatcherError):
            await _retry_once_on_5xx(factory, provider="test")

    assert call_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_retry_once_succeeds_without_error():
    """If the first call succeeds, no retry and no sleep."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx

    async def factory():
        return {"result": "ok"}

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await _retry_once_on_5xx(factory, provider="test")

    assert result == {"result": "ok"}
    mock_sleep.assert_not_called()


# ─── AC#3: retry logged at WARN ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_logs_warning():
    """Retry attempt must be logged at WARN level (AC#3)."""
    from custom_components.culiplan.ai.dispatchers import _retry_once_on_5xx
    from custom_components.culiplan.ai.types import ProviderUnavailableError

    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ProviderUnavailableError("503 unavailable")
        return "ok"

    with patch("custom_components.culiplan.ai.dispatchers.asyncio.sleep", new_callable=AsyncMock):
        with patch("custom_components.culiplan.ai.dispatchers._LOGGER") as mock_logger:
            await _retry_once_on_5xx(factory, provider="mytest")

            # AC#3: warning should mention the provider name
            warned = any(
                "mytest" in str(c) for c in mock_logger.warning.call_args_list
            )
            assert warned, f"Expected 'mytest' in warning logs, got: {mock_logger.warning.call_args_list}"
