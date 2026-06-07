"""
BYOK key storage using HA's homeassistant.helpers.storage (task-1390).

Per §13.2 zero-custody: BYOK API keys are stored ONLY in HA's local storage.
They are NEVER transmitted to Culiplan infrastructure.

Storage contract:
    - Keys stored in HA's .storage/culiplan_byok_keys file
    - HA's Store class handles persistence and encryption on supported installs
    - Keys are identified by provider name (e.g. "openai", "anthropic", "google")
    - Stored value: the raw API key string
    - No Culiplan server ever sees or validates key content

Validation contract (§13.6):
    - One cheap test call per provider on entry (1-token completion or embedding)
    - Cost per validation: < €0.01
    - On success: key is persisted
    - On failure: key is NOT persisted; user sees a clear error
    - Culiplan backend records {user_id, mode='byok-<provider>', validated=True}
      with NO key fingerprint or content
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .types import ProviderAuthError

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = "culiplan_byok_keys"
_STORAGE_VERSION = 1


class BYOKKeyStore:
    """
    Manages BYOK API key persistence in HA's local storage.

    Usage:
        store = BYOKKeyStore(hass)
        await store.async_load()
        await store.async_set_key("anthropic", validated_key)
        key = store.get_key("anthropic")
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._data: dict[str, str] = {}

    async def async_load(self) -> None:
        """Load keys from HA storage (call once on setup)."""
        loaded = await self._store.async_load()
        self._data = loaded.get("keys", {}) if loaded else {}

    def get_key(self, provider: str) -> str | None:
        """Return the stored key for a provider, or None if not set."""
        return self._data.get(provider)

    async def async_set_key(self, provider: str, key: str) -> None:
        """Persist a BYOK key for a provider."""
        self._data[provider] = key
        await self._store.async_save({"keys": self._data})

    async def async_delete_key(self, provider: str) -> None:
        """Remove a provider's key from storage."""
        if provider in self._data:
            del self._data[provider]
            await self._store.async_save({"keys": self._data})

    async def async_clear(self) -> None:
        """Remove all stored keys (used on config entry removal)."""
        self._data = {}
        await self._store.async_remove()

    def has_key(self, provider: str) -> bool:
        """Return True if a key is stored for the provider."""
        return provider in self._data and bool(self._data[provider])


# ─── Validation calls ──────────────────────────────────────────────────────────


async def validate_openai_key(api_key: str) -> bool:
    """
    Validate an OpenAI API key with a minimal models.list call.

    Uses the models list endpoint which is free (no token consumption).
    Raises ProviderAuthError if the key is invalid.
    """
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        # models.list is a free endpoint — no tokens consumed
        await client.models.list()
        return True
    except Exception as exc:  # noqa: BLE001
        exc_str = str(exc)
        _LOGGER.debug(
            "[culiplan][byok-validation] OpenAI validation failed: %s", exc_str
        )
        if (
            "401" in exc_str
            or "auth" in exc_str.lower()
            or "invalid" in exc_str.lower()
        ):
            raise ProviderAuthError(
                "OpenAI API key is invalid or does not have model access. "
                "Please check your key at https://platform.openai.com/api-keys"
            ) from exc
        raise ProviderAuthError(
            f"OpenAI key validation failed: {exc_str}. "
            "Please check your key and try again."
        ) from exc


async def validate_anthropic_key(api_key: str) -> bool:
    """
    Validate an Anthropic API key with a 1-token completion call.

    Cost: ~$0.000003 (1 input + 1 output token on claude-haiku).
    Raises ProviderAuthError if the key is invalid.
    """
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        # Cheapest possible call: 1-token prompt, max 1 output token
        await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True
    except Exception as exc:  # noqa: BLE001
        exc_str = str(exc)
        _LOGGER.debug(
            "[culiplan][byok-validation] Anthropic validation failed: %s", exc_str
        )
        if (
            "401" in exc_str
            or "auth" in exc_str.lower()
            or "invalid_api_key" in exc_str.lower()
        ):
            raise ProviderAuthError(
                "Anthropic API key is invalid. "
                "Please check your key at https://console.anthropic.com/"
            ) from exc
        raise ProviderAuthError(
            f"Anthropic key validation failed: {exc_str}. "
            "Please check your key and try again."
        ) from exc


async def validate_google_key(api_key: str) -> bool:
    """
    Validate a Google Gemini API key with a models.list call.

    Uses the list models endpoint which is free (no token consumption).
    Raises ProviderAuthError if the key is invalid.
    """
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        # List models — free, no token consumption
        async for _ in client.aio.models.list():
            break
        return True
    except Exception as exc:  # noqa: BLE001
        exc_str = str(exc)
        _LOGGER.debug(
            "[culiplan][byok-validation] Google validation failed: %s", exc_str
        )
        if (
            "API_KEY_INVALID" in exc_str
            or "401" in exc_str
            or "invalid" in exc_str.lower()
        ):
            raise ProviderAuthError(
                "Google Gemini API key is invalid. "
                "Please check your key at https://aistudio.google.com/app/apikey"
            ) from exc
        raise ProviderAuthError(
            f"Google key validation failed: {exc_str}. "
            "Please check your key and try again."
        ) from exc


# ─── Provider dispatch ────────────────────────────────────────────────────────

# Provider → name of the validator function in *this* module. We resolve the
# name to the live function inside ``validate_byok_key`` rather than holding a
# direct reference so test code can ``patch("...key_store.validate_openai_key")``
# and have it actually take effect (a dict-of-functions captures the original
# reference at import time and silently bypasses the patch).
_VALIDATOR_NAMES: dict[str, str] = {
    "openai": "validate_openai_key",
    "anthropic": "validate_anthropic_key",
    "google": "validate_google_key",
}


async def validate_byok_key(provider: str, api_key: str) -> bool:
    """
    Validate a BYOK API key for the given provider.

    Raises:
        ValueError:         If provider is not a known BYOK provider.
        ProviderAuthError:  If the key is invalid or cannot authenticate.
    """
    if provider not in _VALIDATOR_NAMES:
        raise ValueError(
            f"Unknown BYOK provider '{provider}'. "
            f"Supported: {list(_VALIDATOR_NAMES.keys())}"
        )
    # Look up the current module attribute so unittest.mock.patch can
    # intercept the call by patching the function at module scope.
    import sys

    validator = getattr(sys.modules[__name__], _VALIDATOR_NAMES[provider])
    return await validator(api_key)
