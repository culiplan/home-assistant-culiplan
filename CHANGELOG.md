# Changelog

All notable changes to the Culiplan Home Assistant integration are documented here.

## [Unreleased]

### Fixed
- **SSO panel 401 fix** — replaced the built-in iframe panel with a custom Lit
  web component (`culiplan-panel`).  The old iframe panel navigated the top-level
  browser context to `/api/culiplan/launch`, which never carried the HA
  `Authorization` header; the view returned 401.  The new panel runs inside
  HA's authenticated frontend, fetches `/api/culiplan/launch` via XHR with
  the HA bearer token, receives `{"redirect_url": "…", "expires_in": 60}`,
  and sets the iframe `src` to the returned URL.  The SSO code remains in the
  URL fragment (`#`) and is never sent to any server.
- `launch_view.py` now returns JSON instead of a 302 redirect.  Error shapes
  are `{"error": "<short_code>", "message": "<human-readable>"}` with HTTP
  502 (backend failure) or 503 (no config entry / token expired).
- The panel serves its JS from `/culiplan_static/culiplan-panel.js` via
  `hass.http.register_static_path` with `cache_headers=False` so updates
  are picked up immediately after an integration reload.

> **Beta v0.2.0 users:** after updating, open the HA sidebar and reload the
> Culiplan panel once (browser hard-refresh or Settings → Developer Tools →
> Clear cache).  The new Lit panel replaces the old iframe entry automatically.

## [0.2.0] - 2026-06-03

### Breaking Changes

**Entity IDs, service names, and Lovelace card identifiers renamed from `flavorplan*` to `culiplan*`.**
Beta users upgrading from v0.1.x must: remove the integration from Settings → Integrations, then
re-add it via HACS or manually. Re-import any blueprints from `blueprints/automation/culiplan/`.
Recreate Lovelace dashboards from the bundled YAML files in `lovelace/dashboards/` — replace all
`custom:flavorplan-*` card types with `custom:culiplan-*` and update any entity_id references
(e.g. `calendar.flavorplan_meal_plan` → `calendar.culiplan_meal_plan`).

### Fixed
- OAuth config flow now sends PKCE (`code_challenge` S256 + `code_verifier`) as required
  by the Culiplan OAuth 2.1 backend for the public `ha-core` client. HA's default
  `LocalOAuth2Implementation` omits PKCE, which caused `invalid_request:
  code_challenge is required (PKCE S256)` on first link.
- OAuth config flow now requests the required scopes (`calendar:read`, `todo:read/write`,
  `pantry:*`, `meals:*`, `shopping:*`, `recipes:read`, `profile:read`, `household:read`,
  `subscription:read`, `ai:suggestions`, `blueprints:generate`, `openid`, `offline_access`).
  Scope list lives in `const.py:OAUTH2_SCOPES` as a single source of truth, mirroring
  `ha-core`'s `allowedScopes` in the backend seed.

### Changed
- Brand rename across all user-facing strings: Flavorplan → Culiplan. `hacs.json` name
  field updated to `"Culiplan"`.
- Iframe sidebar panel added for embedded Culiplan web UI within Home Assistant.

### Added
- OAuth PKCE (S256 code challenge/verifier) support for OAuth 2.1 compliance.
- Scoped OAuth: explicit scope list in `const.py:OAUTH2_SCOPES` matching backend seed.

## [0.1.0] — 2026-04-25

### Added
- Initial scaffold: `manifest.json`, `__init__.py`, `config_flow.py`, `const.py`, `api.py`, `coordinator.py`
- OAuth 2.0 config flow using HA's `application_credentials` + `config_entry_oauth2_flow` helpers
  — connects to `https://api.culiplan.com/api/oauth/authorize` and `/api/oauth/token`
- AI provider selection step: Cloud AI (default), BYOK, Local AI
- Platform stubs: `calendar.py`, `sensor.py`, `todo.py` (entities added in tasks 1365–1368)
- Translations: en, nl, de, fr, es
- LICENSE (Apache 2.0)
- CI: hassfest + HACS action on push / pull_request
- Pre-commit: gitleaks secret scanning

### Pinned AI library versions (smoke-tested 2026-04-25)

| Library | Version | Purpose |
|---|---|---|
| `openai` | `1.77.0` | BYOK / Local AI via OpenAI-compatible API |
| `anthropic` | `0.49.0` | BYOK Claude models |
| `google-genai` | `1.12.0` | BYOK Gemini models |

> **Note:** Update these pins in `manifest.json` before each HACS release.
> Run `pip install openai anthropic google-genai` in a clean venv and capture
> the installed versions.

### Beta limits
- Calendar, todo, and sensor entities are stubs — they load without error but
  expose no data until tasks 1365–1368 are complete.
- Only the HACS beta channel is supported in this release.
- HA Core submission is deferred pending community validation.
