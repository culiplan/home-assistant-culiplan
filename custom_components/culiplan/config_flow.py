"""Config flow for Flavorplan integration."""

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
        """Let the user pick Cloud AI, BYOK, or Local AI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ai_mode = user_input[CONF_AI_MODE]
            entry_data = {**self._oauth_data, CONF_AI_MODE: ai_mode}

            if ai_mode == AI_MODE_BYOK:
                entry_data[CONF_BYOK_PROVIDER] = user_input[CONF_BYOK_PROVIDER]
                # Key never leaves HA; stored in HA secrets, not sent to Flavorplan.
                entry_data[CONF_BYOK_API_KEY] = user_input.get(CONF_BYOK_API_KEY, "")

            elif ai_mode == AI_MODE_LOCAL:
                entry_data[CONF_LOCAL_ENDPOINT] = user_input.get(CONF_LOCAL_ENDPOINT, "")
                entry_data[CONF_LOCAL_MODEL] = user_input.get(CONF_LOCAL_MODEL, "")

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
            description_placeholders={},
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
