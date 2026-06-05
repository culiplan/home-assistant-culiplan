# Culiplan for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/culiplan/home-assistant-culiplan.svg)](https://github.com/culiplan/home-assistant-culiplan/releases)
[![License](https://img.shields.io/github/license/culiplan/home-assistant-culiplan.svg)](LICENSE)

Bring your [Culiplan](https://culiplan.com) meal planning account into Home Assistant.

> **Phase 3** — Cooking Mode card (`culiplan-cooking-mode`) is now live. Calendar, to-do,
> sensor entities, Assist intents and the full Lovelace card pack (Kitchen Dashboard + Pantry
> Tracker + Cooking Mode) are available. Report issues at [GitHub Issues](https://github.com/culiplan/home-assistant-culiplan/issues).

---

## Features

### Entities

| Entity | Description |
|---|---|
| `calendar.culiplan_meal_plan` | One event per planned meal; dinner-party events included |
| `todo.culiplan_shopping_list` | Active shopping list — items can be checked off or added |
| `sensor.culiplan_meals_today` | Number of meals planned today |
| `sensor.culiplan_shopping_items` | Count of unchecked shopping list items |
| `sensor.culiplan_expiring_pantry` | Pantry items expiring within 3 days |
| `sensor.culiplan_planned_kwh_today` | Estimated cooking energy (kWh) for today's planned meals — Phase 3 |

Voice (Assist): say "Add bread to the shopping list" or "What's for dinner tonight?" once the integration is linked.

### Lovelace Card Pack

Three custom cards with Culiplan's mobile design language, installed automatically alongside
the integration. See [lovelace/README.md](lovelace/README.md) for installation details.

| Card | Type | Description |
|---|---|---|
| Kitchen Dashboard | `custom:culiplan-kitchen-dashboard` | Today's meals with recipe image, servings, time and shopping shortcut |
| Pantry Tracker | `custom:culiplan-pantry-tracker` | Tile grid with expiry warnings, low-stock indicator and inline actions |
| Cooking Mode | `custom:culiplan-cooking-mode` | Step-by-step cooking session: step list, active timers, voice "next step" shortcut |

**Four pre-configured dashboard YAMLs** ship in `lovelace/dashboards/`:
- `kitchen-tablet.yaml` — 10" landscape tablet, three-column layout
- `phone-quick-view.yaml` — single-column mobile view
- `voice-pe-companion.yaml` — wall display / Voice PE companion
- `energy-meal-cost.yaml` — planned kWh gauge + history graph (Phase 3, requires `sensor.culiplan_planned_kwh_today`)

**Design tokens** (`lovelace/tokens.css`) are `:root`-scoped so users can override the brand
colour and any token via [card-mod](https://github.com/thomasloven/lovelace-card-mod).

---

## Installation

### Via HACS (recommended)

1. In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/culiplan/home-assistant-culiplan` as an **Integration**.
3. Search for **Culiplan** and install.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration → Culiplan**.

### Manual

Copy `custom_components/culiplan/` into your HA `custom_components/` directory and restart.

---

## Setup

1. Click **Add Integration** and search for **Culiplan**.
2. A browser window opens — log in with your Culiplan account and approve the requested scopes.
3. Choose your AI mode (see below).
4. Done — entities appear within a few seconds.

---

## AI Modes

Culiplan supports three AI execution modes, selectable during setup and changeable later via **Configure**:

### Cloud AI (default)

Culiplan's servers process AI requests on your behalf.

- **Requires:** Active Culiplan Premium subscription.
- **Privacy:** Prompt content (your voice commands) travels to `api.culiplan.com`. No data is sold or shared with third parties. See the [privacy policy](https://culiplan.com/privacy).
- **Cost:** Included in the Premium subscription; no additional AI API costs.

### Bring Your Own Key (BYOK)

Your API key is stored exclusively in Home Assistant's local secrets store. AI calls go directly from your HA install to the AI provider — Culiplan is not in the network path.

- **Requires:** An account with OpenAI, Anthropic, or Google AI Studio.
- **Privacy:** Your API key and prompt content never reach Culiplan's servers. Zero-custody — Culiplan has nothing to lose.
- **Cost:** You pay the AI provider directly at their published token rates. For typical household use this is a few euro cents per month.
- **Free to use** — no Culiplan Premium required.

### Local AI

Requests go to your own Ollama or LM Studio instance on your local network.

- **Requires:** A running local LLM server (e.g., `ollama serve`).
- **Privacy:** All AI processing stays on your hardware. Nothing leaves your home network.
- **Cost:** Your electricity and hardware costs only.
- **Free to use** — no Culiplan Premium required.

> **Note on premium features:** The tier line is on capability, not on AI provider. If a feature requires Premium (e.g., Cloud AI recipe generation), it requires Premium with BYOK too — BYOK doesn't unlock premium features for free. It only removes Culiplan's AI infrastructure costs from the equation for features that are otherwise AI-provider-neutral.

---

## Privacy

Culiplan is a European company (Belgium) built with privacy-by-design as a first principle.

- **Telemetry:** The only signal sent to Culiplan beyond normal API traffic is a single boolean (`homeAssistantLinked: true`) set when OAuth completes. No install metrics, no usage statistics, no version reporting.
- **HA event payloads:** Socket.IO events carry entity IDs only — no recipe titles, no ingredient lists, no personal content — the integration refetches details via OAuth-scoped REST calls.
- **BYOK keys:** Never transmitted to or stored on Culiplan infrastructure.
- **Full policy:** [culiplan.com/privacy](https://culiplan.com/privacy)

---

## Automations

Example: notify when dinner is in 30 minutes.

```yaml
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.culiplan_meal_plan
    offset: "-0:30:00"
action:
  - service: notify.mobile_app_my_phone
    data:
      message: "Dinner starting in 30 minutes: {{ trigger.calendar_event.summary }}"
```

---

## What works (v0.3.1)

Full feature surface as of 2026-06-05:

- **OAuth 2.1 PKCE account linking** — first-install dialog is skipped via auto-imported credential.
- **Reconfigure flow** with same-account guard (wrong-account aborts cleanly).
- **Calendar entity** — one entity (`calendar.culiplan_meal_plan`) with N meal-plan events.
- **Shopping list todo entity** — two-way sync; `HassListAddItem` standard intent works ("add milk to my shopping list").
- **Sensors** — meals planned this week, shopping items count, expiring pantry items, planned kWh today (premium, opt-in).
- **Binary sensors** — pantry has expiring items, dinner party active (opt-in).
- **Lovelace card pack** — Kitchen Dashboard, Pantry Tracker, Cooking Mode + a drop-in welcome card.
- **Cooking Mode** — active-session reader with step list + timer mirroring; `culiplan.advance_cooking_step`, `pause_cooking_session`, `set_servings`, etc.
- **Sidebar panel** — vanilla web component, embed-mode (hides duplicate Culiplan chrome inside the iframe), HA theme tokens bridged via postMessage (dark mode follows).
- **AI services** — `culiplan.suggest_meal`, `culiplan.fill_shopping_list`, `culiplan.generate_blueprint` with three modes:
  - Cloud (Culiplan Premium)
  - BYOK (your own OpenAI / Anthropic / Google key, stored in HA only)
  - Local (Ollama / LM Studio on your LAN)
- **`llm.API` registration** — six Culiplan tools (`get_meal_plan`, `suggest_meal`, `add_to_shopping_list`, `find_recipes_by_ingredients`, `get_recipe`, `get_pantry_items`) are available to **any** HA-configured Conversation Agent (OpenAI / Anthropic / Google / Ollama / Voice Preview) — no BYOK needed if you already have an HA LLM agent.
- **Mealie import wizard** — one-click migration during config flow (24-hour rollback).
- **Smart pantry recommendations** — premium-gated, surfaced via Repairs upsell when called.
- **Assist voice intents** — `what's for dinner tonight`, `what's in my pantry`, `add to shopping list`, cooking-mode controls (en / nl / de / fr / es).
- **Premium gating** — gracefully surfaces Repairs upsell flows on 403; users without Premium see a clean "upgrade" link instead of a stack trace.
- **Live push updates** via Socket.IO (no polling).
- **MCP server** — Culiplan tools also reachable via `mcp.culiplan.com` for HA's built-in MCP client. See [docs/integrations/home-assistant-paths.md](https://github.com/culiplan/Flavorplan/blob/master/docs/integrations/home-assistant-paths.md).

## Known limitations

- **HA Core catalog listing** — Phase 4. We're aiming for HACS first; HA Core submission depends on the upstream `pytest_homeassistant_custom_component` test-fixture fix (the only Silver rule still `todo` in `quality_scale.yaml`).
- **Brands logo in HA integration picker** — assets are prepared; the PR to `home-assistant/brands` ships at the same time as HACS submission.

---

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

This integration is not affiliated with the Home Assistant project.
