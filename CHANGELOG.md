# Changelog

All notable changes to the Flavorplan Home Assistant integration are documented here.

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
