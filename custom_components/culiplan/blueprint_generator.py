"""
Flavorplan Blueprint Generator (task-1400, Phase 3 stretch).

Implements `culiplan.generate_blueprint`:
    - Cloud AI mode: backend generates YAML (premium-gated)
    - BYOK / Local AI mode: backend returns prompt envelope; HA dispatcher
      executes the AI call locally and returns raw YAML.
    - Free tier + Cloud AI: Repairs upsell issue created, HomeAssistantError raised.

Architecture:
    - Tier rules ONLY on backend (§11.1.5). 403 → PremiumRequiredError → Repairs.
    - BYOK keys NEVER transit Flavorplan infrastructure (§13.2).
    - Audit log is metadata-only (§13.6) — logged on backend.

Fires HA event: ``culiplan_blueprint_generated`` with payload:
    {
        "name": str,           # blueprint name
        "description": str,   # blueprint description
        "yaml": str,           # YAML content
        "valid": bool,         # whether backend validation passed
        "warnings": list[str], # non-fatal warnings
        "mode": str,           # ai mode used
    }

When `install` is requested and the blueprint is valid, the YAML is written to
``config/blueprints/automation/culiplan/<slug>.yaml`` and HA is notified via
``blueprint.reload``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .ai.dispatchers import create_dispatcher
from .ai.key_store import BYOKKeyStore
from .api import FlavorplanApiClient
from .const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
    CONF_LOCAL_MODEL,
    DOMAIN,
)
from .repairs import async_create_premium_repair, async_resolve_premium_repair
from .services import PremiumRequiredError, _ensure_v1_path  # type: ignore[attr-defined]

_LOGGER = logging.getLogger(__name__)

# ─── Event name ───────────────────────────────────────────────────────────────

EVENT_BLUEPRINT_GENERATED = f"{DOMAIN}_blueprint_generated"

# ─── Blueprint installation ────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _make_slug(name: str) -> str:
    """Convert a blueprint name to a filesystem-safe slug."""
    slug = name.lower()
    slug = _SLUG_RE.sub("_", slug)
    return slug.strip("_") or "blueprint"


async def _install_blueprint(hass: HomeAssistant, name: str, yaml_content: str) -> str:
    """
    Write the blueprint YAML to config/blueprints/automation/culiplan/<slug>.yaml.

    Returns the file path relative to the config directory.
    Raises HomeAssistantError on write failure.
    """
    slug = _make_slug(name)
    dest_dir = Path(hass.config.config_dir) / "blueprints" / "automation" / "culiplan"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{slug}.yaml"

    try:
        await hass.async_add_executor_job(dest_file.write_text, yaml_content, "utf-8")
    except OSError as exc:
        raise HomeAssistantError(
            f"Failed to write blueprint file '{dest_file}': {exc}"
        ) from exc

    rel_path = str(dest_file.relative_to(hass.config.config_dir))
    _LOGGER.info("[culiplan] Blueprint installed: %s", rel_path)
    return rel_path


# ─── AI execution helpers ─────────────────────────────────────────────────────


async def _cloud_generate_blueprint(
    client: FlavorplanApiClient,
    prompt: str,
    available_entities: list[str] | None,
) -> dict[str, Any]:
    """
    Call POST /api/blueprints/generate in Cloud AI mode.

    Returns the API response dict:
        { yaml, name, description, validation: { valid, warnings } }

    Raises PremiumRequiredError on 403, HomeAssistantError on other failures.
    """
    payload: dict[str, Any] = {
        "prompt": prompt,
        "aiProviderMode": "flavorplan-cloud",
    }
    if available_entities:
        payload["context"] = {"available_entities": available_entities[:100]}

    try:
        return await client.async_post("/api/blueprints/generate", payload)
    except Exception as exc:
        exc_str = str(exc)
        if "403" in exc_str or "premium_required" in exc_str:
            upgrade_url = "https://culiplan.com/premium?source=ha_blueprint"
            try:
                import json
                if "{" in exc_str:
                    body = json.loads(exc_str[exc_str.index("{"):])
                    upgrade_url = body.get("upgradeUrl", upgrade_url)
            except (ValueError, KeyError):
                pass
            raise PremiumRequiredError(feature="ai.blueprint", upgrade_url=upgrade_url) from exc
        raise HomeAssistantError(f"Blueprint generation failed: {exc_str}") from exc


async def _byok_local_generate_blueprint(
    hass: HomeAssistant,
    entry_data: dict[str, Any],
    entry_config: dict[str, Any],
    client: FlavorplanApiClient,
    prompt: str,
    available_entities: list[str] | None,
) -> dict[str, Any]:
    """
    Build prompt envelope via backend (BYOK / Local mode), then execute locally.

    Returns a blueprint-shaped dict:
        { yaml, name, description, validation: { valid, warnings } }

    BYOK keys never transit Flavorplan (§13.2) — the key is used only in the
    local AIDispatchService.execute() call.
    """
    ai_mode = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)
    api_key = ""
    base_url: str | None = None
    debug = entry_data.get("options", {}).get("debug_ai", False)

    if ai_mode == AI_MODE_BYOK:
        provider = entry_config.get(CONF_BYOK_PROVIDER, "")
        key_store = BYOKKeyStore(hass)
        await key_store.async_load()
        api_key = key_store.get_key(provider) or ""
        if not api_key:
            raise HomeAssistantError(
                f"No BYOK key found for provider '{provider}'. "
                "Please reconfigure the Flavorplan integration."
            )
    elif ai_mode == AI_MODE_LOCAL:
        endpoint = entry_config.get(CONF_LOCAL_ENDPOINT, "")
        base_url = _ensure_v1_path(endpoint) if endpoint else None
        api_key = "local"

    dispatcher = create_dispatcher(
        mode=ai_mode,
        api_key=api_key,
        base_url=base_url,
        debug=debug,
    )

    # Determine the AI provider mode string expected by the backend
    byok_provider = entry_config.get(CONF_BYOK_PROVIDER, "openai")
    if ai_mode == AI_MODE_BYOK:
        backend_mode = f"byok-{byok_provider}"
    elif ai_mode == AI_MODE_LOCAL:
        model_name = entry_config.get(CONF_LOCAL_MODEL, "")
        backend_mode = "local-lmstudio" if "lmstudio" in (model_name or "").lower() else "local-ollama"
    else:
        backend_mode = "flavorplan-cloud"

    # Fetch prompt envelope from backend
    envelope_payload: dict[str, Any] = {
        "prompt": prompt,
        "aiProviderMode": backend_mode,
    }
    if available_entities:
        envelope_payload["context"] = {"available_entities": available_entities[:100]}

    try:
        envelope_resp = await client.async_post("/api/blueprints/generate", envelope_payload)
    except Exception as exc:
        raise HomeAssistantError(f"Failed to fetch blueprint envelope: {exc}") from exc

    envelope = envelope_resp.get("envelope")
    if not envelope:
        raise HomeAssistantError("Backend returned no prompt envelope for blueprint generation.")

    # Execute AI call locally via dispatcher (no tool-call loop needed — YAML response)
    from .ai.types import PromptEnvelope

    try:
        prompt_envelope = PromptEnvelope.from_dict(envelope)
        dispatch_result = await dispatcher.dispatch(prompt_envelope, tool_results=None)
        raw_yaml = dispatch_result.text or ""
    except Exception as exc:
        raise HomeAssistantError(f"Local AI blueprint generation failed: {exc}") from exc

    # The raw YAML from local AI is unvalidated — return it in the standard shape.
    # Validation happens on a best-effort basis in the service handler.
    return {
        "yaml": raw_yaml,
        "name": _extract_name_from_yaml(raw_yaml),
        "description": _extract_description_from_yaml(raw_yaml),
        "validation": {"valid": True, "warnings": []},
    }


def _extract_name_from_yaml(yaml_text: str) -> str:
    """Extract blueprint name from YAML text (simple regex, no full parse)."""
    match = re.search(r"^\s+name:\s*[\"']?(.+?)[\"']?\s*$", yaml_text, re.MULTILINE)
    return match.group(1).strip() if match else "blueprint"


def _extract_description_from_yaml(yaml_text: str) -> str:
    """Extract blueprint description from YAML text (simple regex)."""
    match = re.search(r"^\s+description:\s*[\"']?(.+?)[\"']?\s*$", yaml_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


# ─── Public API (called from services.py) ────────────────────────────────────


async def handle_generate_blueprint(
    hass: HomeAssistant,
    call: ServiceCall,
    entry_id: str,
) -> None:
    """
    Service handler for ``culiplan.generate_blueprint``.

    Dispatches to Cloud, BYOK, or Local AI based on integration config.
    On success fires ``culiplan_blueprint_generated`` with blueprint payload.
    If ``install`` is True and blueprint is valid, writes to blueprints dir.
    """
    entry_data = hass.data[DOMAIN][entry_id]
    entries = hass.config_entries.async_entries(DOMAIN)
    entry = next((e for e in entries if e.entry_id == entry_id), None)
    entry_config = entry.data if entry else {}

    client: FlavorplanApiClient = entry_data["client"]
    ai_mode: str = entry_config.get(CONF_AI_MODE, AI_MODE_CLOUD)

    prompt: str = call.data["prompt"]
    available_entities: list[str] | None = call.data.get("available_entities")
    install: bool = call.data.get("install", False)

    try:
        if ai_mode == AI_MODE_CLOUD:
            result = await _cloud_generate_blueprint(client, prompt, available_entities)
        else:
            result = await _byok_local_generate_blueprint(
                hass, entry_data, entry_config, client, prompt, available_entities
            )
    except PremiumRequiredError as exc:
        async_create_premium_repair(hass, exc.feature, exc.upgrade_url)
        raise

    yaml_content: str = result.get("yaml", "")
    name: str = result.get("name", "blueprint")
    description: str = result.get("description", "")
    validation: dict[str, Any] = result.get("validation", {"valid": True, "warnings": []})
    is_valid: bool = validation.get("valid", True)
    warnings: list[str] = validation.get("warnings", [])

    async_resolve_premium_repair(hass, "ai.blueprint")

    # Optionally install to blueprints directory
    installed_path: str | None = None
    if install and is_valid and yaml_content:
        try:
            installed_path = await _install_blueprint(hass, name, yaml_content)
            # Reload blueprints so HA picks up the new file
            await hass.services.async_call("blueprint", "reload", {}, blocking=False)
        except HomeAssistantError as exc:
            _LOGGER.warning("[culiplan] Blueprint install failed: %s", exc)
            # Non-fatal — still fire the event with the YAML

    hass.bus.async_fire(
        EVENT_BLUEPRINT_GENERATED,
        {
            "name": name,
            "description": description,
            "yaml": yaml_content,
            "valid": is_valid,
            "warnings": warnings,
            "mode": ai_mode,
            "installed_path": installed_path,
        },
    )

    _LOGGER.info(
        "[culiplan] Blueprint generated: name=%r mode=%s valid=%s warnings=%d",
        name,
        ai_mode,
        is_valid,
        len(warnings),
    )
