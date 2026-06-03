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

## Known limitations

The following features are **not yet available** and are planned for later HACS releases:

- **AI shopping list fill** (voice command "fill my shopping list for the week") — Phase 3
- **Smart pantry recommendations** — Phase 3
- **Mealie data migration wizard** — Phase 3
- **HA Core catalog listing** — Phase 4 (after HACS community validation)
- **HA cooking-mode service** (culiplan.advance_cooking_step — required for Cooking Mode card step taps) — Phase 3 follow-up (task-1397)

What **does** work:
- OAuth account linking
- Calendar entity (meal plan events, dinner parties)
- Shopping list todo entity (two-way sync)
- Sensors: meals this week, shopping items count, expiring pantry items
- Assist voice commands: add to shopping list, what's for dinner, what's in pantry (en/nl/de/fr/es)
- Lovelace card pack: Kitchen Dashboard, Pantry Tracker, Cooking Mode (Phase 3)
- Cooking Mode card: reads active session, shows step list + timers; graceful idle fallback
- Live push updates via WebSocket (no polling)

---

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

This integration is not affiliated with the Home Assistant project.
