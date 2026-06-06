# Changelog

All notable changes to the Culiplan Home Assistant integration are documented here. Format adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.7.0] — 2026-06-06

Feature release. Native Home Assistant update entity — updates now appear the standard HA way.

### Added

- **`update.culiplan_update` entity.** A first-class HA `update` entity now surfaces the integration's own updates on the **device page** and in **Settings → Updates** (alongside HA core / OS / add-ons), with installed vs latest version, release notes, and an **Install** button — no HACS required. It polls GitHub for the latest release every 6 hours (and on demand). Pressing **Install** reuses the v0.6.0 self-updater (`updater.async_perform_update`: download → backup → swap → rollback-on-failure) and then restarts Home Assistant. This is now the recommended way to update; the v0.6.0 Options-flow "Check for updates" toggle remains as a fallback.

## [0.6.0] — 2026-06-06

Feature release. One-button self-updater — no HACS, no terminal required.

### Added

- **Self-updater in Options flow.** A new "Check for updates" toggle in **Settings → Devices & Services → Culiplan → Configure** checks GitHub for the latest release. If a newer version is found, a confirmation step shows the current version, the available version, and the release notes. Ticking "Update now" downloads the release zip directly from GitHub, backs up the current `custom_components/culiplan/` directory to `culiplan.bak`, extracts the new files into place, and schedules a 2-second delayed Home Assistant restart. On any failure after the backup step the old version is restored automatically from `.bak` and an error is shown — safe to retry. The `.bak` is removed only on success.
- **`updater.py` module** — new stdlib-only (no extra dependencies) async helper module with three public symbols: `LatestRelease` dataclass, `async_check_latest(hass)` (GitHub API call via HA shared session), `is_newer(latest, current)` (numeric dotted-semver comparison), and `async_perform_update(hass, zipball_url)` (download → extract → zip-slip guard → backup → swap → cleanup). All blocking filesystem/zip work runs via `hass.async_add_executor_job` to keep the event loop free.
- **New translation keys** (both `strings.json` and `translations/en.json`): `options.step.update`, `options.error.update_check_failed`, `options.error.update_failed`, `options.abort.up_to_date`, `options.abort.update_check_failed`, `options.abort.update_started`, and `options.step.init.data.check_for_update` with its `data_description`.

## [0.5.0] — 2026-06-06

Feature release. Self-service updates from inside the Culiplan panel.

### Added

- **In-panel update helper.** The custom panel now reads the HACS-managed `update.*` entity for this integration and bridges it to the embedded app via `postMessage`: it posts the installed/latest versions and whether an update is available, and accepts three commands back — `refresh` (force HACS to re-check GitHub via `homeassistant.update_entity`), `install` (download the new version via `update.install`), and `restart` (`homeassistant.restart`). The app uses this to show an update nudge, a "Home Assistant" section in Settings with a **Check for updates** button and an **Auto-update** toggle, and an explicit **Restart now / Later** prompt after a download (a restart is always user-confirmed, never silent). Falls back gracefully (no nudge) when no HACS update entity is present.

## [0.4.0] — 2026-06-06

Feature release. Enables in-panel barcode scanning for the kitchen-tablet use case.

### Added

- **Camera barcode scanning in the embedded app.** The custom panel's iframe now sets `allow="camera"`, delegating camera permission into the cross-origin Culiplan app so it can use `getUserMedia` to scan product barcodes and add them straight to the pantry — without leaving Home Assistant. HA's *built-in* iframe panel hardcodes `allow="fullscreen"` and cannot do this; this integration owns its iframe, so it grants camera itself. On a wall-mounted tablet the app defaults to the **front** camera (the rear faces the wall) with a flip control, and decodes via `html5-qrcode`, which works in Safari / iOS WKWebView (the HA Companion app) where the browser `BarcodeDetector` API is unavailable. A camera icon appears in the app's embed top-bar only when a camera is present.

## [0.3.2] — 2026-06-05

Bug-fix release. Corrects the "meals planned this week" sensor week window
and unbreaks the CI test matrix on HA latest.

### Fixed

- **"Meals planned this week" sensor under-counted earlier-in-week meals.** `MealsPlanedThisWeekSensor.native_value` computed `week_start = now - timedelta(days=now.weekday())`, which keeps the *current time-of-day* instead of snapping to midnight Monday. The effect: once the current time passed a slot's time on a later weekday (e.g. on Friday afternoon), that earlier meal — a Monday 18:00 dinner — fell *before* the window and was dropped from the count. `week_start` is now normalized to `00:00:00` so the window always covers the full ISO week.

