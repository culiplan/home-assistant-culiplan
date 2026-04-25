# Flavorplan for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/culiplan/home-assistant-culiplan.svg)](https://github.com/culiplan/home-assistant-culiplan/releases)
[![License](https://img.shields.io/github/license/culiplan/home-assistant-culiplan.svg)](LICENSE)

Bring your [Flavorplan](https://flavorplan.com) meal planning account into Home Assistant.

> **Beta notice** — This is a pre-release. Calendar, to-do, and sensor entities are live;
> Lovelace cards and advanced AI services ship in a later HACS release.
> Report issues at [GitHub Issues](https://github.com/culiplan/home-assistant-culiplan/issues).

---

## Features (v0.2 — Phase 2 Pantry & Dinner Party Automations)

### Entities

| Entity | Description |
|---|---|
| `calendar.flavorplan_meal_plan` | One event per planned meal; dinner-party events included |
| `todo.flavorplan_shopping_list` | Active shopping list — items can be checked off or added |
| `sensor.flavorplan_meals_today` | Number of meals planned today |
| `sensor.flavorplan_shopping_items` | Count of unchecked shopping list items |
| `sensor.flavorplan_expiring_pantry` | Pantry items expiring within 3 days (count) |
| `binary_sensor.flavorplan_pantry_has_expiring` | **NEW** — On when any pantry item expires within 48 h |
| `binary_sensor.flavorplan_dinner_party_active` | **NEW** — On when a dinner party is planned for today |

### Services (Phase 2)

| Service | Description | Tier |
|---|---|---|
| `flavorplan.pantry_decrement` | Decrement stock for a barcode-scanned item (FEFO) | Free |
| `flavorplan.pantry_expiring_items` | Fetch expiring pantry item IDs into a HA event | Free |
| `flavorplan.scale_tonight_servings` | Scale tonight's recipe portions to present household count | **Premium** |

### Blueprints (Phase 2)

Five automation blueprints ship with the integration (installable via HACS):

| Blueprint | Description | Tier |
|---|---|---|
| `pantry-barcode-decrement` | Decrement pantry on barcode scanner event | Free |
| `pantry-zero-shopping` | Add to shopping list when item depleted | Free |
| `pantry-expiry-notify` | Daily 09:00 reminder if items expire within 48 h | Free |
| `presence-scale-servings` | Scale servings when household presence changes | **Premium** |
| `dinner-party-pre-arrival` | Dim lights + start playlist 15 min before guests arrive | Free |

### Sample automation: Dinner party pre-arrival (task-1380 AC#4)

```yaml
automation:
  alias: "Dinner party — pre-arrival ambiance"
  use_blueprint:
    path: culiplan/dinner-party-pre-arrival.yaml
    input:
      light_target: light.living_room
      light_brightness: 40
      light_kelvin: 2700
      media_player: media_player.living_room_speaker
      playlist_uri: "spotify:playlist:37i9dQZF1DX4PP3DA4J0N8"
      pre_arrival_minutes: 15
```

### Sample automation: Barcode scan decrement (task-1376 AC#3)

```yaml
# Example: USB barcode scanner fires barcode_scanned event with {barcode: "..."}
automation:
  alias: "Pantry — barcode scan decrement"
  use_blueprint:
    path: culiplan/pantry-barcode-decrement.yaml
    input:
      barcode_event: barcode_scanned
      decrement_qty: 1
```

Voice (Assist): say "Add bread to the shopping list" or "What's for dinner tonight?" once the integration is linked.

---

## Installation

### Via HACS (recommended)

1. In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/culiplan/home-assistant-culiplan` as an **Integration**.
3. Search for **Flavorplan** and install.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration → Flavorplan**.

### Manual

Copy `custom_components/culiplan/` into your HA `custom_components/` directory and restart.

---

## Setup

1. Click **Add Integration** and search for **Flavorplan**.
2. A browser window opens — log in with your Flavorplan account and approve the requested scopes.
3. Choose your AI mode (see below).
4. Done — entities appear within a few seconds.

---

## AI Modes

Flavorplan supports three AI execution modes, selectable during setup and changeable later via **Configure**:

### Cloud AI (default)

Flavorplan's servers process AI requests on your behalf.

- **Requires:** Active Flavorplan Premium subscription.
- **Privacy:** Prompt content (your voice commands) travels to `api.culiplan.com`. No data is sold or shared with third parties. See the [privacy policy](https://flavorplan.com/privacy).
- **Cost:** Included in the Premium subscription; no additional AI API costs.

### Bring Your Own Key (BYOK)

Your API key is stored exclusively in Home Assistant's local secrets store. AI calls go directly from your HA install to the AI provider — Flavorplan is not in the network path.

- **Requires:** An account with OpenAI, Anthropic, or Google AI Studio.
- **Privacy:** Your API key and prompt content never reach Flavorplan's servers. Zero-custody — Flavorplan has nothing to lose.
- **Cost:** You pay the AI provider directly at their published token rates. For typical household use this is a few euro cents per month.
- **Free to use** — no Flavorplan Premium required.

### Local AI

Requests go to your own Ollama or LM Studio instance on your local network.

- **Requires:** A running local LLM server (e.g., `ollama serve`).
- **Privacy:** All AI processing stays on your hardware. Nothing leaves your home network.
- **Cost:** Your electricity and hardware costs only.
- **Free to use** — no Flavorplan Premium required.

> **Note on premium features:** The tier line is on capability, not on AI provider. If a feature requires Premium (e.g., Cloud AI recipe generation), it requires Premium with BYOK too — BYOK doesn't unlock premium features for free. It only removes Flavorplan's AI infrastructure costs from the equation for features that are otherwise AI-provider-neutral.

---

## Privacy

Flavorplan is a European company (Belgium) built with privacy-by-design as a first principle.

- **Telemetry:** The only signal sent to Flavorplan beyond normal API traffic is a single boolean (`homeAssistantLinked: true`) set when OAuth completes. No install metrics, no usage statistics, no version reporting.
- **HA event payloads:** Socket.IO events carry entity IDs only — no recipe titles, no ingredient lists, no personal content — the integration refetches details via OAuth-scoped REST calls.
- **BYOK keys:** Never transmitted to or stored on Flavorplan infrastructure.
- **Full policy:** [flavorplan.com/privacy](https://flavorplan.com/privacy)

---

## Automations

Example: notify when dinner is in 30 minutes.

```yaml
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.flavorplan_meal_plan
    offset: "-0:30:00"
action:
  - service: notify.mobile_app_my_phone
    data:
      message: "Dinner starting in 30 minutes: {{ trigger.calendar_event.summary }}"
```

---

## Beta — known limitations

This is a Tier 1 beta. The following features are **not yet available** and are planned for later HACS releases:

- **Lovelace custom cards** (Kitchen Dashboard, Cooking Mode, Pantry Tracker) — Phase 2
- **AI shopping list fill** (voice command "fill my shopping list for the week") — Phase 2
- **Smart pantry recommendations** — Phase 2
- **Cooking Mode step-by-step timers** — Phase 3
- **Mealie data migration wizard** — Phase 2
- **HA Core catalog listing** — Phase 4 (after HACS community validation)

What **does** work in 0.1.0:
- OAuth account linking
- Calendar entity (meal plan events, dinner parties)
- Shopping list todo entity (two-way sync)
- Sensors: meals this week, shopping items count, expiring pantry items
- Assist voice commands: add to shopping list, what's for dinner, what's in pantry (en/nl/de/fr/es)
- Live push updates via WebSocket (no polling)

---

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

This integration is not affiliated with the Home Assistant project.
