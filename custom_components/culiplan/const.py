"""Constants for the Flavorplan integration."""

DOMAIN = "culiplan"
OAUTH_CLIENT_ID = "ha-core"
BASE_URL = "https://api.culiplan.com"
OAUTH2_AUTHORIZE = f"{BASE_URL}/api/oauth/authorize"
OAUTH2_TOKEN = f"{BASE_URL}/api/oauth/token"

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

# binary_sensor added in Phase 2 (tasks 1378 + 1380)
PLATFORMS: list[str] = ["binary_sensor", "calendar", "sensor", "todo"]

# ─── Mealie migration (Phase 2, task-1394) ────────────────────────────────────
CONF_MEALIE_URL = "mealie_url"
CONF_MEALIE_TOKEN = "mealie_token"
CONF_MEALIE_JOB_ID = "mealie_job_id"
CONF_MEALIE_IMPORT_AT = "mealie_import_at"

# How long the rollback button remains available after import (seconds)
MEALIE_ROLLBACK_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