### CI

- **Test suite re-greened on HA 2026.6.0.** `test_llm_api.py::test_get_api_instance_returns_tools` constructed `LLMContext` with a hard-coded kwarg list; HA 2026.x removed the `user_prompt` field, raising `TypeError: LLMContext.__init__() got an unexpected keyword argument`. The test now builds its kwargs from the live `LLMContext` signature via `inspect.signature`, so it passes across every HA version in the matrix (2024.10.0 / 2025.1.4 / 2026.6.0).

## [0.3.1] — 2026-06-05

Phase B of the Gold → Platinum (Diamant) roadmap. All four Platinum-tier
HA quality-scale rules now claimable. Compliance-only refactor — no
behaviour change. `manifest.json` `quality_scale` advanced from `gold`
to `platinum`.

### Changed

- **`inject-websession` (Platinum).** Every remaining `aiohttp.ClientSession()` constructor across the integration removed; all HTTP calls now route through `homeassistant.helpers.aiohttp_client.async_get_clientsession(hass)` so HA owns the connection pool and DNS resolution centrally. Migrated call sites: `config_flow._fetch_culiplan_account_id`, `config_flow._call_migrate_preview`, `config_flow._call_migrate_start`, `MealieOptionsFlow.async_step_mealie_rollback`, and the LAN-probe helpers `ai.local_ai.probe_local_ai_endpoints` + `probe_custom_endpoint` (which now take `hass` as their first argument). `grep -rn 'aiohttp\.ClientSession()' custom_components/culiplan/` returns zero matches.
- **`strict-typing` (Platinum).** `mypy --strict` now passes against the integration's own code with **zero entries in `pyproject.toml [tool.mypy] disable_error_code`** — reduced from 8 globally-suppressed error codes in v0.3.0 (`misc`, `type-arg`, `untyped-decorator`, `assignment`, `call-arg`, `import-untyped`, `unused-ignore`, `no-untyped-def`) to none. Remaining stub-gap silences are localized per-line with explanatory comments (4× `untyped-decorator` on python-socketio handlers, 3× `attr-defined` on lagging HA component re-exports, 2× `override` on `dict[str, Any]` config-flow returns kept for HA 2024.10 floor, 1× `call-arg` on `DataUpdateCoordinator config_entry` for the same reason, 1× `misc,assignment` on the `_HomeAssistantError` ImportError fallback). Pre-existing errors at `launch_view.py:38` (HomeAssistantView re-export) and `__init__.py:339` (redundant cast) resolved; ~8 unused `# type: ignore[arg-type]` / `[import]` comments in `ai/dispatchers.py` + `ai/key_store.py` deleted.
- **`async-dependency` (Platinum).** Audited all four PyPI-pinned runtime deps. The integration uses the async client variants throughout — `AsyncOpenAI`, `AsyncAnthropic`, `genai.Client.aio.*`, and `socketio.AsyncClient`. No sync `OpenAI()` / `Anthropic()` / `socketio.Client()` constructor exists in the codebase. Status flipped from `todo` to `done` in `quality_scale.yaml` with the per-dep mapping documented.
- **`entity-event-setup` (Platinum).** Re-verified for v0.3.1: all entity classes (sensor, binary_sensor, calendar, todo) inherit `CoordinatorEntity`, which handles the coordinator subscription lifecycle automatically. No entity subscribes to extra HA bus events, Socket.IO events, or any other external signal source, so no manual `async_on_remove` wiring is required. `quality_scale.yaml` comment expanded to record the verification.

### Documentation

- Roadmap: `backlog/docs/ha-integration-gold-platinum-roadmap-2026-06-05.md` (Phase B, B1–B5).

## [0.3.0] — 2026-06-05

### Added

