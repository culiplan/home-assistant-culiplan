"""Config flow for Culiplan integration.

task-1390: BYOK key validation + HA local secret store
task-1391: Local AI auto-detection (Ollama + LM Studio)
task-1413: Non-loopback Local AI endpoint warning
task-1422: Mealie config_flow wizard steps + OptionsFlow rollback
task-1626: Default to Cloud AI on first run; BYOK/Local behind OptionsFlow Advanced
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from typing import Any, cast
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    AI_MODES,
    BASE_URL,
    BYOK_PROVIDERS,
    CONF_ADVANCED_AI,
    CONF_AI_MODE,
    CONF_BYOK_API_KEY,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    CONF_MEALIE_IMPORT_AT,
    CONF_MEALIE_JOB_ID,
    CONF_MEALIE_TOKEN,
    CONF_MEALIE_URL,
    DOMAIN,
    MEALIE_ROLLBACK_WINDOW_SECONDS,
    OAUTH_CLIENT_ID,
)
from .ai.key_store import BYOKKeyStore, validate_byok_key
from .ai.local_ai import (
    LocalAIEndpoint,
    model_supports_function_calling,
    probe_custom_endpoint,
    probe_local_ai_endpoints,
)
from .ai.types import ProviderAuthError

# HA FlowResult is dict[str, Any] at runtime; cast is used to satisfy strict mypy
# since the HA stubs type flow helper returns as Any.
_FlowResult = dict[str, Any]

_LOGGER = logging.getLogger(__name__)

# Sentinel string for the "manual entry" option in the detected-model selector
_MANUAL_ENTRY = "__manual__"

# Hostnames that are definitively loopback (task-1413)
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_loopback_host(endpoint: str) -> bool:
    """Return True if the endpoint resolves to a loopback or mDNS .local host.

    Loopback (no warning needed):
      - localhost, 127.0.0.1, ::1
      - IPv4 loopback range 127.0.0.0/8
      - IPv6 loopback ::1
    mDNS (treated as local network, no warning):
      - *.local hostnames (mDNS / Bonjour)

    Everything else (RFC-1918 private ranges, public IPs, hostnames) gets a
    warning because the BYOK API key will be forwarded to whatever server
    answers the endpoint.

    SSRF note: plain addr.is_loopback misses:
      - IPv4-mapped IPv6 (::ffff:127.0.0.1) — is_loopback returns False
      - Site-local (fec0::/10) — deprecated but present on some stacks
      - Link-local (fe80::/10) — never routes outside the subnet
    All three are blocked / treated as "remote" here so the warning fires.
    """
    try:
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname or ""
    except Exception:  # noqa: BLE001
        return False

    if not host:
        return False

    # Explicit loopback names
    if host in _LOOPBACK_HOSTNAMES:
        return True

    # mDNS .local — Bonjour / Avahi, never leaves the subnet
    if host.endswith(".local"):
        return True

    # IP address checks — must handle IPv4-mapped IPv6 explicitly
    try:
        addr = ipaddress.ip_address(host)
        if isinstance(addr, ipaddress.IPv6Address):
            # IPv4-mapped IPv6 (::ffff:0:0/96): extract the embedded IPv4 address
            # and check that — Python's is_loopback returns False for these.
            mapped = addr.ipv4_mapped
            if mapped is not None:
                return mapped.is_loopback
            # Site-local (fec0::/10) and link-local (fe80::/10): treat as remote
            # so the user gets a warning that the endpoint is non-loopback.
            if addr.is_site_local or addr.is_link_local:
                return False
        return addr.is_loopback
    except ValueError:
        pass

    return False


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle OAuth2 authentication, AI provider selection, and Mealie import."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        super().__init__()
        self._oauth_data: dict[str, Any] = {}
        self._detected_endpoints: list[LocalAIEndpoint] = []
        self._entry_data: dict[str, Any] = {}
        # Mealie flow state
        self._mealie_preview: dict[str, Any] = {}

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Ensure the built-in OAuth credential is registered, then start OAuth.

        HA only invokes the integration's ``async_setup`` when an entry
        already exists OR when configuration.yaml references the domain.
        On a fresh install both are false, so the ``async_import_client_
        credential`` call in ``async_setup`` never runs before the user
        clicks Add Integration → Culiplan — which is exactly when HA reads
        the credential list to launch OAuth.

        The reliable place is inside the config flow itself. Importing here
        is idempotent: HA stores the credential keyed by (domain, auth_domain),
        and ``async_import_client_credential`` is a no-op if it already
        exists. The fixed ``ha-core`` client is a public OAuth 2.1 PKCE
        client; ``client_secret=""`` is required by the framework but
        ignored by the Culiplan backend per OAuth 2.1 §2.3.
        """
        from homeassistant.components.application_credentials import (  # noqa: PLC0415
            ClientCredential,
            async_import_client_credential,
        )

        _LOGGER.debug(
            "[culiplan][flow] Ensuring built-in OAuth client credential is "
            "registered before pick_implementation",
        )
        await async_import_client_credential(
            self.hass,
            DOMAIN,
            ClientCredential(client_id=OAUTH_CLIENT_ID, client_secret=""),
        )
        return cast(_FlowResult, await super().async_step_user(user_input))

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler.

        HA 2025.12+ removed the legacy ``OptionsFlow(config_entry)`` ctor
        pattern; the framework now injects ``self.config_entry`` after
        construction. We construct without args and read state from
        ``self.config_entry`` inside the flow.
        """
        return MealieOptionsFlow()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle successful OAuth completion.

        Two paths:

        - **New entry** (default): default AI mode to Cloud, set a stable
          unique_id from the Culiplan account, then continue to the Mealie
          import offer. task-1626: BYOK / Local AI are configured later via
          OptionsFlow → Advanced AI settings.
        - **Reconfigure** (Gold rule `reconfiguration-flow`): verify the
          OAuth completed against the *same* Culiplan account as the entry
          being reconfigured; if not, abort with `wrong_account`. On match,
          update the existing entry's token + identity and reload.

        Captures the HA user id of whoever drove the OAuth flow into
        ``data["ha_user_id"]`` so the launch view can later distinguish
        per-user Culiplan accounts on multi-user HA installs.
        """
        self._oauth_data = data
        ha_user_id = self.context.get("user_id")
        if ha_user_id:
            self._oauth_data["ha_user_id"] = ha_user_id

        # Resolve a stable per-account identifier from the Culiplan API so
        # both the new-entry and reconfigure paths can enforce account
        # identity. Failure here is non-fatal for legacy entries — we fall
        # back to letting HA assign a synthetic unique_id, matching the
        # pre-Gold behaviour rather than locking the user out.
        culiplan_account_id = await self._fetch_culiplan_account_id(data)

        if self.source == config_entries.SOURCE_RECONFIGURE:
            return await self._async_finish_reconfigure(data, culiplan_account_id)

        if culiplan_account_id:
            await self.async_set_unique_id(culiplan_account_id)
            self._abort_if_unique_id_configured()

        # task-1626: Default to Cloud AI — skip the ai_provider step entirely.
        # Users who want BYOK / Local AI can reconfigure via OptionsFlow.
        self._entry_data = {**self._oauth_data, CONF_AI_MODE: AI_MODE_CLOUD}
        return await self.async_step_mealie_offer()

    async def _fetch_culiplan_account_id(
        self, oauth_data: dict[str, Any]
    ) -> str | None:
        """Fetch the Culiplan account id via /api/users/me.

        Returns ``None`` on any failure so that an OAuth-but-API-down case
        doesn't break setup. The account id is used as ``ConfigEntry.unique_id``
        to drive the Gold-tier `wrong_account` check on reconfigure.
        """
        try:
            token = oauth_data.get("token", {})
            access_token = token.get("access_token") if isinstance(token, dict) else None
            if not access_token:
                return None
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/api/users/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    me = await resp.json()
                    user_id = me.get("id") if isinstance(me, dict) else None
                    return str(user_id) if user_id else None
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "[culiplan][oauth] Could not fetch Culiplan account id "
                "for unique_id (continuing without): %s",
                exc,
            )
            return None

    async def _async_finish_reconfigure(
        self,
        data: dict[str, Any],
        culiplan_account_id: str | None,
    ) -> dict[str, Any]:
        """Apply a reconfigure result to the existing entry.

        Implements the Gold rule `reconfiguration-flow`. Compares the freshly
        OAuth'd Culiplan account to the existing entry's unique_id; mismatch
        aborts with `wrong_account` (HA 2024.10 lacks
        `_abort_if_unique_id_mismatch`, so this is the manual equivalent).

        On match, replaces the OAuth tokens on the entry, preserves the
        previously-chosen AI mode / Mealie state, and triggers a reload.
        """
        entry_id = self.context.get("entry_id")
        existing = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )

        if existing and culiplan_account_id and existing.unique_id:
            if existing.unique_id != culiplan_account_id:
                return cast(_FlowResult, self.async_abort(reason="wrong_account"))

        # Adopt the new unique_id on entries that pre-date this check.
        if culiplan_account_id:
            await self.async_set_unique_id(culiplan_account_id)

        # Preserve everything the user already configured (AI mode, BYOK
        # provider, Mealie job id, etc); replace just the OAuth identity.
        merged_data = {**(existing.data if existing else {}), **data}
        ha_user_id = self.context.get("user_id")
        if ha_user_id:
            merged_data["ha_user_id"] = ha_user_id

        if existing is None:
            # Defensive: reconfigure with no target entry should never happen
            # in practice, but fall back to creating a new entry rather than
            # silently dropping the OAuth result.
            self._entry_data = {**data, CONF_AI_MODE: AI_MODE_CLOUD}
            return await self.async_step_mealie_offer()

        return cast(
            _FlowResult,
            self.async_update_reload_and_abort(existing, data=merged_data),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Entry point for the Settings → ⋮ → Reconfigure action.

        Re-runs OAuth with the same scopes; on completion,
        ``_async_finish_reconfigure`` enforces same-account identity and
        replaces the entry's tokens.
        """
        return cast(_FlowResult, await self.async_step_user())

    # ──────────────────────────────────────────────────────────────────────────
    # Step: ai_provider
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_ai_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        First AI step — pick Cloud, BYOK, or Local. Provider-specific fields
        are collected in a dedicated follow-up step so the form only ever
        shows the inputs relevant to the chosen mode.
        """
        if user_input is not None:
            ai_mode = user_input[CONF_AI_MODE]
            self._entry_data = {**self._oauth_data, CONF_AI_MODE: ai_mode}

            if ai_mode == AI_MODE_BYOK:
                return await self.async_step_ai_byok()
            if ai_mode == AI_MODE_LOCAL:
                return await self.async_step_ai_local()
            # Cloud AI — no extra config needed
            return await self.async_step_mealie_offer()

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="ai_provider",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_AI_MODE, default=AI_MODE_CLOUD): vol.In(
                            AI_MODES
                        )
                    }
                ),
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: ai_byok  (task-1390)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_ai_byok(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect BYOK provider + API key; validate before storing.

        - Cheap validation call directly to provider (key never leaves HA).
        - On success: key stored in BYOKKeyStore (HA local storage only).
        - On failure: user-friendly error, key NOT stored.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
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
                        provider,
                        exc,
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
                    self._entry_data[CONF_BYOK_PROVIDER] = provider
                    # Key NOT in entry_data — zero-custody §13.2
                    return await self.async_step_mealie_offer()

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="ai_byok",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_BYOK_PROVIDER): vol.In(BYOK_PROVIDERS),
                        vol.Required(CONF_BYOK_API_KEY): str,
                    }
                ),
                errors=errors,
                description_placeholders=description_placeholders,
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: ai_local  (task-1391 + task-1413)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_ai_local(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect Local AI endpoint + model.

        - If endpoints were auto-detected, offer them as a dropdown plus a
          manual-entry option.
        - Non-loopback endpoint triggers a follow-up warning step.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            local_endpoint = user_input.get(CONF_LOCAL_ENDPOINT, "").strip()
            local_model = user_input.get(CONF_LOCAL_MODEL, "").strip()

            if local_endpoint == _MANUAL_ENTRY or not local_endpoint:
                local_endpoint = user_input.get("local_endpoint_manual", "").strip()

            if local_endpoint and local_endpoint != _MANUAL_ENTRY:
                try:
                    _host, _port_str = _parse_local_endpoint(local_endpoint)
                    _port = int(_port_str)
                    provider_hint = "lmstudio" if _port == 1234 else "ollama"
                    probed = await probe_custom_endpoint(_host, _port, provider_hint)
                    if probed is None:
                        errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_unreachable"
                    elif local_model and not model_supports_function_calling(
                        local_model
                    ):
                        description_placeholders["model_warning"] = (
                            f"Model '{local_model}' may not support tool calling. "
                            "Complex AI features (shopping list fill, meal suggestions "
                            "with pantry context) may not work. "
                            "Consider using llama3.2, gemma3, or qwen2.5."
                        )
                        self._entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                        self._entry_data[CONF_LOCAL_MODEL] = local_model
                    else:
                        self._entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                        self._entry_data[CONF_LOCAL_MODEL] = local_model
                except (ValueError, Exception):
                    errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_invalid"
            else:
                self._entry_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                self._entry_data[CONF_LOCAL_MODEL] = local_model

            if not errors:
                local_ep = self._entry_data.get(CONF_LOCAL_ENDPOINT, "")
                if local_ep and not _is_loopback_host(local_ep):
                    return await self.async_step_local_endpoint_remote_warning()
                return await self.async_step_mealie_offer()

        # ── Build form schema ──────────────────────────────────────────────────
        schema_fields: dict[Any, Any] = {}
        if self._detected_endpoints:
            endpoint_options = [
                f"{ep.base_url} ({ep.display_name})" for ep in self._detected_endpoints
            ] + [_MANUAL_ENTRY]
            schema_fields[vol.Required(CONF_LOCAL_ENDPOINT)] = vol.In(endpoint_options)

            all_models: list[str] = []
            for ep in self._detected_endpoints:
                all_models.extend(ep.available_models)
            if all_models:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = vol.In(all_models)
            else:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = str

            detected_str = ", ".join(ep.display_name for ep in self._detected_endpoints)
            description_placeholders.setdefault("detected_endpoints", detected_str)
        else:
            schema_fields[vol.Required(CONF_LOCAL_ENDPOINT)] = str
            schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = str

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="ai_local",
                data_schema=vol.Schema(schema_fields),
                errors=errors,
                description_placeholders=description_placeholders,
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: local_endpoint_remote_warning  (task-1413)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_local_endpoint_remote_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Warn the user that their Local AI endpoint is on a remote host.

        The user is informed (not blocked) and must tick a checkbox to continue.
        """
        if user_input is not None:
            # User acknowledged — proceed to Mealie offer
            return await self.async_step_mealie_offer()

        local_ep = self._entry_data.get(CONF_LOCAL_ENDPOINT, "")
        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="local_endpoint_remote_warning",
                data_schema=vol.Schema(
                    {vol.Required("confirmed", default=False): bool}
                ),
                description_placeholders={"endpoint": local_ep},
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_offer  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_offer(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Offer the user the option to import from Mealie.

        Skips the question entirely when there's no Mealie integration
        configured in this HA install — without Mealie running there's
        nothing to import from, so the prompt is just friction. Users
        who add Mealie later can trigger import via Settings → Configure.

        User can also skip from the form itself and complete setup
        without importing.
        """
        # Check whether HA's Mealie integration has any configured entries.
        # async_entries returns [] if Mealie isn't installed (manifest absent
        # from custom_components/integrations) OR is installed but no entry
        # has been set up. In both cases the import wizard has nothing to
        # connect to that the user has already authenticated, so skip.
        if not self.hass.config_entries.async_entries("mealie"):
            _LOGGER.debug(
                "[culiplan][flow] No Mealie config entries detected — "
                "skipping mealie_offer step",
            )
            return cast(
                _FlowResult,
                self.async_create_entry(title="Culiplan", data=self._entry_data),
            )

        if user_input is not None:
            if user_input.get("migrate_mealie", False):
                return await self.async_step_mealie_credentials()
            # User skipped Mealie — create entry now
            return cast(
                _FlowResult,
                self.async_create_entry(title="Culiplan", data=self._entry_data),
            )

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="mealie_offer",
                data_schema=vol.Schema(
                    {vol.Required("migrate_mealie", default=False): bool}
                ),
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_credentials  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect Mealie base URL and API token, then fetch a preview."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mealie_url = user_input.get(CONF_MEALIE_URL, "").strip().rstrip("/")
            mealie_token = user_input.get(CONF_MEALIE_TOKEN, "").strip()

            if not mealie_url:
                errors[CONF_MEALIE_URL] = "invalid_mealie_url"
            elif not mealie_token:
                errors[CONF_MEALIE_TOKEN] = "byok_key_required"
            else:
                try:
                    preview = await _call_migrate_preview(
                        self.hass,
                        self._entry_data,
                        mealie_url,
                        mealie_token,
                    )
                    self._mealie_preview = preview
                    # Stash credentials for use in _preview → _progress
                    self._entry_data[CONF_MEALIE_URL] = mealie_url
                    self._entry_data[CONF_MEALIE_TOKEN] = mealie_token
                    return await self.async_step_mealie_preview()
                except aiohttp.ClientConnectionError:
                    errors[CONF_MEALIE_URL] = "mealie_unreachable"
                except asyncio.TimeoutError:
                    errors[CONF_MEALIE_URL] = "mealie_timeout"
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error("[culiplan][mealie] Preview failed: %s", exc)
                    errors["base"] = "unknown"

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="mealie_credentials",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MEALIE_URL): str,
                        vol.Required(CONF_MEALIE_TOKEN): str,
                    }
                ),
                errors=errors,
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_preview  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show import preview and ask for confirmation."""
        if user_input is not None:
            if user_input.get("confirm_import", False):
                return await self.async_step_mealie_progress()
            # User cancelled — skip import, create entry without Mealie data
            self._entry_data.pop(CONF_MEALIE_URL, None)
            self._entry_data.pop(CONF_MEALIE_TOKEN, None)
            return cast(
                _FlowResult,
                self.async_create_entry(title="Culiplan", data=self._entry_data),
            )

        p = self._mealie_preview
        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="mealie_preview",
                data_schema=vol.Schema(
                    {vol.Required("confirm_import", default=True): bool}
                ),
                description_placeholders={
                    "will_import": str(p.get("willImport", 0)),
                    "will_flag": str(p.get("willFlag", 0)),
                    "will_skip": str(p.get("willSkip", 0)),
                    "samples": ", ".join(p.get("sampleTitles", [])[:3]),
                },
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_progress  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Kick off the import and poll until complete."""
        mealie_url = self._entry_data.get(CONF_MEALIE_URL, "")
        mealie_token = self._entry_data.get(CONF_MEALIE_TOKEN, "")

        try:
            result = await _call_migrate_start(
                self.hass,
                self._entry_data,
                mealie_url,
                mealie_token,
            )
            job_id = result.get("jobId", "")
            errors_count = result.get("errors", 0)

            # Persist jobId + import timestamp for rollback window check
            self._entry_data[CONF_MEALIE_JOB_ID] = job_id
            self._entry_data[CONF_MEALIE_IMPORT_AT] = int(time.time())

            return await self.async_step_mealie_done(
                job_id=job_id, errors_count=errors_count
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("[culiplan][mealie] Import start failed: %s", exc)
            # Strip token and create entry anyway — user can retry via options flow
            self._entry_data.pop(CONF_MEALIE_TOKEN, None)
            self._entry_data.pop(CONF_MEALIE_URL, None)
            return cast(
                _FlowResult,
                self.async_create_entry(title="Culiplan", data=self._entry_data),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_done  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_done(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        job_id: str = "",
        errors_count: int = 0,
    ) -> dict[str, Any]:
        """Show completion summary and create the config entry.

        §6.6 compliance: Mealie token and URL are stripped before persisting.
        """
        if user_input is not None or job_id:
            # ── CRITICAL: strip Mealie credentials before persisting (§6.6) ──
            self._entry_data.pop(CONF_MEALIE_TOKEN, None)
            self._entry_data.pop(CONF_MEALIE_URL, None)

            return cast(
                _FlowResult,
                self.async_create_entry(title="Culiplan", data=self._entry_data),
            )

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="mealie_done",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "job_id": job_id,
                    "errors": str(errors_count),
                },
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Re-authentication
    # ──────────────────────────────────────────────────────────────────────────

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
            return cast(_FlowResult, self.async_show_form(step_id="reauth_confirm"))
        return cast(_FlowResult, await self.async_step_user())


# ──────────────────────────────────────────────────────────────────────────────
# Options Flow — Mealie rollback (task-1422) + Advanced AI (task-1626)
# ──────────────────────────────────────────────────────────────────────────────


class MealieOptionsFlow(config_entries.OptionsFlow):
    """Options flow: Mealie rollback + Advanced AI settings.

    task-1422: Allow rolling back a Mealie import within 24 hours.
    task-1626: Expose BYOK / Local AI mode selection under "Advanced AI settings".

    HA 2025.12+ removed the legacy ``OptionsFlow(config_entry)`` constructor;
    the framework now sets ``self.config_entry`` after construction so we
    read state from there. We retain the same field names internally — only
    the constructor pattern changed.
    """

    # Declared for type-checkers (HA stubs in the pinned CI version don't
    # surface this attribute); HA's framework assigns it at runtime before
    # any step method is called.
    config_entry: config_entries.ConfigEntry

    def __init__(self) -> None:
        super().__init__()
        # Temporary store for AI config changes during the Advanced AI sub-flow
        self._advanced_ai_data: dict[str, Any] = {}
        # Auto-detected Local AI endpoints (populated on entering advanced_ai_local)
        self._detected_endpoints: list[LocalAIEndpoint] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show main options: pantry windows + debug + Advanced AI + rollback.

        Three previously-orphaned options (`expiry_days`, `expiry_hours`,
        `debug_ai`) are surfaced here. Two pantry windows are consumed by
        `sensor.py` and `binary_sensor.py`; `debug_ai` is consumed by the AI
        dispatcher in `services.py`. Defaults match the consumer-side defaults
        (3 days / 48 h / off) so existing entries don't observe a behavior
        change on first save.
        """
        job_id = self.config_entry.data.get(CONF_MEALIE_JOB_ID)
        import_at = self.config_entry.data.get(CONF_MEALIE_IMPORT_AT, 0)
        elapsed = int(time.time()) - import_at
        rollback_available = bool(job_id and elapsed < MEALIE_ROLLBACK_WINDOW_SECONDS)

        current_options = self.config_entry.options
        current_expiry_days = int(current_options.get("expiry_days", 3))
        current_expiry_hours = int(current_options.get("expiry_hours", 48))
        current_debug_ai = bool(current_options.get("debug_ai", False))

        if user_input is not None:
            if user_input.get("rollback") and rollback_available:
                return await self.async_step_mealie_rollback()
            if user_input.get(CONF_ADVANCED_AI):
                # Carry the pantry/debug values into the Advanced AI sub-flow
                # so the final create_entry call doesn't drop them.
                self._advanced_ai_data = {
                    "expiry_days": int(
                        user_input.get("expiry_days", current_expiry_days)
                    ),
                    "expiry_hours": int(
                        user_input.get("expiry_hours", current_expiry_hours)
                    ),
                    "debug_ai": bool(user_input.get("debug_ai", current_debug_ai)),
                }
                # Probe local endpoints before entering Advanced AI step
                self._detected_endpoints = await probe_local_ai_endpoints()
                return await self.async_step_advanced_ai()
            # No Advanced AI: persist the General/Pantry/Advanced fields.
            options_data = {
                "expiry_days": int(user_input.get("expiry_days", current_expiry_days)),
                "expiry_hours": int(
                    user_input.get("expiry_hours", current_expiry_hours)
                ),
                "debug_ai": bool(user_input.get("debug_ai", current_debug_ai)),
            }
            # Preserve any existing AI mode keys the user already configured.
            for key in (
                CONF_AI_MODE,
                CONF_BYOK_PROVIDER,
                CONF_LOCAL_ENDPOINT,
                CONF_LOCAL_MODEL,
            ):
                if key in current_options:
                    options_data[key] = current_options[key]
            return cast(
                _FlowResult, self.async_create_entry(title="", data=options_data)
            )

        # HA selectors render with units, sliders, and inline helper text
        # (from strings.json data_description). Plain vol types render as
        # raw schema keys with no affordances — see backlog/docs/
        # ha-integration-settings-redesign-2026-06-05.md §4 for IA rationale.
        schema: dict[Any, Any] = {
            vol.Optional("expiry_days", default=current_expiry_days): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=30,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="days",
                )
            ),
            vol.Optional("expiry_hours", default=current_expiry_hours): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=168,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="hours",
                )
            ),
            vol.Optional("debug_ai", default=current_debug_ai): BooleanSelector(),
            # task-1626: Toggle to enter the Advanced AI sub-flow
            vol.Optional(CONF_ADVANCED_AI, default=False): BooleanSelector(),
        }
        if rollback_available:
            schema[vol.Optional("rollback", default=False)] = BooleanSelector()

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(schema),
                description_placeholders={
                    "rollback_available": str(rollback_available).lower(),
                    "job_id": job_id or "",
                    "current_ai_mode": self.config_entry.data.get(
                        CONF_AI_MODE, AI_MODE_CLOUD
                    ),
                },
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Advanced AI settings sub-flow (task-1626)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_advanced_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Select AI mode (Cloud / BYOK / Local).

        Free users get the standard set; Premium unlocks advanced features.
        """
        if user_input is not None:
            ai_mode = user_input[CONF_AI_MODE]
            # Preserve pantry/debug values stashed by async_step_init.
            self._advanced_ai_data = {
                **self._advanced_ai_data,
                CONF_AI_MODE: ai_mode,
            }

            if ai_mode == AI_MODE_BYOK:
                return await self.async_step_advanced_ai_byok()
            if ai_mode == AI_MODE_LOCAL:
                return await self.async_step_advanced_ai_local()
            # Cloud AI — commit immediately (carry pantry/debug forward)
            return cast(
                _FlowResult,
                self.async_create_entry(
                    title="",
                    data={**self._advanced_ai_data, CONF_AI_MODE: AI_MODE_CLOUD},
                ),
            )

        current_mode = self.config_entry.data.get(CONF_AI_MODE, AI_MODE_CLOUD)
        # Selector renders as a vertical list with mode-specific labels.
        # Plain vol.In(AI_MODES) showed bare values ("cloud" / "byok" / "local")
        # with no description — see strings.json options.step.advanced_ai for
        # the long-form explanation that renders above the selector.
        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="advanced_ai",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_AI_MODE, default=current_mode
                        ): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    SelectOptionDict(
                                        value=AI_MODE_CLOUD,
                                        label="Cloud (Culiplan-hosted)",
                                    ),
                                    SelectOptionDict(
                                        value=AI_MODE_BYOK,
                                        label="Bring your own key (BYOK)",
                                    ),
                                    SelectOptionDict(
                                        value=AI_MODE_LOCAL,
                                        label="Local (Ollama / LM Studio)",
                                    ),
                                ],
                                mode=SelectSelectorMode.LIST,
                                translation_key="ai_mode",
                            )
                        )
                    }
                ),
            ),
        )

    async def async_step_advanced_ai_byok(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect BYOK provider + API key for reconfiguration."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
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
                        "[culiplan][options][byok] Key validation failed for '%s': %s",
                        provider,
                        exc,
                    )
                    errors[CONF_BYOK_API_KEY] = "byok_key_invalid"
                    description_placeholders["error_detail"] = str(exc)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error(
                        "[culiplan][options][byok] Unexpected validation error: %s", exc
                    )
                    errors["base"] = "byok_validation_error"
                    description_placeholders["error_detail"] = str(exc)

                if not errors:
                    key_store = BYOKKeyStore(self.hass)
                    await key_store.async_load()
                    await key_store.async_set_key(provider, api_key)
                    _LOGGER.info(
                        "[culiplan][options][byok] Stored validated key for '%s'",
                        provider,
                    )
                    return cast(
                        _FlowResult,
                        self.async_create_entry(
                            title="",
                            data={
                                **self._advanced_ai_data,
                                CONF_AI_MODE: AI_MODE_BYOK,
                                CONF_BYOK_PROVIDER: provider,
                                # Key NOT in options data — zero-custody §13.2
                            },
                        ),
                    )

        # Use SelectSelector (dropdown) for the provider list and a password-
        # typed TextSelector for the API key so the key is masked in the form
        # and not echoed in browser autocomplete history.
        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="advanced_ai_byok",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_BYOK_PROVIDER): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    SelectOptionDict(value=p, label=p.capitalize())
                                    for p in BYOK_PROVIDERS
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Required(CONF_BYOK_API_KEY): TextSelector(
                            TextSelectorConfig(
                                type=TextSelectorType.PASSWORD,
                                autocomplete="off",
                            )
                        ),
                    }
                ),
                errors=errors,
                description_placeholders=description_placeholders,
            ),
        )

    async def async_step_advanced_ai_local(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect Local AI endpoint + model for reconfiguration."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            local_endpoint = user_input.get(CONF_LOCAL_ENDPOINT, "").strip()
            local_model = user_input.get(CONF_LOCAL_MODEL, "").strip()

            if local_endpoint == _MANUAL_ENTRY or not local_endpoint:
                local_endpoint = user_input.get("local_endpoint_manual", "").strip()

            if local_endpoint and local_endpoint != _MANUAL_ENTRY:
                try:
                    _host, _port_str = _parse_local_endpoint(local_endpoint)
                    _port = int(_port_str)
                    provider_hint = "lmstudio" if _port == 1234 else "ollama"
                    probed = await probe_custom_endpoint(_host, _port, provider_hint)
                    if probed is None:
                        errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_unreachable"
                    else:
                        self._advanced_ai_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                        self._advanced_ai_data[CONF_LOCAL_MODEL] = local_model
                except (ValueError, Exception):  # noqa: BLE001
                    errors[CONF_LOCAL_ENDPOINT] = "local_endpoint_invalid"
            else:
                self._advanced_ai_data[CONF_LOCAL_ENDPOINT] = local_endpoint
                self._advanced_ai_data[CONF_LOCAL_MODEL] = local_model

            if not errors:
                # task-1413 parity: warn before saving a non-loopback endpoint
                # in the OptionsFlow. The initial config flow does this; the
                # OptionsFlow previously skipped it (security regression for
                # users reconfiguring to a remote host).
                committed_endpoint = self._advanced_ai_data.get(CONF_LOCAL_ENDPOINT, "")
                if committed_endpoint and not _is_loopback_host(committed_endpoint):
                    return await self.async_step_advanced_ai_local_remote_warning()
                return self._async_commit_advanced_ai_local()

        detected: list[LocalAIEndpoint] = getattr(self, "_detected_endpoints", [])
        schema_fields: dict[Any, Any] = {}
        # Use SelectSelector(custom_value=True) so users can paste a URL not
        # in the detected list without needing a separate __manual__ step.
        if detected:
            endpoint_options = [
                SelectOptionDict(
                    value=ep.base_url,
                    label=f"{ep.base_url} ({ep.display_name})",
                )
                for ep in detected
            ]
            schema_fields[vol.Required(CONF_LOCAL_ENDPOINT)] = SelectSelector(
                SelectSelectorConfig(
                    options=endpoint_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
            all_models: list[str] = []
            for ep in detected:
                all_models.extend(ep.available_models)
            if all_models:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=m, label=m) for m in all_models
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            else:
                schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = TextSelector()
        else:
            schema_fields[vol.Required(CONF_LOCAL_ENDPOINT)] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            )
            schema_fields[vol.Optional(CONF_LOCAL_MODEL)] = TextSelector()

        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="advanced_ai_local",
                data_schema=vol.Schema(schema_fields),
                errors=errors,
                description_placeholders=description_placeholders,
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Advanced AI: remote-endpoint warning (parity with config flow)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_advanced_ai_local_remote_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Warn that the chosen Local AI endpoint is on a remote host.

        Mirrors `async_step_local_endpoint_remote_warning` in the initial
        config flow. The user is informed (not blocked) and must tick a
        checkbox to continue — same UX as the initial-setup warning.
        """
        if user_input is not None:
            return self._async_commit_advanced_ai_local()

        local_ep = self._advanced_ai_data.get(CONF_LOCAL_ENDPOINT, "")
        return cast(
            _FlowResult,
            self.async_show_form(
                step_id="advanced_ai_local_remote_warning",
                data_schema=vol.Schema(
                    {vol.Required("confirmed", default=False): BooleanSelector()}
                ),
                description_placeholders={"endpoint": local_ep},
            ),
        )

    def _async_commit_advanced_ai_local(self) -> dict[str, Any]:
        """Persist the Local AI configuration and finish the options flow."""
        return cast(
            _FlowResult,
            self.async_create_entry(
                title="",
                data={
                    **self._advanced_ai_data,
                    CONF_AI_MODE: AI_MODE_LOCAL,
                    CONF_LOCAL_ENDPOINT: self._advanced_ai_data.get(
                        CONF_LOCAL_ENDPOINT, ""
                    ),
                    CONF_LOCAL_MODEL: self._advanced_ai_data.get(CONF_LOCAL_MODEL, ""),
                },
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Mealie rollback  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_rollback(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call the backend rollback endpoint and report the result."""
        job_id = self.config_entry.data.get(CONF_MEALIE_JOB_ID, "")

        try:
            # NOTE: CuliplanApiClient(session, access_token) — the variable was
            # unused here; the actual DELETE is made via raw aiohttp below.
            # Removed to avoid TypeError (B2 from E2E review).
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{BASE_URL}/api/migrate/mealie",
                    headers={
                        "Authorization": f"Bearer {self.config_entry.data.get('access_token', '')}",
                    },
                    json={"jobId": job_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    resp.raise_for_status()

            _LOGGER.info("[culiplan][mealie] Rollback succeeded for jobId=%s", job_id)
            return cast(_FlowResult, self.async_abort(reason="rollback_complete"))

        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "[culiplan][mealie] Rollback failed for jobId=%s: %s", job_id, exc
            )
            return cast(_FlowResult, self.async_abort(reason="rollback_failed"))


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────


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


async def _call_migrate_preview(
    hass: Any,
    entry_data: dict[str, Any],
    mealie_url: str,
    mealie_token: str,
) -> dict[str, Any]:
    """Call POST /api/migrate/mealie/preview via Culiplan backend.

    Returns a dict with keys: willImport, willFlag, willSkip, sampleTitles.
    """
    access_token = entry_data.get("access_token", "")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/api/migrate/mealie/preview",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"mealieUrl": mealie_url, "mealieToken": mealie_token},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            return cast(dict[str, Any], await resp.json())


async def _call_migrate_start(
    hass: Any,
    entry_data: dict[str, Any],
    mealie_url: str,
    mealie_token: str,
) -> dict[str, Any]:
    """Call POST /api/migrate/mealie to start the import job.

    Returns a dict with keys: jobId, errors.
    """
    access_token = entry_data.get("access_token", "")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/api/migrate/mealie",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"mealieUrl": mealie_url, "mealieToken": mealie_token},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            resp.raise_for_status()
            return cast(dict[str, Any], await resp.json())
