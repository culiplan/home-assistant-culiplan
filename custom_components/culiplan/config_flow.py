"""Config flow for Culiplan integration.

task-1390: BYOK key validation + HA local secret store
task-1391: Local AI auto-detection (Ollama + LM Studio)
task-1413: Non-loopback Local AI endpoint warning
task-1422: Mealie config_flow wizard steps + OptionsFlow rollback
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow

from .api import CuliplanApiClient
from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    AI_MODES,
    BASE_URL,
    BYOK_PROVIDERS,
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
    warning because the token might travel over an untrusted network.
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

    # IP address checks
    try:
        addr = ipaddress.ip_address(host)
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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return MealieOptionsFlow(config_entry)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle successful OAuth completion; proceed to AI provider step.

        Captures the HA user id of whoever drove the OAuth flow into
        ``data["ha_user_id"]`` so the launch view can later distinguish
        per-user Culiplan accounts on multi-user HA installs. The id comes
        from HA's auth context; for flows started by a non-user (yaml
        import, service call) it is left unset.
        """
        self._oauth_data = data
        ha_user_id = self.context.get("user_id")
        if ha_user_id:
            self._oauth_data["ha_user_id"] = ha_user_id
        # Probe local AI endpoints before showing the AI provider form
        # (AC#1: probe runs on entering AI provider config flow step)
        self._detected_endpoints = await probe_local_ai_endpoints()
        return await self.async_step_ai_provider()

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

        return self.async_show_form(
            step_id="ai_provider",
            data_schema=vol.Schema(
                {vol.Required(CONF_AI_MODE, default=AI_MODE_CLOUD): vol.In(AI_MODES)}
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
                    self._entry_data[CONF_BYOK_PROVIDER] = provider
                    # Key NOT in entry_data — zero-custody §13.2
                    return await self.async_step_mealie_offer()

        return self.async_show_form(
            step_id="ai_byok",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BYOK_PROVIDER): vol.In(BYOK_PROVIDERS),
                    vol.Required(CONF_BYOK_API_KEY): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
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
                    elif local_model and not model_supports_function_calling(local_model):
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
                f"{ep.base_url} ({ep.display_name})"
                for ep in self._detected_endpoints
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

        return self.async_show_form(
            step_id="ai_local",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders=description_placeholders,
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
        return self.async_show_form(
            step_id="local_endpoint_remote_warning",
            data_schema=vol.Schema(
                {vol.Required("confirmed", default=False): bool}
            ),
            description_placeholders={"endpoint": local_ep},
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step: mealie_offer  (task-1422)
    # ──────────────────────────────────────────────────────────────────────────

    async def async_step_mealie_offer(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Offer the user the option to import from Mealie.

        User can skip and complete setup without importing.
        """
        if user_input is not None:
            if user_input.get("migrate_mealie", False):
                return await self.async_step_mealie_credentials()
            # User skipped Mealie — create entry now
            return self.async_create_entry(title="Culiplan", data=self._entry_data)

        return self.async_show_form(
            step_id="mealie_offer",
            data_schema=vol.Schema(
                {vol.Required("migrate_mealie", default=False): bool}
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

        return self.async_show_form(
            step_id="mealie_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MEALIE_URL): str,
                    vol.Required(CONF_MEALIE_TOKEN): str,
                }
            ),
            errors=errors,
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
            return self.async_create_entry(title="Culiplan", data=self._entry_data)

        p = self._mealie_preview
        return self.async_show_form(
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
            return self.async_create_entry(title="Culiplan", data=self._entry_data)

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

            return self.async_create_entry(title="Culiplan", data=self._entry_data)

        return self.async_show_form(
            step_id="mealie_done",
            data_schema=vol.Schema({}),
            description_placeholders={
                "job_id": job_id,
                "errors": str(errors_count),
            },
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
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()


# ──────────────────────────────────────────────────────────────────────────────
# Options Flow — Mealie rollback  (task-1422)
# ──────────────────────────────────────────────────────────────────────────────


class MealieOptionsFlow(config_entries.OptionsFlow):
    """Options flow: allow rolling back a Mealie import within 24 hours."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show rollback option if within the 24-hour window."""
        job_id = self._config_entry.data.get(CONF_MEALIE_JOB_ID)
        import_at = self._config_entry.data.get(CONF_MEALIE_IMPORT_AT, 0)
        elapsed = int(time.time()) - import_at
        rollback_available = bool(
            job_id and elapsed < MEALIE_ROLLBACK_WINDOW_SECONDS
        )

        if user_input is not None:
            if user_input.get("rollback") and rollback_available:
                return await self.async_step_mealie_rollback()
            return self.async_create_entry(title="", data={})

        schema: dict[Any, Any] = {}
        if rollback_available:
            schema[vol.Optional("rollback", default=False)] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema) if schema else None,
            description_placeholders={
                "rollback_available": str(rollback_available).lower(),
                "job_id": job_id or "",
            },
        )

    async def async_step_mealie_rollback(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call the backend rollback endpoint and report the result."""
        job_id = self._config_entry.data.get(CONF_MEALIE_JOB_ID, "")

        try:
            client = CuliplanApiClient(
                self.hass,
                self._config_entry,
            )
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{BASE_URL}/api/migrate/mealie",
                    headers={
                        "Authorization": f"Bearer {self._config_entry.data.get('access_token', '')}",
                    },
                    json={"jobId": job_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    resp.raise_for_status()

            _LOGGER.info("[culiplan][mealie] Rollback succeeded for jobId=%s", job_id)
            return self.async_abort(reason="rollback_complete")

        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "[culiplan][mealie] Rollback failed for jobId=%s: %s", job_id, exc
            )
            return self.async_abort(reason="rollback_failed")


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
            return await resp.json()


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
            return await resp.json()