- **`llm.API` registration — Culiplan tools available to any HA Conversation Agent.** New module `custom_components/culiplan/llm_api.py` registers Culiplan with HA's official LLM helper (`homeassistant.helpers.llm.async_register_api`). Any user who already has an HA Conversation Agent configured (OpenAI / Anthropic / Google / Ollama / HA Voice Preview) can now select "Culiplan" under the agent's "Control Home Assistant" dropdown and the LLM gets six Culiplan tools natively — no Culiplan BYOK setup required for users who only want the LLM tools surface. Tools shipped: `get_meal_plan` (date-range optional), `suggest_meal` (routes through the existing AI dispatcher so Premium gating and BYOK key resolution are preserved), `add_to_shopping_list`, `find_recipes_by_ingredients`, `get_recipe`, `get_pantry_items` (expiring-within-days filter). All tools reuse `CuliplanApiClient` methods and the same permission/Premium-gating as the integration's services. The Conversation Agent's LLM key is used only for natural-language understanding; Culiplan's own AI runs for `suggest_meal`. Deregister on unload via direct pop from `hass.data["llm"]` (HA does not yet expose `async_unregister_api`).
- **Standard intents — `HassListAddItem` routes into the Culiplan todo entity.** No new wiring required: the `CuliplanShoppingList` entity already subclasses `TodoListEntity` and exposes `TodoListEntityFeature.CREATE_TODO_ITEM`, which is the contract HA's built-in shopping-list intent handler dispatches against. Users who have selected `todo.culiplan_shopping_list` as their active list now get "add milk to my shopping list" working out of the box.

### Documentation

- Pairs with the wiki "three integration paths" page at `docs/integrations/home-assistant-paths.md`.
- Roadmap: `backlog/docs/ha-integration-gold-platinum-roadmap-2026-06-05.md` (Phase C).

## [0.2.6] — 2026-06-05

### Added

- **`quality_scale.yaml`.** New file enumerates every Bronze / Silver / Gold / Platinum rule with `done` / `exempt` / `todo` + comment. Backs up the `quality_scale: gold` claim in `manifest.json` with an auditable per-rule trail. Platinum rules (`inject-websession`, `strict-typing`, `async-dependency`) tagged `todo` with a v0.3.0 target.

### Changed

- **`api.py` 403 raise now uses `translation_key`.** The last non-translated `raise HomeAssistantError("Culiplan API returned 403…")` call site was migrated to `translation_domain=DOMAIN, translation_key="api_forbidden"`. Every `HomeAssistantError` raised by the integration now goes through `strings.json` / `translations/<lang>.json`, satisfying the Gold `exception-translations` rule end-to-end.
- **Panel JS now uses `hass.callApi()` instead of raw `fetch()` + manual token extraction.** Previously the sidebar panel read the bearer token directly off `this._hass.auth.data.access_token` — a private HA internal field — and built its own `Authorization` header. A stale-token 401 today (after an HA session rotation) surfaced the fragility. `hass.callApi("GET", "culiplan/launch")` pulls a current token off the hass object internally and handles refresh across HA versions; on non-2xx it throws `{ status_code, body }`, which we now map to a clear "session expired" message for 401 and a passthrough message for everything else. No behaviour change on the happy path.

### Documentation

- **Wiki: five Gold `docs-*` sub-rules added** in `docs/integrations/home-assistant.md` (Culiplan monorepo, separate commit) — automation examples, troubleshooting, known limitations, removal instructions, supported devices.

## [0.2.5] — 2026-06-05

### Fixed

- **Hassfest `CONFIG_SCHEMA` warning.** HA Core's hassfest linter (dev branch) warns when an integration defines `async_setup` without declaring a config schema. Added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` to signal that Culiplan is config-entry-only — YAML setup is unsupported and will surface HA's standard deprecation warning if attempted. No runtime behaviour change. Verified with `python -m script.hassfest --action validate` (HA dev container): "Integrations: 1, Invalid integrations: 0" with zero warnings.

## [0.2.4] — 2026-06-05

### Added

- **Welcome Lovelace card.** Drop-in YAML at `lovelace/cards/culiplan-welcome-card.yaml` gives users a one-tap "Open Culiplan" tile on any HA dashboard. Uses the built-in `button` card (no custom JS), shows the live "meals planned this week" count, and taps through to the Culiplan sidebar panel. See `lovelace/README.md` for import instructions.

## [0.2.3] — 2026-06-05

### Added

- **HA theme tokens bridged into the embedded iframe.** The panel JS reads `getComputedStyle(document.documentElement)` for HA's 12 design tokens (`--primary-color`, `--card-background-color`, `--primary/secondary-text-color`, `--divider-color`, `--accent-color`, error/success/warning, etc.) and posts them via `postMessage` to the Culiplan web app on iframe load and on every `hass` state update. The web app applies them as CSS variable overrides on `:root` — embedded Culiplan now follows HA's dark mode / accent color instead of always rendering light. Token names whitelisted on both sides; arbitrary CSS variable injection is not possible. Pairs with the matching listener in `culiplan/Flavorplan@master`.

