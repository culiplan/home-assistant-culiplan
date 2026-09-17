"""Constants for the Culiplan integration."""

import json as _json
from pathlib import Path as _Path

DOMAIN = "culiplan"
OAUTH_CLIENT_ID = "ha-core"
BASE_URL = "https://api.culiplan.com"
WEB_URL = "https://culiplan.com"
OAUTH2_AUTHORIZE = f"{BASE_URL}/api/oauth/authorize"
OAUTH2_TOKEN = f"{BASE_URL}/api/oauth/token"

# OAuth scopes requested for the ha-core client. Must be a subset of the
# `allowedScopes` registered for `ha-core` in the backend
# (packages/backend/src/scripts/seed/seedOAuthClients.ts). Single source of
# truth — referenced from application_credentials.py and (future) reauth flows.
OAUTH2_SCOPES: tuple[str, ...] = (
    "calendar:read",
    "todo:read",
    "todo:write",
    "pantry:read",
    "pantry:write",
    "meals:read",
    "meals:write",
    "shopping:read",
    "shopping:write",
    "recipes:read",
    "profile:read",
    "household:read",
    "subscription:read",
    "energy:read",
    "ai:suggestions",
    "blueprints:generate",
    "openid",
    "offline_access",
)

# AI provider modes
AI_MODE_CLOUD = "cloud"
AI_MODE_BYOK = "byok"
AI_MODE_LOCAL = "local"

AI_MODES = [AI_MODE_CLOUD, AI_MODE_BYOK, AI_MODE_LOCAL]

# Supported AI providers for BYOK
BYOK_PROVIDERS = ["openai", "anthropic", "google"]

CONF_AI_MODE = "ai_mode"
CONF_BYOK_PROVIDER = "byok_provider"
CONF_BYOK_API_KEY = "byok_api_key"
CONF_LOCAL_ENDPOINT = "local_endpoint"
CONF_LOCAL_MODEL = "local_model"

# OptionsFlow: "Advanced AI settings" toggle
CONF_ADVANCED_AI = "advanced_ai"

# binary_sensor added in Phase 2 (tasks 1378 + 1380)
PLATFORMS: list[str] = ["binary_sensor", "calendar", "sensor", "todo", "update"]

# ─── Mealie migration (Phase 2, task-1394) ────────────────────────────────────
CONF_MEALIE_URL = "mealie_url"
CONF_MEALIE_TOKEN = "mealie_token"
CONF_MEALIE_JOB_ID = "mealie_job_id"
CONF_MEALIE_IMPORT_AT = "mealie_import_at"

# How long the rollback button remains available after import (seconds)
MEALIE_ROLLBACK_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours

# ─── Pantry ───────────────────────────────────────────────────────────────────
# Storage locations accepted by the backend (PantryStock.location enum, sent
# lower-case; the backend upper-cases). Shared by the pantry_add service, the
# add_to_pantry LLM tool and the CuliplanAddToPantry Assist intent.
PANTRY_LOCATIONS: tuple[str, ...] = (
    "pantry",
    "fridge",
    "freezer",
    "counter",
    "spice_rack",
    "other",
)


# ─── Integration version ─────────────────────────────────────────────────────
#
# Read ONCE, at module import. HA imports integration modules in an executor
# thread, so this file read never runs on the event loop. Reading the manifest
# from a coroutine instead makes HA log:
#
#   Detected blocking call to read_text with args
#   (PosixPath('/config/custom_components/culiplan/manifest.json'),)
#   inside the event loop by custom integration 'culiplan'
#
# const.py imports nothing from this package, so every module can import
# MANIFEST_VERSION from here without risking a circular import.


def _read_manifest_version() -> str:
    """Return the ``version`` field from manifest.json, or "dev" if unreadable."""
    try:
        manifest_path = _Path(__file__).parent / "manifest.json"
        return str(
            _json.loads(manifest_path.read_text(encoding="utf-8")).get("version", "dev")
        )
    except Exception:  # noqa: BLE001
        return "dev"


MANIFEST_VERSION: str = _read_manifest_version()
