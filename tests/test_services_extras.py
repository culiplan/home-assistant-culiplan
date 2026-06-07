"""Coverage for services.py — branches not exercised by test_services
and test_phase2_services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.culiplan.ai.types import PremiumRequiredError


# ─── _build_dispatch_mode ────────────────────────────────────────────────────


def test_build_dispatch_mode_byok_openai():
    from custom_components.culiplan.const import AI_MODE_BYOK, CONF_BYOK_PROVIDER
    from custom_components.culiplan.services import _build_dispatch_mode

    assert (
        _build_dispatch_mode(AI_MODE_BYOK, {CONF_BYOK_PROVIDER: "openai"})
        == "byok-openai"
    )


def test_build_dispatch_mode_byok_google_maps_to_gemini():
    from custom_components.culiplan.const import AI_MODE_BYOK, CONF_BYOK_PROVIDER
    from custom_components.culiplan.services import _build_dispatch_mode

    assert (
        _build_dispatch_mode(AI_MODE_BYOK, {CONF_BYOK_PROVIDER: "google"})
        == "byok-gemini"
    )


def test_build_dispatch_mode_local_ollama():
    from custom_components.culiplan.const import AI_MODE_LOCAL, CONF_LOCAL_ENDPOINT
    from custom_components.culiplan.services import _build_dispatch_mode

    assert (
        _build_dispatch_mode(
            AI_MODE_LOCAL, {CONF_LOCAL_ENDPOINT: "http://localhost:11434"}
        )
        == "local-ollama"
    )


def test_build_dispatch_mode_local_lmstudio():
    from custom_components.culiplan.const import AI_MODE_LOCAL, CONF_LOCAL_ENDPOINT
    from custom_components.culiplan.services import _build_dispatch_mode

    assert (
        _build_dispatch_mode(
            AI_MODE_LOCAL, {CONF_LOCAL_ENDPOINT: "http://localhost:1234"}
        )
        == "local-lmstudio"
    )


def test_build_dispatch_mode_local_endpoint_parse_failure():
    """A garbage endpoint string falls back to local-ollama."""
    from custom_components.culiplan.const import AI_MODE_LOCAL, CONF_LOCAL_ENDPOINT
    from custom_components.culiplan.services import _build_dispatch_mode

    assert (
        _build_dispatch_mode(
            AI_MODE_LOCAL, {CONF_LOCAL_ENDPOINT: "completely-garbage"}
        )
        == "local-ollama"
    )


def test_build_dispatch_mode_cloud_passthrough():
    from custom_components.culiplan.const import AI_MODE_CLOUD
    from custom_components.culiplan.services import _build_dispatch_mode

    assert _build_dispatch_mode(AI_MODE_CLOUD, {}) == AI_MODE_CLOUD


# ─── _call_pantry_decrement error paths ──────────────────────────────────────


@pytest.mark.asyncio
async def test_pantry_decrement_404_raises_item_not_found():
    from custom_components.culiplan.services import (
        PantryItemNotFoundError,
        _call_pantry_decrement,
    )

    client = MagicMock()
    client.async_post = AsyncMock(
        side_effect=Exception("404 PANTRY_ITEM_NOT_FOUND")
    )
    with pytest.raises(PantryItemNotFoundError):
        await _call_pantry_decrement(client, "1234567890123", 1.0)


@pytest.mark.asyncio
async def test_pantry_decrement_422_raises_insufficient_stock():
    from custom_components.culiplan.services import (
        InsufficientStockError,
        _call_pantry_decrement,
    )

    client = MagicMock()
    client.async_post = AsyncMock(
        side_effect=Exception('422 INSUFFICIENT_STOCK {"available": 0.5}')
    )
    with pytest.raises(InsufficientStockError) as excinfo:
        await _call_pantry_decrement(client, "1234567890123", 2.0)
    # available was parsed from the JSON body
    assert excinfo.value.translation_placeholders["available"] == "0.5"


@pytest.mark.asyncio
async def test_pantry_decrement_422_unparseable_body():
    """A 422 with non-JSON body still raises InsufficientStockError with available=0."""
    from custom_components.culiplan.services import (
        InsufficientStockError,
        _call_pantry_decrement,
    )

    client = MagicMock()
    client.async_post = AsyncMock(side_effect=Exception("422 INSUFFICIENT_STOCK"))
    with pytest.raises(InsufficientStockError):
        await _call_pantry_decrement(client, "1234567890123", 1.0)


@pytest.mark.asyncio
async def test_pantry_decrement_other_error_wraps():
    from custom_components.culiplan.services import _call_pantry_decrement

    client = MagicMock()
    client.async_post = AsyncMock(side_effect=RuntimeError("backend down"))
    with pytest.raises(HomeAssistantError):
        await _call_pantry_decrement(client, "1234567890123", 1.0)


# ─── _call_scale_servings error paths ────────────────────────────────────────


@pytest.mark.asyncio
async def test_scale_servings_with_plan_date():
    from custom_components.culiplan.services import _call_scale_servings

    client = MagicMock()
    client.async_post = AsyncMock(return_value={"success": True})
    await _call_scale_servings(client, 3, "2026-06-07")
    payload = client.async_post.call_args[0][1]
    assert payload["plan_date"] == "2026-06-07"


@pytest.mark.asyncio
async def test_scale_servings_other_error_wraps():
    from custom_components.culiplan.services import _call_scale_servings

    client = MagicMock()
    client.async_post = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HomeAssistantError):
        await _call_scale_servings(client, 3, None)


@pytest.mark.asyncio
async def test_scale_servings_premium_propagates():
    from custom_components.culiplan.services import _call_scale_servings

    client = MagicMock()
    client.async_post = AsyncMock(
        side_effect=PremiumRequiredError(feature="x", upgrade_url="https://x")
    )
    with pytest.raises(PremiumRequiredError):
        await _call_scale_servings(client, 3, None)


# ─── _call_pantry_expiring error paths ──────────────────────────────────────


@pytest.mark.asyncio
async def test_pantry_expiring_error_wraps():
    from custom_components.culiplan.services import _call_pantry_expiring

    client = MagicMock()
    client._get = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HomeAssistantError):
        await _call_pantry_expiring(client, 48)


# ─── async_unregister_services ───────────────────────────────────────────────


def test_async_unregister_services_removes_all():
    from custom_components.culiplan.services import async_unregister_services

    hass = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_remove = MagicMock()
    async_unregister_services(hass)
    # 6 services registered → 6 removed
    assert hass.services.async_remove.call_count == 6


def test_async_unregister_services_skips_already_removed():
    from custom_components.culiplan.services import async_unregister_services

    hass = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_remove = MagicMock()
    async_unregister_services(hass)
    hass.services.async_remove.assert_not_called()