## [0.2.2] — 2026-06-05

### Added

- **Embed-mode signaling.** The `redirect_url` returned by `/api/culiplan/launch` now includes `?embed=ha` before the SSO code fragment. The web app reads this on boot, persists it via `sessionStorage`, and applies a `body.embed-mode` class on every route. CSS hides the duplicate sidebar / logo / account block / greeting / notification bell when running inside the HA iframe, recovering the full content width. Outside embed mode nothing changes.

## [0.2.1] — 2026-06-05

### Fixed

- **Panel JS cache-bust on version bump.** Read the manifest version at module load time and append it to the sidebar panel `module_url` (`/culiplan_static/culiplan-panel.js?v=0.2.1`). Browsers refetch the module on each version bump — no more hard-refresh required after an update.

## [0.2.0] — 2026-06-05

First production release with all P0 issues from the 2026-06-04/05 smoke-test sessions fixed. Tag `v0.2.0` was retagged ~5 times during the smoke-test session before SemVer discipline was adopted — from `v0.2.1` onward, every tag is immutable.

### Fixed

- **Calendar entity collapse.** Backend returns meal plans grouped by date (`{date: {slot: [entry]}}`). The previous implementation emitted one calendar entity per date — 11+ entities/week observed. The integration now flattens the response into ONE `calendar.culiplan` entity (`id="current"`) with N events across the dates, matching the user's mental model of a continuous timeline. Stable `unique_id` so the entity survives coordinator refreshes without re-registering.
- **`entry.options` ⇄ `entry.data` mismatch.** OptionsFlow saves were silently ignored: `services.py` and `blueprint_generator.py` read AI mode / BYOK provider / local endpoint from `entry.data`, while the flow wrote them to `entry.options`. Both call sites now merge `{**entry.data, **entry.options}` so Settings changes actually take effect at runtime.
- **`expiry_days` / `expiry_hours` dead options wired.** Both were consumed by `sensor.py` and `binary_sensor.py` but had no UI surface — defaults baked in at 3 days / 48 hours. Now exposed in the Settings dialog as `NumberSelector` slider + box, configurable 1–30 days / 1–168 hours.
- **`debug_ai` access path corrected.** Was read via `entry_data.get("options", {}).get("debug_ai")` — `entry_data` is `hass.data[DOMAIN][entry_id]` (a runtime dict), NOT the `ConfigEntry`. Re-routed through the merged `entry_config` so the toggle actually engages.
- **Loopback warning re-runs on reconfigure.** Task-1413's non-loopback Local AI endpoint warning fired in the initial config flow but was skipped when the user reconfigured to a remote endpoint via OptionsFlow. The same warning step now runs in both flows.
- **Mealie offer step auto-skipped when Mealie not installed.** Checks `hass.config_entries.async_entries("mealie")` — if empty, skips directly to entry creation. Cuts friction for users without a Mealie server.
- **OAuth credential auto-imported on first install.** The "Add application credentials" dialog appeared on every fresh install because `async_setup` never runs before the first config entry exists — HA loads the integration only after entry creation, but the dialog fires before. The fix imports the built-in `ha-core` client credential inside `async_step_user` itself, idempotent on re-call, so pick_implementation finds it on the first OAuth attempt.
- **Sidebar panel rewritten as vanilla web components.** The previous Lit-based panel used a bare `import "lit"` specifier that browsers don't resolve, producing `Failed to resolve module specifier "lit"` and a blank panel. Rewritten as `HTMLElement` + Shadow DOM — no third-party deps, no CDN, no bundler.
- **Panel registration: `async_register_built_in_panel` with `component_name="custom"`.** The previous `async_register_panel_custom` API was removed.
- **OAuth credential `auth_domain` argument.** Was passing `"Culiplan"` (capital C) as the fourth positional arg, which sets `auth_domain="Culiplan"` — HA's lookup uses `auth_domain="culiplan"` (matching the domain), so the credential was stored under a key HA never looked up. Argument removed (defaults to `DOMAIN`).

### HA 2024.10 – 2026.6 compatibility sweep

