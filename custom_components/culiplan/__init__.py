"""The Culiplan integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import aiohttp
import yaml
from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
    intent,
)
from homeassistant.helpers.typing import ConfigType

from .api import CuliplanApiClient
from .const import (
    DOMAIN,
    MANIFEST_VERSION,
    OAUTH_CLIENT_ID,
    PANTRY_LOCATIONS,
    PLATFORMS,
)
from .coordinator import CuliplanCoordinator
from .cooking_services import (
    async_register_cooking_services,
    async_unregister_cooking_services,
)
from .launch_view import CuliplanLaunchView
from .llm_api import async_register_llm_api, async_unregister_llm_api
from .services import (
    _call_pantry_add,
    async_register_services,
    async_unregister_services,
)


# ─── Lovelace resource auto-registration (task-1408) ─────────────────────────
#
# Card bundles are served from the integration's own static path,
# /culiplan_static/cards/<name>.js, registered in
# _async_register_sidebar_panel() from custom_components/culiplan/frontend/cards/.
#
# These used to point at /hacsfiles/culiplan/lovelace/cards/dist/<name>.js on
# the assumption that HACS mirrors the whole repo into <config>/www/community/.
# It does not: for an *integration* repo HACS copies custom_components/<domain>/
# and nothing else, so /hacsfiles/culiplan/... was never populated and all three
# resources 404'd on every dashboard load. Serving them ourselves makes the
# files present for every install method — HACS, manual copy, or the built-in
# update entity.
#
# Deliberately un-versioned: the static path is registered with
# cache_headers=False, so a version query string is unnecessary — and it would
# be actively harmful here, since a changing URL means a *new* resource row on
# every upgrade, leaving the old one behind forever.
#
# Decision on unload: resources are NOT auto-removed when the integration
# is unloaded/reloaded. Removing them would break dashboards that the user
# has customised to use these cards. The manual fallback path in
# lovelace/README.md remains valid and unchanged.
#
_LOVELACE_RESOURCES: tuple[dict[str, str], ...] = (
    {
        "url": "/culiplan_static/cards/kitchen-dashboard.js",
        "res_type": "module",
    },
    {
        "url": "/culiplan_static/cards/pantry-tracker.js",
        "res_type": "module",
    },
    {
        "url": "/culiplan_static/cards/cooking-mode.js",
        "res_type": "module",
    },
)

# Resource URLs this integration registered in earlier versions and which are
# known-dead. Any resource row whose URL starts with one of these is removed on
# setup — see _async_register_lovelace_resources(). Scoped to Culiplan-owned
# prefixes so a user's own resources are never touched.
_STALE_RESOURCE_URL_PREFIXES: tuple[str, ...] = (
    "/hacsfiles/culiplan/lovelace/cards/dist/",
)

# Sidebar panel path — kept module-level so register/unregister refer to the same name.
PANEL_URL_PATH = "culiplan"

_LOGGER = logging.getLogger(__name__)

# Hassfest CONFIG_SCHEMA requirement: this integration is config_entry-only.
# YAML configuration is intentionally unsupported — users set it up via the UI
# (config flow) which performs OAuth via the application_credentials framework.
# `cv.config_entry_only_config_schema` raises a deprecation warning if anyone
# tries to add a `culiplan:` block to configuration.yaml.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_INTENTS_DIR = Path(__file__).parent / "intents"

# Assist intent → backend voice tool, executed on POST /api/voice/execute.
# Every value must exist by that exact name in the backend's
# voiceToolRegistry.ts (verified 2026-09-17; the earlier
# "get_expiring_pantry" never existed — the tool is get_expiring_items).
_INTENT_TO_TOOL: dict[str, str] = {
    "CuliplanWhatsDinnerTonight": "whats_for_dinner",
    "CuliplanGetWeekMeals": "get_week_meals",
    "CuliplanGetShoppingList": "get_shopping_list",
    "CuliplanAddToShoppingList": "add_to_shopping_list",
    "CuliplanWhatsInPantry": "whats_in_pantry",
    "CuliplanWhatsExpiringSoon": "get_expiring_items",
}

# Sentence slot name → tool parameter name, where they differ.
_INTENT_SLOT_TO_PARAM: dict[str, dict[str, str]] = {
    "CuliplanAddToShoppingList": {"item": "name"},
}

# Languages we ship Assist sentences for (custom_components/culiplan/intents/).
_INTENT_LANGS: tuple[str, ...] = ("en", "nl", "de", "fr", "es")

# HA's default conversation agent only reads sentence files from
# <config>/custom_sentences/<lang>/*.yaml — there is no hook for a custom
# component to ship them in its own directory. So on every setup we install
# our per-language YAML there under this name (byte-compare first, so an
# unchanged file is never rewritten) and ask the conversation integration to
# reload if anything changed. The files are deliberately left in place on
# unload / removal: the user may have edited them.
_CUSTOM_SENTENCES_FILENAME = "culiplan.yaml"

# Cooking-mode intents that map directly to HA services (task-1397).
# These call the local service rather than the remote voice-tool endpoint.
_COOKING_INTENT_TO_SERVICE: dict[str, str] = {
    "CuliplanNextCookingStep": "advance_cooking_step",
    "CuliplanSetRecipeTimer": "set_recipe_timer",
    "CuliplanCancelRecipeTimer": "cancel_recipe_timer",
}

# "Add {item} to the fridge" — writes to the pantry through the same helper
# as the culiplan.pantry_add service (services._call_pantry_add).
_PANTRY_ADD_INTENT = "CuliplanAddToPantry"

# Spoken confirmation per language: (template, location → spoken phrase).
# Composed locally so the reply echoes the location Assist understood
# ("Added milk to your fridge"); the backend's own speakable string is
# location-agnostic ("Added milk to your pantry") and is used as fallback
# for any language not listed here. Keys mirror PANTRY_LOCATIONS.
_PANTRY_ADD_SPEECH: dict[str, tuple[str, dict[str, str]]] = {
    "en": (
        "Added {item} to your {location}.",
        {
            "pantry": "pantry",
            "fridge": "fridge",
            "freezer": "freezer",
            "counter": "counter",
            "spice_rack": "spice rack",
            "other": "pantry",
        },
    ),
    "nl": (
        "{item} toegevoegd aan je {location}.",
        {
            "pantry": "voorraad",
            "fridge": "koelkast",
            "freezer": "diepvries",
            "counter": "aanrecht",
            "spice_rack": "kruidenrek",
            "other": "voorraad",
        },
    ),
    "de": (
        "{item} {location} hinzugefügt.",
        {
            "pantry": "zum Vorrat",
            "fridge": "zum Kühlschrank",
            "freezer": "zum Gefrierschrank",
            "counter": "zur Arbeitsplatte",
            "spice_rack": "zum Gewürzregal",
            "other": "zum Vorrat",
        },
    ),
    "fr": (
        "{item} ajouté {location}.",
        {
            "pantry": "au garde-manger",
            "fridge": "au frigo",
            "freezer": "au congélateur",
            "counter": "sur le plan de travail",
            "spice_rack": "à l'étagère à épices",
            "other": "au garde-manger",
        },
    ),
    "es": (
        "{item} añadido {location}.",
        {
            "pantry": "a la despensa",
            "fridge": "a la nevera",
            "freezer": "al congelador",
            "counter": "a la encimera",
            "spice_rack": "al especiero",
            "other": "a la despensa",
        },
    ),
}


async def _async_register_lovelace_resources(hass: HomeAssistant) -> None:
    """
    Register Culiplan Lovelace card resources idempotently (task-1408).

    Uses HA's internal Lovelace ResourceStorageCollection when available.
    Falls back gracefully if the Lovelace component is not yet loaded or
    if the storage collection API has changed (e.g. dev HA builds).

    Idempotency: the set of already-registered URLs is read first, and we
    only create the ones that are missing. Crucially, if that read fails for
    any reason we **skip registration entirely** rather than assuming
    "nothing is registered" — guessing wrong there appends a fresh row with a
    new UUID on every single startup. That is exactly what the previous
    version did: it awaited `async_items()` (a sync @callback returning a
    list, so `await` raised TypeError) and then called `async_load(True)`
    (which takes no arguments, so it raised TypeError too), landing in a bare
    `except Exception: existing_items = []`. One reporter's instance had
    accumulated 1398 resource rows — 466 duplicates of each of three cards.

    Also removes rows left behind by earlier versions: dead
    /hacsfiles/culiplan/... URLs and any duplicates of our current URLs.

    Unload behaviour: resources are intentionally NOT removed on
    integration unload/reload (see _LOVELACE_RESOURCES comment above).
    """
    try:
        # HA exposes the Lovelace resource collection via hass.data["lovelace"].
        # The legacy `hass.components.lovelace` proxy was removed in HA 2025.8;
        # if hass.data hasn't been populated yet, treat it as "not available"
        # and skip registration (the user can still install resources via the
        # Lovelace UI per lovelace/README.md).
        lovelace = hass.data.get("lovelace")
        resource_collection = getattr(lovelace, "resources", None) if lovelace else None

        if resource_collection is None:
            _LOGGER.debug(
                "[culiplan] Lovelace resource collection not available — "
                "skipping auto-registration. Use lovelace/README.md for manual setup."
            )
            return

        # ResourceStorageCollection lazily loads from storage; async_items()
        # returns an empty list until it has. Every public mutator calls
        # _async_ensure_loaded() internally, but the read path does not — so
        # load explicitly, or we would read "no resources" and re-create all
        # three on top of whatever is already stored.
        #
        # async_get_info() is the public call that runs _async_ensure_loaded()
        # and flips `.loaded`. Prefer it over calling async_load() directly: a
        # bare async_load() leaves `.loaded` False, so the first create would
        # trigger a second load and re-notify every existing item.
        if not getattr(resource_collection, "loaded", False):
            if hasattr(resource_collection, "async_get_info"):
                await resource_collection.async_get_info()
            else:
                await resource_collection.async_load()
                resource_collection.loaded = True

        # async_items() is a synchronous @callback (homeassistant.helpers
        # .collection.ObservableCollection.async_items) — it must NOT be awaited.
        existing_items = resource_collection.async_items()

    except Exception as err:
        # Fail CLOSED: without a trustworthy view of what is already
        # registered we cannot register anything without risking duplicates.
        _LOGGER.warning(
            "[culiplan] Could not read existing Lovelace resources (%s) — skipping "
            "auto-registration to avoid creating duplicates. See lovelace/README.md "
            "for manual setup.",
            err,
        )
        return

    wanted_urls = {resource["url"] for resource in _LOVELACE_RESOURCES}
    seen_urls: set[str] = set()
    stale_item_ids: list[tuple[str, str]] = []  # (item_id, url) for logging

    for item in existing_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        item_id = item.get("id")

        # Dead URLs from earlier Culiplan versions.
        if url.startswith(_STALE_RESOURCE_URL_PREFIXES):
            if item_id:
                stale_item_ids.append((item_id, url))
            continue

        # Duplicate rows for a URL we own — keep the first, drop the rest.
        if url in wanted_urls:
            if url in seen_urls:
                if item_id:
                    stale_item_ids.append((item_id, url))
            else:
                seen_urls.add(url)

    for item_id, url in stale_item_ids:
        try:
            await resource_collection.async_delete_item(item_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "[culiplan] Could not remove stale Lovelace resource %s (%s): %s",
                url,
                item_id,
                err,
            )

    if stale_item_ids:
        _LOGGER.info(
            "[culiplan] Removed %d stale/duplicate Culiplan Lovelace resource(s)",
            len(stale_item_ids),
        )

    for resource in _LOVELACE_RESOURCES:
        url = resource["url"]
        if url in seen_urls:
            _LOGGER.debug("[culiplan] Lovelace resource already registered: %s", url)
            continue
        try:
            await resource_collection.async_create_item(
                {"url": url, "res_type": resource["res_type"]}
            )
            _LOGGER.info("[culiplan] Registered Lovelace resource: %s", url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "[culiplan] Could not register Lovelace resource %s: %s", url, err
            )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Culiplan integration.

    Auto-imports the public OAuth client credentials so users skip the
    "Add application credentials" dialog and go straight to consent.

    The Culiplan backend's ``ha-core`` is a public PKCE-only client per
    OAuth 2.1 §2.3 — the client_secret field is required by HA's
    application_credentials framework but ignored by the backend.

    Note: ``async_import_client_credential``'s fourth positional argument
    is ``auth_domain``, NOT a display name. Earlier versions passed
    ``"Culiplan"`` which stored the credential under a mismatched
    auth_domain, so HA's lookup for ``culiplan`` never found it and the
    dialog kept appearing. Pass ``None`` (the default) so auth_domain
    falls back to DOMAIN, matching what the config flow looks up.
    """
    _LOGGER.debug(
        "[culiplan][setup] Importing built-in OAuth client credential for domain %s",
        DOMAIN,
    )
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential(
            client_id=OAUTH_CLIENT_ID,
            client_secret="",
        ),
    )
    return True


