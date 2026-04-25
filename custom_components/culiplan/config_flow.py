"""Config flow for Flavorplan integration.

task-1390: BYOK key validation + HA local secret store
task-1391: Local AI auto-detection (Ollama + LM Studio)
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow

from .api import FlavorplanApiClient
from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    AI_MODES,
    BYOK_PROVIDERS,
    CONF_AI_MODE,
    CONF_BYOK_API_KEY,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    DOMAIN,
)
from .ai.key_store import BYOKKeyStore, validate_byok_key
from .ai.local_ai import (
    LocalAIEndpoint,
    model_supports_function_calling,
    probe_custom_endpoint,
    probe_local_ai_endpoints,
)
from .ai.types import ProviderAuthError

_LOGGER = logging.getLogger(__name__)

# Sentinel string for the "manual entry" option in the detected-model selector
_MANUAL_ENTRY = "__manual__"


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle OAuth2 authentication and AI provider selection."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        super().__init__()
        self._oauth_data: dict[str, Any] = {}
        self._detected_endpoints: list[LocalAIEndpoint] = []

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle successful OAuth completion; proceed to AI provider step."""
        self._oauth_data = data
        # Probe local AI endpoints before showing the AI provider form
        # (AC#1: probe runs on entering AI provider config flow step)
        self._detected_endpoints = await probe_local_ai_endpoints()
        return await self.async_step_ai_provider()

    async def async_step_ai_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Let the user pick Cloud AI, BYOK, or Local AI.

        BYOK path (task-1390):
          - User enters provider + API key
          - Cheap validation call directly to provider (key never leaves HA)
          - On success: key stored in BYOKKeyStore (HA local storage only)
          - On failure: user-friendly error, key NOT stored

        Local AI path (task-1391):
          - If endpoints detected: show "Detected X at host:port — use it?"
          - AC#4: manual entry always available
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            ai_mode = user_input[CONF_AI_MODE]
            entry_data = {**self._oauth_data, CONF_AI_MODE: ai_mode}

            # ── BYOK ────────────────────────────────────────────────────────
            if ai_mode == AI_MODE_BYOK:
                provider = user_input.get(CONF_BYOK_PROVIDER, "")
                api_key = user_input.get(CONF_BYOK_API_KEY, "").strip()

                if not provider:
                    errors[CONF_BYOK_PROVIDER] = "byok_provider_required"
                elif not api_key:
                    errors[CONF_BYOK_API_KEY] = "byok_key_required"
                else:
                    try:
                        await validate_byok_key(provider, api_key)
                    except ProviderAuthError as exc:
                        _LOGGER.warning(
                            "[culiplan][byok] Key validation failed for '%s': %s",
                            provider, exc,
                        )
                        errors[CONF_BYOK_API_KEY] = "byok_key_invalid"
                        description_placeholders["error_detail"] = str(exc)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.error(
                            "[culiplan][byok] Unexpected validation error: %s", exc
                        )
                        errors["base"] = "byok_validation_error"
                        description_placeholders["error_detail"] = str(exc)

                    if not errors:
                        key_store = BYOKKeyStore(self.hass)
                        await key_store.async_load()
                        await key_store.async_set_key(provider, api_key)
                        _LOGGER.info(
                            "[culiplan][byok] Stored validated key for '%s'", provider
                        )
                        entry_data[CONF_BYOK_PROVIDER] = provider
                        # Key NOT in entry_data — zero-custody §13.2

            # ── Local AI ─────────────────────────────────────────────────────
            elif ai_mode == AI_MODE_LOCAL:
                local_endpoint = user_input.get(CONF_LOCAL_ENDPOINT, "").strip()
                local_model = user_input.get(CONF_LOCAL_MODEL, "").strip()

                if local_endpoint == _MANUAL_ENTRY or not local_endpoint:
                    # Manual entry: use raw values the user typed
                    local_endpoint = user_input.get("local_endpoint_manual", "").strip()

                # Validate the custom endpoint if user provided one
                if local_endpoint and local_endpoint != _MANUAL_ENTRY:
                    try:
                        # Parse host:port from the endpoint URL
                        _host, _port_str = _parse_local_endpoint(local_endpoint)
                        _port = int(_port_str)
                        provider_hint = "lmstudio" if _port == 1234 else "ollama"
                        probed = await probe_custom_endpoint(_host, _port, provider_hint)
                        if probed is None:
                            errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_unreachable"
                        elif local_model and not model_supports_function_calling(local_model):
                            # Warn but don't block — user may know what they're doing
                            description_placeholders["model_warning"] = (
                                f"Model '{local_model}' may not support tool calling. "
                                "Complex AI features (shopping list fill, meal suggestions "
                                "with pantry context) may not work. "
                                "Consider using llama3.2, gemma3, or qwen2.5."
                            )
                            entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                            entry_data[CONF_LOCAL_MODEL] = local_model
                        else:
                            entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                            entry_data[CONF_LOCAL_MODEL] = local_model
                    except (ValueError, Exception):
                        errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_invalid"
                else:
                    entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                    entry_data[CONF_LOCAL_MODEL] = local_model

            if not errors:
                return self.async_create_entry(title="Flavorplan", data=entry_data)

        # ── Build form schema ──────────────────────────────────────────────────
        schema_fields: dict[Any, Any] = {
            vol.Required(CONF_AI_MODE, default=AI_MODE_CLOUD): vol.In(AI_MODES),
        }
        schema_fields[vol.Optional(CONF_BYOK_PROVIDER)] = vol.In(BYOK_PROVIDERS)
        schema_fields[vol.Optional(CONF_BYOK_API_KEY)] = str

        # Pre-fill local endpoint from auto-detection (AC#1 + AC#2)
        if self._detected_endpoints:
            # Show detected endpoints + manual entry option
            endpoint_options = [
                f"{ep.base_url} ({ep.display_name})"
                for ep in self._detected_endpoints
            ] + [_MANUAL_ENTRY]
            schema_fields[vol.Optional(CONF_LOCAL_ENDPOINT)] = vol.In(endpoint_options)

            # Build combined model list from all detected endpoints
            all_models = []
            for ep in self._detected_endpoints:
                all_models.extend(ep.available_models)
            if all_models:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = vol.In(all_models)
            else:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = str
        else:
            schema_fields[vol.Optional(CONF_LOCAL_ENDPOINT)] = str
            schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = str

        # Build description showing detected endpoints
        if self._detected_endpoints and not description_placeholders.get("error_detail"):
            detected_str = ", ".join(ep.display_name for ep in self._detected_endpoints)
            description_placeholders["detected_endpoints"] = detected_str

        return self.async_show_form(
            step_id="ai_provider",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Re-authenticate an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Confirm re-authentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()


def _parse_local_endpoint(endpoint: str) -> tuple[str, str]:
    """
    Parse a local endpoint URL string into (host, port).

    Accepts:
      - "http://localhost:11434" → ("localhost", "11434")
      - "localhost:11434"       → ("localhost", "11434")
      - "http://192.168.1.50:11434/v1" → ("192.168.1.50", "11434")

    Raises ValueError if parsing fails.
    """
    # Strip protocol and trailing path
    url = endpoint.strip()
    if "://" in url:
        url = url.split("://", 1)[1]
    url = url.split("/")[0]  # remove path

    if ":" in url:
        host, port = url.rsplit(":", 1)
        return host.strip(), port.strip()

    raise ValueError(f"Cannot parse host:port from endpoint '{endpoint}'")
