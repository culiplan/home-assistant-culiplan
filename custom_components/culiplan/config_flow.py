"""Config flow for Flavorplan integration (task-1390 adds BYOK key validation)."""

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
from .ai.types import ProviderAuthError

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle OAuth2 authentication and AI provider selection."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle successful OAuth completion; proceed to AI provider step."""
        self._oauth_data = data
        return await self.async_step_ai_provider()

    async def async_step_ai_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Let the user pick Cloud AI, BYOK, or Local AI.

        BYOK path (task-1390):
          - User enters provider + API key
          - One cheap validation call is made directly to the provider (key never
            leaves HA; Flavorplan backend is not involved)
          - On success: key is stored in HA's local storage (BYOKKeyStore)
          - On failure: user sees a clear error; key is NOT stored
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            ai_mode = user_input[CONF_AI_MODE]
            entry_data = {**self._oauth_data, CONF_AI_MODE: ai_mode}

            if ai_mode == AI_MODE_BYOK:
                provider = user_input.get(CONF_BYOK_PROVIDER, "")
                api_key = user_input.get(CONF_BYOK_API_KEY, "").strip()

                if not provider:
                    errors[CONF_BYOK_PROVIDER] = "byok_provider_required"
                elif not api_key:
                    errors[CONF_BYOK_API_KEY] = "byok_key_required"
                else:
                    # Validate the key with a cheap test call to the provider.
                    # The key is NEVER sent to Flavorplan — this call goes directly
                    # from HA to the AI provider's API.
                    try:
                        await validate_byok_key(provider, api_key)
                    except ProviderAuthError as exc:
                        _LOGGER.warning(
                            "[culiplan][byok] Key validation failed for provider '%s': %s",
                            provider, exc,
                        )
                        errors[CONF_BYOK_API_KEY] = "byok_key_invalid"
                        description_placeholders["error_detail"] = str(exc)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.error(
                            "[culiplan][byok] Unexpected error during key validation: %s", exc
                        )
                        errors["base"] = "byok_validation_error"
                        description_placeholders["error_detail"] = str(exc)

                    if not errors:
                        # Store the validated key in HA's local storage only
                        key_store = BYOKKeyStore(self.hass)
                        await key_store.async_load()
                        await key_store.async_set_key(provider, api_key)
                        _LOGGER.info(
                            "[culiplan][byok] Validated and stored key for provider '%s'",
                            provider,
                        )

                        # NOTE: The API key is NOT included in entry_data.
                        # It lives only in BYOKKeyStore (HA local storage).
                        # The config entry records only the provider name so the
                        # integration knows which key to load at runtime.
                        entry_data[CONF_BYOK_PROVIDER] = provider
                        # Do NOT set CONF_BYOK_API_KEY in entry_data — zero-custody.

            elif ai_mode == AI_MODE_LOCAL:
                entry_data[CONF_LOCAL_ENDPOINT] = user_input.get(CONF_LOCAL_ENDPOINT, "")
                entry_data[CONF_LOCAL_MODEL] = user_input.get(CONF_LOCAL_MODEL, "")

            if not errors:
                return self.async_create_entry(title="Flavorplan", data=entry_data)

        schema_fields: dict[Any, Any] = {
            vol.Required(CONF_AI_MODE, default=AI_MODE_CLOUD): vol.In(AI_MODES),
        }
        # Show BYOK/Local fields so the user can fill them in one step.
        schema_fields[vol.Optional(CONF_BYOK_PROVIDER)] = vol.In(BYOK_PROVIDERS)
        schema_fields[vol.Optional(CONF_BYOK_API_KEY)] = str
        schema_fields[vol.Optional(CONF_LOCAL_ENDPOINT)] = str
        schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = str

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