_LEGACY_UNIQUE_ID_SUFFIXES: tuple[str, ...] = (
    # sensor.py
    "meals_planned_this_week",
    "shopping_items",
    "expiring_pantry",
    "planned_kwh_today",
    # binary_sensor.py
    "pantry_has_expiring",
    "dinner_party_active",
    # update.py
    "update",
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    v1 → v2 (v0.13.0)
        Rewrite per-entity ``unique_id`` from the legacy
        ``f"{DOMAIN}_<suffix>"`` form to the per-entry
        ``f"{entry.entry_id}_<suffix>"`` form. The previous form caused a
        collision the moment a user added a second Culiplan account: HA
        rejects a duplicate ``(platform, unique_id)`` tuple, so half of the
        sensors / binary_sensors / the update entity for the second account
        never appeared.

        Only the entries in :data:`_LEGACY_UNIQUE_ID_SUFFIXES` are affected
        — calendar (keyed on plan_id) and todo (keyed on shopping_list_id)
        already had per-resource unique IDs and are intentionally left
        alone. Idempotent: if the entity registry already holds the new
        form (e.g. fresh install or re-run after a partial migration),
        ``async_update_entity`` is not called.
    """
    if entry.version == 1:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        migrated = 0
        # Snapshot the entries up-front; async_update_entity mutates the
        # registry's internal index, which would invalidate a live iterator.
        for reg_entry in list(registry.entities.values()):
            if reg_entry.config_entry_id != entry.entry_id:
                continue
            for suffix in _LEGACY_UNIQUE_ID_SUFFIXES:
                legacy_uid = f"{DOMAIN}_{suffix}"
                if reg_entry.unique_id != legacy_uid:
                    continue
                new_uid = f"{entry.entry_id}_{suffix}"
                # Skip if the new uid already exists for this platform
                # (idempotency guard against a half-finished prior run).
                existing = registry.async_get_entity_id(
                    reg_entry.domain, DOMAIN, new_uid
                )
                if existing is not None and existing != reg_entry.entity_id:
                    _LOGGER.warning(
                        "[culiplan][migrate] Both %s and %s already exist; "
                        "leaving legacy entity %s untouched. Remove the "
                        "duplicate manually if desired.",
                        legacy_uid,
                        new_uid,
                        reg_entry.entity_id,
                    )
                    break
                registry.async_update_entity(reg_entry.entity_id, new_unique_id=new_uid)
                _LOGGER.info(
                    "[culiplan][migrate] %s: %s → %s",
                    reg_entry.entity_id,
                    legacy_uid,
                    new_uid,
                )
                migrated += 1
                break

        hass.config_entries.async_update_entry(entry, version=2)
        _LOGGER.info(
            "[culiplan][migrate] Entry %s upgraded v1 → v2 "
            "(%d entity unique_ids rewritten)",
            entry.entry_id,
            migrated,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Culiplan from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    async def _async_refresh_or_reauth() -> None:
        """Refresh the token, mapping failures to HA's config-entry exceptions.

        A 4xx from the token endpoint means the refresh token is gone server-side
        (revoked, expired, or rotated away) — only reauth can recover, so raise
        ConfigEntryAuthFailed to surface HA's reauthentication repair instead of
        a permanent silent setup-retry loop. 5xx / network errors are transient.
        OAuth2TokenRequestReauthError subclasses aiohttp.ClientResponseError, so
        this also covers HA cores that raise the plain aiohttp error.
        """
        try:
            await session.async_ensure_token_valid()
        except aiohttp.ClientResponseError as err:
            if 400 <= err.status < 500:
                raise ConfigEntryAuthFailed(
                    "Culiplan rejected the OAuth refresh token; reauthentication required"
                ) from err
            raise ConfigEntryNotReady(
                f"Culiplan token endpoint returned {err.status}"
            ) from err
        except aiohttp.ClientError as err:
            raise ConfigEntryNotReady(
                f"Could not reach the Culiplan token endpoint: {err}"
            ) from err

    await _async_refresh_or_reauth()

    async def _async_token() -> str:
        """Ensure the OAuth token is valid (refresh if near expiry) and return it.

        Shared by the REST client and the Socket.IO coordinator so a single
        OAuth2Session owns refresh — avoids two sessions racing a rotation and
        keeps long-lived entries from 401-ing once the initial token ages out.
        ConfigEntryAuthFailed raised here propagates through the coordinator,
        which triggers HA's reauth flow.
        """
        await _async_refresh_or_reauth()
        return cast(str, session.token["access_token"])

    client = CuliplanApiClient(
        session=aiohttp_client.async_get_clientsession(hass),
        access_token=session.token["access_token"],
        token_provider=_async_token,
    )

    coordinator = CuliplanCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )

    await _async_sync_custom_sentences(hass)
    await _register_intents(hass, entry)
    async_register_services(hass)
    async_register_cooking_services(hass)
    # Phase C (v0.3.0): expose Culiplan tools to any HA Conversation Agent
    # via the official llm.async_register_api() mechanism. Non-fatal if the
    # LLM helper is unavailable on older HA versions.
    async_register_llm_api(hass)
    # Panel first: it registers the /culiplan_static path that serves the card
    # bundles the Lovelace resources point at.
    await _async_register_sidebar_panel(hass)
    await _async_register_lovelace_resources(hass)
    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(lambda: async_unregister_services(hass))
    entry.async_on_unload(lambda: async_unregister_cooking_services(hass))
    entry.async_on_unload(lambda: async_unregister_llm_api(hass))
    # Reload the entry whenever OptionsFlow saves so the new ai_mode / pantry
    # windows / debug toggle take effect without requiring the user to
    # disable+enable the integration. Equivalent to OptionsFlowWithReload
    # (HA ≥ 2025.5) but compatible with the supported 2024.10 / 2025.4 matrix.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_sidebar_panel(hass: HomeAssistant) -> None:
    """Register the launch view + custom Lit panel.

    Replaces the old built-in iframe panel: the iframe panel navigated the
    top-level browser context to ``/api/culiplan/launch``, which never carried
    the HA ``Authorization`` header, causing a 401.  The custom panel fetches
    the endpoint via XHR (with the bearer token), receives a JSON redirect URL,
    and sets the iframe src itself.

    Idempotent: ``register_view`` accepts re-registration; the panel registration
    raises ``ValueError`` on a duplicate path which we treat as success.
    """
    # Imported lazily to avoid pulling the frontend module on integration
    # import (it pulls heavy dependencies that are not needed until setup).
    from homeassistant.components.frontend import async_register_built_in_panel

    # 1. HTTP view that issues the one-time SSO code and returns JSON.
    #    ``register_view`` is idempotent — calling it again replaces the existing route.
    hass.http.register_view(CuliplanLaunchView(hass))

    # 2. Serve the frontend directory from a dedicated static path. This
    #    covers both the sidebar panel (/culiplan_static/culiplan-panel.js)
    #    and the Lovelace card bundles (/culiplan_static/cards/<name>.js,
    #    see _LOVELACE_RESOURCES) — subdirectories are served too.
    #    cache_headers=False ensures the browser always gets the latest version
    #    after an integration update without requiring a hard-refresh.
    #    HA 2025.9+ removed the legacy synchronous register_static_path (it did
    #    blocking I/O in the event loop). Use async_register_static_paths with
    #    StaticPathConfig where available; fall back for older HA.
    static_dir = hass.config.path("custom_components/culiplan/frontend")
    try:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await hass.http.async_register_static_paths(
            [StaticPathConfig("/culiplan_static", static_dir, False)]
        )
    except ImportError:
        # HA < 2024.7 — legacy synchronous helper still works.
        hass.http.register_static_path(
            "/culiplan_static", static_dir, cache_headers=False
        )

    # 3. Register the custom Lit panel (web component) in the sidebar.
    #    HA exposes custom panels via the "custom" component_name of the
    #    built-in panel registry. The ``_panel_custom`` config block carries
    #    the LitElement metadata (element name, JS module URL, isolation flags).
    try:
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Culiplan",
            sidebar_icon="mdi:chef-hat",
            frontend_url_path=PANEL_URL_PATH,
            require_admin=False,
            config={
                "_panel_custom": {
                    "name": "culiplan-panel",
                    "module_url": f"/culiplan_static/culiplan-panel.js?v={MANIFEST_VERSION}",
                    "embed_iframe": False,
                    "trust_external": False,
                },
            },
        )
    except ValueError:
        # Panel already registered (HA reload / second config entry) — fine.
        pass


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        async_unregister_services(hass)

        # Remove sidebar panel only when the *last* config entry is unloaded;
        # if other entries remain, keep the panel so they keep working.
        if not hass.config_entries.async_entries(DOMAIN):
            try:
                from homeassistant.components.frontend import async_remove_panel

                async_remove_panel(hass, PANEL_URL_PATH)
            except (KeyError, ValueError, ImportError):
                pass

    return unload_ok


# ─── Assist sentence installation ────────────────────────────────────────────


def _sync_custom_sentences_sync(src_dir: Path, config_dir: Path) -> list[Path]:
    """Copy each shipped intents/<lang>.yaml into custom_sentences/<lang>/.

    Blocking helper — runs in the executor. Returns the destination paths
    that were actually written; a destination whose bytes already equal the
    source is skipped so unchanged files are never rewritten.
    """
    written: list[Path] = []
    for lang in _INTENT_LANGS:
        src = src_dir / f"{lang}.yaml"
        if not src.is_file():
            continue
        payload = src.read_bytes()
        dest = config_dir / "custom_sentences" / lang / _CUSTOM_SENTENCES_FILENAME
        if dest.is_file() and dest.read_bytes() == payload:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        written.append(dest)
    return written


async def _async_sync_custom_sentences(hass: HomeAssistant) -> None:
    """Install the Assist sentence files and reload conversation if needed.

    Never raises: a read-only config dir or a failed reload must not stop
    the integration from setting up — the sentences are then simply picked
    up on the next Home Assistant restart.
    """
    try:
        config_dir = Path(hass.config.config_dir)
        written = await hass.async_add_executor_job(
            _sync_custom_sentences_sync, _INTENTS_DIR, config_dir
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not install Culiplan Assist sentences into "
            "custom_sentences/ (%s); voice commands may not be recognised",
            err,
        )
        return
    if not written:
        _LOGGER.debug("Culiplan Assist sentences already up to date")
        return
    _LOGGER.info(
        "Installed Culiplan Assist sentences: %s",
        ", ".join(str(p) for p in written),
    )
    if "conversation" not in hass.config.components:
        _LOGGER.debug(
            "conversation integration not loaded; sentences load on next start"
        )
        return
    try:
        await hass.services.async_call("conversation", "reload", {}, blocking=True)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "conversation.reload failed after installing Culiplan sentences "
            "(%s); restart Home Assistant to pick them up",
            err,
        )


# ─── Assist intent registration ──────────────────────────────────────────────


async def _register_intents(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Culiplan Assist intents for the HA language.

    The YAML load is offloaded to the executor thread pool so the event loop
    is never blocked by synchronous file I/O (fixes blocking-call warning on
    HAOS 2025.11.0+).  Setup awaits this coroutine directly so intents are
    registered before async_setup_entry returns (closes voice-command race).
    """
    lang = hass.config.language.split("-")[0].lower()
    if lang not in _INTENT_LANGS:
        lang = "en"

    intents_file = _INTENTS_DIR / f"{lang}.yaml"
    if not intents_file.exists():
        intents_file = _INTENTS_DIR / "en.yaml"

    def _load_yaml_sync(path: Path) -> dict[str, Any]:
        """Blocking helper — runs in the executor thread pool."""
        return cast(
            dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        )

    async def _do_register(file_path: Path) -> None:
        try:
            data = await hass.async_add_executor_job(_load_yaml_sync, file_path)
        except Exception as err:
            _LOGGER.error("Failed to load Culiplan intents YAML: %s", err)
            return

        intents_data = data.get("intents", {})
        for intent_name in intents_data:
            # Cooking-mode intents are handled by local HA service calls.
            if intent_name in _COOKING_INTENT_TO_SERVICE:
                handler = _make_cooking_intent_handler(intent_name, entry)
            elif intent_name == _PANTRY_ADD_INTENT:
                handler = _make_pantry_add_intent_handler(entry)
            else:
                handler = _make_intent_handler(intent_name, entry)
            # async_register is idempotent (overwrites on reload).
            intent.async_register(hass, handler)

        _LOGGER.debug(
            "Registered %d Culiplan Assist intents (lang=%s)",
            len(intents_data),
            lang,
        )

    await _do_register(intents_file)


def _make_intent_handler(intent_name: str, entry: ConfigEntry) -> intent.IntentHandler:
    """Return an IntentHandler for a single Culiplan intent.

    We create a fresh class per intent so that `intent_type` is a proper
    class-level attribute (HA asserts it via getattr and stores by type).
    """

    class _Handler(intent.IntentHandler):
        intent_type = intent_name

        async def async_handle(
            self, intent_obj: intent.Intent
        ) -> intent.IntentResponse:
            data = intent_obj.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not data:
                return _speech(intent_obj, "Culiplan is not connected.")
            client: CuliplanApiClient = data["client"]
            tool = _INTENT_TO_TOOL.get(intent_name)
            if not tool:
                return _speech(intent_obj, "That intent is not configured.")
            # Rename sentence slots to the tool's parameter names and drop
            # empty ones; wildcard slot text carries trailing whitespace.
            slot_map = _INTENT_SLOT_TO_PARAM.get(intent_name, {})
            params: dict[str, Any] = {}
            for slot_name, slot in intent_obj.slots.items():
                value = slot.get("value")
                if isinstance(value, str):
                    value = value.strip()
                if value in (None, ""):
                    continue
                params[slot_map.get(slot_name, slot_name)] = value
            fallback = "Sorry, Culiplan couldn't complete that request."
            try:
                result = await client.async_execute_voice_tool(
                    tool, params, language=_intent_language(intent_obj)
                )
            except Exception as err:
                _LOGGER.error("Voice tool '%s' failed: %s", tool, err)
                return _speech(intent_obj, fallback)
            spoken = result.get("speakableResponse") or result.get("message")
            if result.get("success") is False:
                # HTTP 200 with a spoken error — surface the backend's text.
                _LOGGER.warning(
                    "Voice tool '%s' rejected the request: %s", tool, spoken
                )
                return _speech(intent_obj, spoken or fallback)
            return _speech(intent_obj, spoken or "Done.")

    return _Handler()


def _make_cooking_intent_handler(
    intent_name: str, entry: ConfigEntry
) -> intent.IntentHandler:
    """
    Return an IntentHandler for a cooking-mode intent that delegates to
    a local HA service call rather than the remote voice-tool endpoint.

    This keeps the session-management logic in cooking_services.py (single source
    of truth) and avoids duplicating HTTP calls from the intent layer.
    """
    service_name = _COOKING_INTENT_TO_SERVICE[intent_name]

    class _CookingHandler(intent.IntentHandler):
        intent_type = intent_name

        async def async_handle(
            self, intent_obj: intent.Intent
        ) -> intent.IntentResponse:
            slots: dict[str, Any] = {
                k: v.get("value") for k, v in intent_obj.slots.items()
            }
            # Map intent slot names to service field names
            service_data: dict[str, Any] = {}
            if "label" in slots and slots["label"]:
                service_data["label"] = slots["label"]
            if "label_or_id" in slots and slots["label_or_id"]:
                service_data["label_or_id"] = slots["label_or_id"]
            if "duration_sec" in slots and slots["duration_sec"]:
                try:
                    service_data["duration_sec"] = int(slots["duration_sec"])
                except (TypeError, ValueError):
                    pass

            try:
                await intent_obj.hass.services.async_call(
                    DOMAIN,
                    service_name,
                    service_data,
                    blocking=True,
                )
                # Map service to a friendly spoken response.
                if service_name == "advance_cooking_step":
                    text = "Moving to the next cooking step."
                elif service_name == "set_recipe_timer":
                    label = service_data.get("label", "")
                    text = f"Starting the {label} timer."
                elif service_name == "cancel_recipe_timer":
                    label = service_data.get(
                        "label_or_id", service_data.get("label", "")
                    )
                    text = f"Cancelled the {label} timer."
                else:
                    text = "Done."
            except Exception as err:
                _LOGGER.error(
                    "Cooking intent '%s' (service %s) failed: %s",
                    intent_name,
                    service_name,
                    err,
                )
                text = "Sorry, Culiplan couldn't complete that cooking action."
            return _speech(intent_obj, text)

    return _CookingHandler()


def _make_pantry_add_intent_handler(entry: ConfigEntry) -> intent.IntentHandler:
    """Return the IntentHandler for CuliplanAddToPantry.

    Slots: ``item`` (wildcard, required) and ``location`` (optional; one of
    PANTRY_LOCATIONS, defaults to "pantry"). Goes through
    services._call_pantry_add so the intent, the service and the LLM tool
    share one code path and one error translation.
    """

    class _PantryAddHandler(intent.IntentHandler):
        intent_type = _PANTRY_ADD_INTENT

        async def async_handle(
            self, intent_obj: intent.Intent
        ) -> intent.IntentResponse:
            data = intent_obj.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not data:
                return _speech(intent_obj, "Culiplan is not connected.")
            client: CuliplanApiClient = data["client"]
            slots: dict[str, Any] = {
                k: v.get("value") for k, v in intent_obj.slots.items()
            }
            item = str(slots.get("item") or "").strip()
            if not item:
                return _speech(intent_obj, "Sorry, I didn't catch what to add.")
            location = str(slots.get("location") or "pantry").strip().lower()
            if location not in PANTRY_LOCATIONS:
                location = "pantry"
            lang = _intent_language(intent_obj)
            try:
                result = await _call_pantry_add(
                    client, item, location=location, language=lang
                )
            except Exception as err:
                _LOGGER.error("Pantry add intent failed for '%s': %s", item, err)
                return _speech(
                    intent_obj, "Sorry, Culiplan couldn't add that to your pantry."
                )
            return _speech(intent_obj, _pantry_add_speech(lang, item, location, result))

    return _PantryAddHandler()


def _pantry_add_speech(
    lang: str, item: str, location: str, result: dict[str, Any]
) -> str:
    """Localised confirmation for a pantry add (see _PANTRY_ADD_SPEECH)."""
    entry = _PANTRY_ADD_SPEECH.get(lang)
    if entry is None:
        backend = result.get("speakableResponse")
        if isinstance(backend, str) and backend:
            return backend
        entry = _PANTRY_ADD_SPEECH["en"]
    template, locations = entry
    return template.format(
        item=item, location=locations.get(location, locations["pantry"])
    )


def _intent_language(intent_obj: intent.Intent) -> str:
    """Base language code ("nl" for "nl-BE") of the intent, else of HA."""
    language = str(
        getattr(intent_obj, "language", None) or intent_obj.hass.config.language or "en"
    )
    return language.split("-")[0].lower()


def _speech(intent_obj: intent.Intent, text: str) -> intent.IntentResponse:
    response = intent_obj.create_response()
    response.async_set_speech(text)
    return response
