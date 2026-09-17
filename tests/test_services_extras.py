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
        _build_dispatch_mode(AI_MODE_LOCAL, {CONF_LOCAL_ENDPOINT: "completely-garbage"})
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
    client.async_post = AsyncMock(side_effect=Exception("404 PANTRY_ITEM_NOT_FOUND"))
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


# ─── _call_pantry_add ────────────────────────────────────────────────────────


def _pantry_add_client(**kwargs):
    client = MagicMock()
    client.async_add_pantry_item = AsyncMock(**kwargs)
    return client


@pytest.mark.asyncio
async def test_pantry_add_forwards_all_fields_and_returns_envelope():
    from custom_components.culiplan.services import _call_pantry_add

    envelope = {"success": True, "data": {"name": "milk"}, "speakableResponse": "ok"}
    client = _pantry_add_client(return_value=envelope)
    result = await _call_pantry_add(
        client,
        "milk",
        quantity=2.0,
        unit="l",
        location="fridge",
        expiration_days=5,
        language="nl",
    )
    assert result is envelope
    client.async_add_pantry_item.assert_awaited_once_with(
        "milk", quantity=2.0, unit="l", location="fridge", expiration_days=5, language="nl"
    )


@pytest.mark.asyncio
async def test_pantry_add_transport_error_wraps_with_translation_key():
    from custom_components.culiplan.services import _call_pantry_add

    client = _pantry_add_client(side_effect=RuntimeError("backend down"))
    with pytest.raises(HomeAssistantError) as excinfo:
        await _call_pantry_add(client, "milk")
    assert excinfo.value.translation_key == "pantry_add_failed"
    assert excinfo.value.translation_placeholders["name"] == "milk"
    assert "backend down" in excinfo.value.translation_placeholders["error"]


@pytest.mark.asyncio
async def test_pantry_add_success_false_raises():
    """The voice executor reports a rejected tool call as HTTP 200 success:false."""
    from custom_components.culiplan.services import _call_pantry_add

    client = _pantry_add_client(
        return_value={"success": False, "speakableResponse": "Sorry, something went wrong."}
    )
    with pytest.raises(HomeAssistantError) as excinfo:
        await _call_pantry_add(client, "milk")
    assert excinfo.value.translation_key == "pantry_add_failed"
    assert "Sorry, something went wrong." in excinfo.value.translation_placeholders["error"]


@pytest.mark.asyncio
async def test_pantry_add_typed_ha_errors_propagate_unwrapped():
    from homeassistant.exceptions import ConfigEntryAuthFailed

    from custom_components.culiplan.services import _call_pantry_add

    client = _pantry_add_client(side_effect=ConfigEntryAuthFailed("401"))
    with pytest.raises(ConfigEntryAuthFailed):
        await _call_pantry_add(client, "milk")


# ─── pantry_add service handler ──────────────────────────────────────────────


def _pantry_add_handler(hass):
    from custom_components.culiplan.services import (
        SERVICE_PANTRY_ADD,
        async_register_services,
    )

    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register = MagicMock()
    async_register_services(hass)
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SERVICE_PANTRY_ADD:
            return call.args[2], call.kwargs["schema"]
    raise AssertionError("pantry_add service was not registered")


def test_pantry_add_schema_defaults_and_validation():
    import voluptuous as vol

    from custom_components.culiplan.services import PANTRY_ADD_SCHEMA

    validated = PANTRY_ADD_SCHEMA({"name": "milk"})
    assert validated["location"] == "pantry"
    validated = PANTRY_ADD_SCHEMA(
        {"name": "milk", "quantity": "2", "unit": "l", "location": "fridge", "expiration_days": "7"}
    )
    assert validated["quantity"] == 2.0
    assert validated["expiration_days"] == 7
    with pytest.raises(vol.Invalid):
        PANTRY_ADD_SCHEMA({"name": "milk", "location": "garage"})
    with pytest.raises(vol.Invalid):
        PANTRY_ADD_SCHEMA({"quantity": 1})


@pytest.mark.asyncio
async def test_handle_pantry_add_calls_client_with_ha_language():
    client = _pantry_add_client(
        return_value={
            "success": True,
            "data": {"name": "milk", "quantity": 2, "unit": "l", "location": "fridge"},
        }
    )
    hass = MagicMock()
    hass.data = {"culiplan": {"entry1": {"client": client}}}
    hass.config.language = "nl"
    handler, schema = _pantry_add_handler(hass)

    call_obj = MagicMock()
    call_obj.data = schema(
        {"name": "milk", "quantity": 2, "unit": "l", "location": "fridge", "expiration_days": 3}
    )
    await handler(call_obj)

    client.async_add_pantry_item.assert_awaited_once_with(
        "milk", quantity=2.0, unit="l", location="fridge", expiration_days=3, language="nl"
    )


@pytest.mark.asyncio
async def test_handle_pantry_add_not_configured():
    hass = MagicMock()
    hass.data = {"culiplan": {}}
    handler, schema = _pantry_add_handler(hass)
    call_obj = MagicMock()
    call_obj.data = schema({"name": "milk"})
    with pytest.raises(HomeAssistantError) as excinfo:
        await handler(call_obj)
    assert excinfo.value.translation_key == "not_configured"


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
    # 7 services registered → 7 removed
    assert hass.services.async_remove.call_count == 7


def test_async_unregister_services_skips_already_removed():
    from custom_components.culiplan.services import async_unregister_services

    hass = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_remove = MagicMock()
    async_unregister_services(hass)
    hass.services.async_remove.assert_not_called()


# ─── handle_generate_blueprint missing-entry path ───────────────────────────


@pytest.mark.asyncio
async def test_handle_generate_blueprint_missing_entry_raises():
    """The blueprint service raises HomeAssistantError when no Culiplan entry exists."""
    from custom_components.culiplan.services import async_register_services

    hass = MagicMock()
    hass.data = {"culiplan": {}}
    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register = MagicMock()

    async_register_services(hass)
    # Locate the blueprint service handler by name.
    handler = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == "generate_blueprint":
            handler = call.args[2]
            break
    assert handler is not None

    call_obj = MagicMock()
    call_obj.data = {"prompt": "Make a blueprint"}
    with pytest.raises(HomeAssistantError) as excinfo:
        await handler(call_obj)
    assert getattr(excinfo.value, "translation_key", "") == "not_configured"
