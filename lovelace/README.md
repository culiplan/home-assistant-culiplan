# Culiplan Lovelace Card Pack — v1.0.0

Custom Lovelace cards that bring Culiplan's mobile/tablet visual language to Home Assistant.
Cards are distributed as part of the Culiplan HACS integration and load automatically when
the integration is installed.

---

## Cards included in v1

| Card element | Description | Source |
|---|---|---|
| `flavorplan-kitchen-dashboard` | Today's meal plan with recipe image, servings, time and a shopping-list shortcut | `cards/dist/kitchen-dashboard.js` |
| `flavorplan-pantry-tracker` | Pantry tile grid with expiry warnings (red < 48 h, amber < 7 d), low-stock indicator, filter chips, and inline actions | `cards/dist/pantry-tracker.js` |

### v1 Known Limitations

**Cooking Mode card (`flavorplan-cooking-mode`) is NOT included in v1.**
It depends on the cooking session resource (`GET /api/cooking-sessions/:id`) which is scheduled
for Phase 3 backend work (task-1396). The three pre-configured dashboard YAMLs contain a
placeholder `markdown` card with instructions for where to add it once Phase 3 ships.

---

## Design Tokens

All visual values (colours, spacing, type ramp, radius, shadows, gradients, motion) live in
`lovelace/tokens.css` on `:root` scope, meaning HA users can override any token via
[card-mod](https://github.com/thomasloven/lovelace-card-mod) without touching Shadow DOM
internals.

See [tokens.README.md](tokens.README.md) for the full mapping table from mobile and web sources.

**Quick override example:**
```yaml
card_mod:
  style: |
    :root {
      --culiplan-primary: #e05a30;
      --culiplan-radius-xl: 20px;
    }
```

---

## Installation

### Via HACS (recommended — automatic)

The cards load automatically when the Culiplan integration is installed via HACS.
The integration's `__init__.py` registers the JS resources and CSS tokens file as Lovelace
resources on first setup. No manual steps required.

### Manual resource registration

If you installed the integration manually (not via HACS), add the following to your
`configuration.yaml` under `lovelace:resources:` (or use the HA Dashboard Resources UI):

```yaml
lovelace:
  resources:
    - url: /local/culiplan/lovelace/tokens.css
      type: css
    - url: /local/culiplan/lovelace/cards/dist/kitchen-dashboard.js
      type: module
    - url: /local/culiplan/lovelace/cards/dist/pantry-tracker.js
      type: module
```

Copy the `lovelace/` directory to `config/www/culiplan/lovelace/` in your HA config directory.

---

## Pre-configured Dashboards

Four dashboard YAML presets ship in `lovelace/dashboards/`. Import any of them via
**Home Assistant → Dashboards → Add Dashboard → Take Control**, then paste the YAML
into the RAW configuration editor.

| File | Optimised for | Description |
|---|---|---|
| `kitchen-tablet.yaml` | 10" landscape tablet | Three-column layout: Kitchen Dashboard, Meal Calendar, Pantry Tracker |
| `phone-quick-view.yaml` | Mobile phone (360–430 px) | Single-column scrollable with today's meals + pantry summary |
| `voice-pe-companion.yaml` | Wall display / Voice PE companion | Two-column always-on layout with prominent voice shortcut |
| `energy-meal-cost.yaml` | Any display | Planned meal energy gauge + 7-day history + per-meal breakdown. Requires `sensor.culiplan_planned_kwh_today` (Phase 3). |

### Energy & Meal Cost Dashboard (`energy-meal-cost.yaml`)

Added in Phase 3 (task-1399). Shows planned cooking energy consumption alongside your HA
Energy dashboard.

**Sensor required:** `sensor.culiplan_planned_kwh_today`
- Unit: `kWh`
- State class: `total`
- Device class: `energy`
- Updated: whenever your meal plan changes (via WebSocket push), and on coordinator refetch

**To add cooking cost to the HA Energy dashboard:**
1. Go to **Settings → Energy**
2. Under **Individual devices**, click **Add device**
3. Select **sensor.culiplan_planned_kwh_today**

HA multiplies the sensor value by your configured energy tariff automatically.

---

## Screenshots

### Kitchen Dashboard Card

The Kitchen Dashboard card shows today's planned meals with:
- Recipe thumbnail (or branded placeholder if no image)
- Meal title, servings count, total cook time
- Meal-type badge (Breakfast / Lunch / Dinner / Snack)
- One-tap shopping list shortcut button (green, shows item count badge)

**Screenshot baseline:** `screenshots/kitchen-dashboard-light.png` (light mode)
**Screenshot baseline:** `screenshots/kitchen-dashboard-dark.png` (dark mode)

> Screenshots are captured using the smoke test procedure below. The `screenshots/`
> directory ships with the repo to provide PR reviewers with a visual regression baseline.

### Pantry Tracker Card

The Pantry Tracker card shows:
- Header with green gradient and expiry/low-stock count badges
- Three filter chips: All / Expiring / Low stock
- Tile grid (auto-fill, minimum 140 px wide) with:
  - Item name and quantity
  - Red badge for items expiring within 48 h (or already expired)
  - Amber badge for items expiring within 7 days
  - Grey "Low" badge for items below stock threshold
- Tap a tile to reveal an inline action sheet: "Use one", "Add to shopping", close

**Screenshot baseline:** `screenshots/pantry-tracker-light.png` (light mode, All filter)
**Screenshot baseline:** `screenshots/pantry-tracker-expiring.png` (Expiring filter active)

### Kitchen Tablet Dashboard

Three-column layout for landscape tablets showing all cards together.

**Screenshot baseline:** `screenshots/kitchen-tablet-dashboard.png`

### Phone Quick View

Single-column scrollable view optimised for phone width.

**Screenshot baseline:** `screenshots/phone-quick-view.png`

### Voice PE Companion

Two-column layout with Voice PE Assist button prominent at top-left.

**Screenshot baseline:** `screenshots/voice-pe-companion.png`

---

## Smoke Test Plan

A live HA instance is required for full smoke testing. The following procedure validates
each acceptance criterion:

### Prerequisites
- Home Assistant 2024.5 or later
- Culiplan HACS integration installed and OAuth-authenticated
- At least one meal planned for today (to test non-empty state)
- At least 3 pantry items, 1 expiring within 48 h, 1 expiring within 7 d (to test badges)

### Card load test (AC #5 for kitchen-dashboard, auto-load)

1. Install integration via HACS.
2. Open HA → Developer Tools → Template.
3. Enter `{{ states('calendar.culiplan_meal_plan') }}` — should return a state (not `unknown`).
4. Open HA → Settings → Dashboards → Lovelace resources — confirm three Culiplan entries are
   present (`tokens.css`, `kitchen-dashboard.js`, `pantry-tracker.js`).

### Kitchen Dashboard card smoke test

1. Add a new manual card to any dashboard:
   ```yaml
   type: custom:flavorplan-kitchen-dashboard
   entity: calendar.culiplan_meal_plan
   shopping_entity: todo.culiplan_shopping_list
   ```
2. Verify: meal card shows with image/placeholder, title, servings/time meta.
3. Verify: shopping shortcut button shows item count badge if shopping list is non-empty.
4. Tap the shopping shortcut — the more-info dialog for `todo.culiplan_shopping_list` should open.
5. Resize the HA dashboard to phone width (< 400 px) — card remains readable.

### Pantry Tracker card smoke test

1. Add a new manual card:
   ```yaml
   type: custom:flavorplan-pantry-tracker
   entity: sensor.culiplan_expiring_pantry
   shopping_entity: todo.culiplan_shopping_list
   ```
2. Verify: tiles appear with correct expiry badges (red < 48 h, amber < 7 d).
3. Click the "Expiring" filter chip — only expiring items show.
4. Click the "Low stock" filter chip — only low-stock items show.
5. Tap a tile — action sheet appears with "Use one" and "Add to shopping" buttons.
6. Click "Use one" — `culiplan.pantry_decrement` service is called (check Dev Tools → Events).
7. Click "Add to shopping" — item appears in `todo.culiplan_shopping_list`.

### Token override smoke test (card-mod)

1. Install card-mod via HACS.
2. Add to any Culiplan card:
   ```yaml
   card_mod:
     style: |
       :root {
         --culiplan-primary: #0ea5e9;
       }
   ```
3. Verify: kitchen dashboard header gradient and shopping shortcut button both turn blue.
4. Verify: pantry tile hover border and filter chip active state also turn blue.

### Dashboard YAML smoke test

1. Go to HA → Dashboards → Add Dashboard.
2. Name: "Kitchen" / Take Control.
3. Paste `lovelace/dashboards/kitchen-tablet.yaml` into RAW configuration editor.
4. Save — dashboard renders without errors.
5. Repeat for `phone-quick-view.yaml` and `voice-pe-companion.yaml`.

---

## Building from TypeScript source

The `dist/` JS files are pre-built for convenience (no build step needed for HA).
To rebuild from the TypeScript sources:

```bash
# Option A: esbuild (fast, recommended)
npm install -g esbuild
cd lovelace/cards
esbuild kitchen-dashboard.ts --bundle --format=esm --outfile=dist/kitchen-dashboard.js
esbuild pantry-tracker.ts   --bundle --format=esm --outfile=dist/pantry-tracker.js

# Option B: tsc (slower, full type-check)
npx tsc --module esnext --target es2020 --outDir dist kitchen-dashboard.ts
npx tsc --module esnext --target es2020 --outDir dist pantry-tracker.ts
```

Note: The TypeScript source files import Lit from the unpkg CDN to keep the distributed JS
minimal. The CDN import resolves in browser context (HA frontend) but not in a Node.js
build environment without the `--bundle false` flag.

---

## File Map

```
lovelace/
├── tokens.css                    # :root CSS variables (brand + surface + type + radius + shadows + motion)
├── tokens.README.md              # Mapping table from mobile/theme.ts and tailwind.config.ts
├── README.md                     # This file
├── cards/
│   ├── kitchen-dashboard.ts      # LitElement source — flavorplan-kitchen-dashboard
│   ├── pantry-tracker.ts         # LitElement source — flavorplan-pantry-tracker
│   └── dist/
│       ├── kitchen-dashboard.js  # Pre-built distribution bundle (commit to repo)
│       └── pantry-tracker.js     # Pre-built distribution bundle (commit to repo)
├── dashboards/
│   ├── kitchen-tablet.yaml       # 10" landscape tablet layout
│   ├── phone-quick-view.yaml     # Single-column phone layout
│   ├── voice-pe-companion.yaml   # Wall display / Voice PE companion layout
│   └── energy-meal-cost.yaml     # Planned kWh gauge + history (Phase 3, task-1399)
└── screenshots/                  # Visual regression baselines (captured per smoke test)
    ├── kitchen-dashboard-light.png
    ├── kitchen-dashboard-dark.png
    ├── pantry-tracker-light.png
    ├── pantry-tracker-expiring.png
    ├── kitchen-tablet-dashboard.png
    ├── phone-quick-view.png
    └── voice-pe-companion.png
```

---

## Compatibility

| HA version | Status |
|---|---|
| 2024.5 + | Tested |
| 2024.1–2024.4 | Likely works; `assist_satellite` card in voice-pe-companion.yaml requires 2024.5 |
| < 2024.1 | Not supported |

Requires the `culiplan` integration to be installed and authenticated.
Custom cards are web components (LitElement 2.x via CDN) compatible with all modern browsers
supported by HA 2024.5.