The CI matrix tested HA 2024.10 + 2025.4 (Python 3.12); a user installed on HA 2026.6.0 / Python 3.14.2 and hit six API breakages we hadn't caught. Each is fixed and the CI matrix now also covers HA 2026.6 / Python 3.14 so this class of issue lands as a red build:

- `register_static_path` (sync, blocking-IO) → `async_register_static_paths` + `StaticPathConfig` with an `ImportError` fallback for the 2024.10 lane.
- `DataUpdateCoordinator.__init__` now requires `config_entry=` kwarg (HA 2025.10+) — passed with a `TypeError` catch for older HA.
- `OptionsFlow.__init__(config_entry)` removed (HA 2025.12+) — switched to no-arg ctor + `self.config_entry` framework injection.
- `async_create_issue` no longer accepts `is_persistent` (HA 2025.4+) — kwarg dropped (default was False anyway).
- `hass.components.lovelace` proxy removed (HA 2025.8+) — switched to `hass.data.get("lovelace")`.
- AI SDK pins relaxed (`==` → `>=`) so pip can resolve Python 3.14 wheels (the `openai==1.77.0` wheel does not exist for 3.14).

### Added

- **Settings dialog redesigned with HA selectors.** `NumberSelector` (slider + box), `SelectSelector` (LIST + DROPDOWN modes), `BooleanSelector`, `TextSelector(PASSWORD/URL, autocomplete=off)`. Localized strings for every step (`options.step.*` and `options.error.*` blocks added to `strings.json`). Replaces unlabeled raw schema keys (`ai_mode`, `byok_provider`, `local_endpoint`) that the old options flow rendered.
- **`async_step_reconfigure`** (Gold-tier "reconfiguration-flow" rule). Fetches the user's Culiplan account ID from `/api/users/me` after OAuth, compares against the entry's `unique_id`, and aborts with `wrong_account` on mismatch — preventing accidental re-pointing of an entry at a different account. On match, merges the new tokens into existing entry data and triggers a reload. Same-account reconfigure preserves AI mode / BYOK / Mealie state.
- **`OptionsFlowWithReload` equivalent.** `__init__.py` now registers an update listener so OptionsFlow saves auto-reload the entry. Works on the supported 2024.10 / 2025.4 CI matrix where `OptionsFlowWithReload` isn't yet exported.
- **Sidebar icon `mdi:chef-hat`** (replacing `mdi:silverware-fork-knife`) for brand consistency with the integration card and brand assets.
- **Local brand assets** (`custom_components/culiplan/brand/icon.png` + `logo.png`) for HA device-card branding. PR to `home-assistant/brands` is prepared at `/tmp/brands/add-culiplan` but not yet pushed — picker placeholder remains until that lands.

### Documentation

- Design doc: `backlog/docs/ha-integration-settings-redesign-2026-06-05.md` (Settings page IA + rationale).
- Handoff doc: `backlog/docs/ha-integration-handoff-2026-06-05.md`.
- UX roadmap: `backlog/docs/ha-integration-ux-improvements-2026-06-05.md` (P0–P5, F1–F9, pre-HACS gate list).

## [0.1.1] — 2026-04-26

Beta release. Initial OAuth flow, AI provider selection, scaffolded entities. **Superseded by 0.2.0** — users upgrading should reinstall via HACS.

## [0.1.0] — 2026-04-25

### Added

- Initial scaffold: `manifest.json`, `__init__.py`, `config_flow.py`, `const.py`, `api.py`, `coordinator.py`.
- OAuth 2.0 config flow using HA's `application_credentials` + `config_entry_oauth2_flow` helpers — connects to `https://api.culiplan.com/api/oauth/authorize` and `/api/oauth/token`.
- AI provider selection step: Cloud AI (default), BYOK, Local AI.
- Platform stubs: `calendar.py`, `sensor.py`, `todo.py`.
- Translations: en, nl, de, fr, es.
- LICENSE (Apache 2.0).
- CI: hassfest + HACS action on push / pull_request.
- Pre-commit: gitleaks secret scanning.

[0.2.6]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.6
[0.2.5]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.5
[0.2.4]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.4
[0.2.3]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.3
[0.2.2]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.2
[0.2.1]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.1
[0.2.0]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.2.0
[0.1.1]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.1.1
[0.1.0]: https://github.com/culiplan/home-assistant-culiplan/releases/tag/v0.1.0
