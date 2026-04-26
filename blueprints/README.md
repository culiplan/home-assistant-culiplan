# Culiplan Blueprint Library

Free Home Assistant automation blueprints for households using the
[Culiplan](https://culiplan.com) meal planning integration.

Each blueprint is a polished, production-ready automation skeleton.
Import one in 30 seconds, configure a handful of entity pickers, and your
kitchen runs itself.

**Requirements for all blueprints**

- Home Assistant 2024.6 or later
- Culiplan integration installed and connected via OAuth 2.1
  ([setup guide](https://culiplan.com/home-assistant))

---

## Blueprints

### 1. Pre-heat on Presence

**File:** `automation/culiplan/preheat-on-presence.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpreheat-on-presence.yaml)

Automatically starts your oven or induction hob a configurable number of
minutes before tonight's recipe start time — but only when someone is
actually home. The automation reads the next event from
`calendar.culiplan_meal_plan`, checks your presence sensor, and fires a
`climate.set_temperature` or `switch.turn_on` call exactly when pre-heating
needs to begin. No more cold ovens; no energy wasted when the house is empty.

**Configurable inputs:** pre-heat lead time (1–60 min), check window
start/end times, presence sensor, appliance entity (climate or switch),
target temperature, optional push notification.

**Marketing copy (for flavorplan.com/home-assistant/blueprints):**
Stop waiting for the oven. Culiplan knows when dinner starts — this
blueprint bridges that knowledge to your smart appliance. Set your pre-heat
lead time once, point it at any climate or smart-plug entity, and your
kitchen is warm before you even start chopping. Presence-aware: the
automation stands down automatically when the house is empty. Works with
any smart oven, hob, or plug that HA can control.

---

### 2. Pantry Zero → Shopping List

**File:** `automation/culiplan/pantry-zero-shopping.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpantry-zero-shopping.yaml)

The moment a pantry item hits zero stock, Culiplan fires a
`pantry.item.depleted` event. This blueprint catches that event, appends the
depleted item to your active `todo.culiplan_shopping_list`, and notifies the
household — so nothing falls through the cracks between the pantry and the
supermarket run. Supports an optional presence check to silence notifications
when the house is empty, and fan-out to multiple `notify.*` services
(phones, speakers, wall tablets) in a single rule.

**Configurable inputs:** shopping list entity, one or more notification
services, optional presence gate.

**Marketing copy (for flavorplan.com/home-assistant/blueprints):**
Your pantry talks directly to your shopping list. When Culiplan detects that
an ingredient has run out, this blueprint adds it to the HA shopping list and
pings every device in the household instantly — no manual logging, no
forgotten items. It fans out to as many notification targets as you like:
phones, kitchen speakers, wall displays. The loop from pantry shelf to
shopping cart closes itself.

---

### 3. Sunday Plan Push

**File:** `automation/culiplan/sunday-plan-push.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpantry-zero-shopping.yaml)

Every Sunday at 18:00 (configurable), this blueprint pulls the upcoming
meal plan from `calendar.culiplan_meal_plan`, combines it with live counts
from the shopping list and pantry expiry sensors, and pushes a formatted
weekly summary to your household tablet or any `notify.*` target. Works
beautifully as a wall-panel notification, a companion-app lock-screen card,
or a spoken kitchen announcement. Change the trigger weekday to Friday for a
"weekend ahead" preview instead.

**Configurable inputs:** trigger time, day of week, notification service,
message title, optional shopping item count, optional pantry expiry warning.

**Marketing copy (for flavorplan.com/home-assistant/blueprints):**
Every Sunday evening your household tablet shows next week's full meal plan
— without anyone lifting a finger. Shopping list count, pantry expiry
warnings, and a deep-link back into Culiplan are all included in a single
push. Set it up once; stay aligned as a household every week without a
Sunday-night group-chat debate about what's for dinner.

---

### 4. Energy-Aware Meal Swap

**File:** `automation/culiplan/energy-aware-swap.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fenergy-aware-swap.yaml)

When spot electricity prices spike above your threshold, this blueprint
suggests an energy-light alternative dinner before you start pre-heating the
oven. Works with any HA energy-price sensor: Tibber, Nordpool, Amber
Electric, ENTSO-E, or any custom `sensor.*` with a numeric kWh price. The
notification deep-links directly into your Culiplan recipe library filtered
by the energy-light tag. Enable the optional in-app swap event to let the
Culiplan AI dispatcher propose a specific recipe (requires Culiplan premium).

**Configurable inputs:** electricity price sensor, threshold value, daily
check time, notification service, optional in-app swap trigger, recipe tag
for alternatives.

**Marketing copy (for flavorplan.com/home-assistant/blueprints):**
Cook smarter, not just cheaper. This blueprint watches your spot electricity
price and nudges the household toward an energy-light dinner on peak-price
days — before anyone fires up the oven. Compatible with every major European
energy price integration. Optional one-tap access to your Culiplan
"energy-light" recipe tag makes the swap frictionless. Your meal plan
adapts to the grid, not the other way around.

---

### 5. Late-Event Quick-Cook Swap

**File:** `automation/culiplan/late-event-quick-cook.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Flate-event-quick-cook.yaml)

When the family calendar shows a late-running event tonight, this blueprint
alerts the household before anyone commits to a 90-minute lasagne. At your
chosen check time (default 15:00), it scans a shared `calendar.*` entity for
any event ending after your "late threshold" time (default 18:30) and, when
one is found, notifies the household with a deep-link to the Culiplan recipe
library filtered by the "quick-cook" tag. Enable the optional in-app swap
trigger to let the Culiplan AI dispatcher automatically propose a substitute
(requires Culiplan premium).

**Configurable inputs:** family calendar entity, late threshold time, daily
check time, quick-cook recipe tag, notification service, optional in-app
swap trigger.

**Marketing copy (for flavorplan.com/home-assistant/blueprints):**
No more arriving home at 19:30 to find someone halfway through a slow roast.
This blueprint checks your shared calendar every afternoon and fires a
household notification the moment it spots a late night coming — before prep
has started. One tap opens your Culiplan "quick-cook" recipe library filtered
and ready to pick from. Works with any HA-connected shared calendar: Google,
iCloud, CalDAV, Nextcloud, and more.

---

### 6. Pantry Barcode Decrement

**File:** `automation/culiplan/pantry-barcode-decrement.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpantry-barcode-decrement.yaml)

When a barcode scanner connected to Home Assistant fires a scan event, this
blueprint calls `culiplan.pantry_decrement` to remove one unit of the matched
item from your Culiplan pantry. Works with any HA-compatible barcode scanner:
USB HID readers, Bluetooth scanners, the HA companion app's barcode scanner
action, or any integration that fires an event with a barcode payload.

**Configurable inputs:** barcode event entity, decrement quantity.

**Marketing copy (for culiplan.com/home-assistant/blueprints):**
Scan an item out of your pantry the same way a supermarket scans it in.
Connect any barcode reader to Home Assistant, point this blueprint at it, and
Culiplan's pantry ledger stays accurate in real time — no manual counting, no
app tap required. Works with USB, Bluetooth, and phone-based scanners.

---

### 7. Daily Pantry Expiry Reminder

**File:** `automation/culiplan/pantry-expiry-notify.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpantry-expiry-notify.yaml)

Every morning at a configurable time, this blueprint checks whether any pantry
items are expiring within the next 48 hours and sends a push notification
prompting the household to act. Pairs perfectly with the Sunday Plan Push
blueprint to give both a weekly overview and daily last-chance reminders for
items about to turn.

**Configurable inputs:** reminder time, notification service, title, message template.

**Marketing copy (for culiplan.com/home-assistant/blueprints):**
Stop throwing money away. This blueprint sends a daily nudge when something in
your pantry is about to expire — before it ends up in the bin. Takes 30 seconds
to set up and runs itself every morning. Your household bins less, wastes less,
and plans better.

---

### 8. Presence-Based Serving Scale

**File:** `automation/culiplan/presence-scale-servings.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fpresence-scale-servings.yaml)

When the number of household members home changes, this blueprint calls
`culiplan.scale_tonight_servings` with the live count so Culiplan can
automatically adjust tonight's recipe quantities. A family of four with one
person away on a work trip gets a three-portion recipe automatically; a dinner
party that fills up gets scaled up without anyone touching the app.

**Configurable inputs:** presence sensor (person group or count sensor).

**Marketing copy (for culiplan.com/home-assistant/blueprints):**
The right number of portions, automatically. Link your HA household presence
sensors to Culiplan and tonight's recipe scales itself in real time as people
arrive or leave. No more guessing at quantities, no more leftovers by accident.
Pairs with the Dinner Party Pre-Arrival blueprint for full event-night automation.

---

### 9. Dinner Party Pre-Arrival Ambiance

**File:** `automation/culiplan/dinner-party-pre-arrival.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fdinner-party-pre-arrival.yaml)

Fifteen minutes before your Culiplan dinner party starts, this blueprint dims
the lights to a warm ambiance level and starts your dinner playlist — so the
mood is set before the first guest rings the doorbell. Reads the `start_at`
attribute from `binary_sensor.culiplan_dinner_party_active` and fires at
exactly the right moment.

**Configurable inputs:** light target, brightness percentage, colour temperature (K),
media player entity, playlist URI, minutes-before-start lead time.

**Marketing copy (for culiplan.com/home-assistant/blueprints):**
Every dinner party deserves a proper entrance. Culiplan knows when your guests
arrive — this blueprint makes sure your lights and music agree. Candlelight dim
and dinner playlist start automatically, timed to the minute. Works with any
HA-compatible light and media player: Philips Hue, LIFX, Sonos, Cast, and more.

---

### 10. Smart Oven & Induction Preheat

**File:** `automation/culiplan/smart-oven-preheat.yaml`

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fculiplan%2Fhome-assistant-culiplan%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fculiplan%2Fsmart-oven-preheat.yaml)

The recipe-aware evolution of blueprint #1. Where "Pre-heat on Presence" fires
a single appliance at a fixed temperature, this blueprint reads the recipe's
`requiredTemperature` and `cookingMethod` attributes directly from the
`calendar.culiplan_meal_plan` event and orchestrates your oven **and**
induction hob as a coordinated pair.

When tonight's recipe is tagged `oven` the oven fires at the recipe's specified
temperature (or your configured default). When tagged `induction` the hob fires
instead. When tagged `oven,induction` — or when no tag is present — both
appliances fire in the same run. A presence gate, a configurable preheat
window, and an optional push notification round out the feature set.

Per-step appliance routing (e.g. induction for sautéing at step 1, oven for
finishing at step 3) is forward-compatible: when Culiplan exposes
`step_appliances` on the calendar event the blueprint will route accordingly,
and the notification message will flag this to the user.

**Configurable inputs:** preheat lead time (1–60 min, default 15), check window
start/end, oven entity (climate or switch), default oven temperature (°C),
induction entity (optional, climate or switch), default induction temperature,
"fire induction without cookingMethod" toggle, presence sensor (optional),
notification service (optional), notification title.

**Recipe metadata used:** `requiredTemperature` (integer, °C) and
`cookingMethod` (string: `oven`, `induction`, or `oven,induction`) from
`calendar.culiplan_meal_plan` event attributes. Falls back gracefully when
absent.

**Marketing copy (for culiplan.com/home-assistant/blueprints):**
Your kitchen heats up at exactly the right temperature, automatically. This
blueprint reads tonight's recipe — including the required cooking temperature —
and tells your oven and induction hob what to do, when to do it, and only when
someone is home. No more cold ovens, no more guessing at temperatures, no more
wasted energy while the house is empty. Set it up once and let Culiplan and
Home Assistant run the kitchen together.

---

## Installation

### Option A: One-click import (recommended)

Click the **Import blueprint** badge next to any blueprint above. Home
Assistant will open the blueprint import dialog with the file pre-loaded.
Review the YAML, click **Import**, then open **Settings → Automations →
Create automation → Use a blueprint** to configure and activate it.

### Option B: Manual install

1. Copy the `.yaml` file to your HA config folder:
   `<config>/blueprints/automation/culiplan/<name>.yaml`
2. Reload blueprints: **Developer Tools → YAML → Reload → Blueprint**
3. Create a new automation: **Settings → Automations → Create automation →
   Use a blueprint**

---

## Entities provided by the Culiplan integration

These entities are registered automatically when you connect Culiplan to
Home Assistant via OAuth 2.1. All blueprints reference them:

| Entity | Type | Description |
|---|---|---|
| `calendar.culiplan_meal_plan` | `calendar` | Weekly meal plan as calendar events |
| `todo.culiplan_shopping_list` | `todo` | Active shopping list, two-way sync |
| `sensor.culiplan_meals_planned_this_week` | `sensor` | Count of meals planned this week |
| `sensor.culiplan_shopping_items` | `sensor` | Count of active shopping list items |
| `sensor.culiplan_pantry_expiring_soon` | `sensor` | Count of pantry items expiring within 7 days |

---

## Events fired by the Culiplan integration

The integration publishes events on the HA event bus. Blueprints and custom
automations can subscribe to these:

| Event type | Fired when |
|---|---|
| `culiplan_event` with `event_type: meal_plan.updated` | Meal plan is changed |
| `culiplan_event` with `event_type: shopping_list.item.added` | Item added to shopping list |
| `culiplan_event` with `event_type: shopping_list.item.completed` | Item checked off |
| `culiplan_event` with `event_type: pantry.item.depleted` | Pantry item reaches zero stock |
| `culiplan_event` with `event_type: pantry.item.updated` | Pantry item quantity updated |
| `culiplan_event` with `event_type: dinner_party.updated` | Dinner party details change |

---

## Changelog

### v1.1.0 (2026-04-25)

- Added blueprint #10: Smart Oven & Induction Preheat — recipe-aware
  multi-appliance choreography with `requiredTemperature` + `cookingMethod`
  attribute reading, per-step routing forward-compatibility, and presence gate
- Documented blueprints #6–#9 (Phase 2 pantry/dinner-party blueprints that
  shipped alongside the cooking-mode card): pantry-barcode-decrement,
  pantry-expiry-notify, presence-scale-servings, dinner-party-pre-arrival

### v1.0.0 (2026-04-25)

- Initial release of Blueprint Library v1
- Five free skeleton blueprints: preheat-on-presence, pantry-zero-shopping,
  sunday-plan-push, energy-aware-swap, late-event-quick-cook
- Full HA 2024.6+ compatibility
- Validated against HA blueprint schema

---

## Contributing

Found a bug or have an improvement? Open an issue or pull request at
[github.com/culiplan/home-assistant-culiplan](https://github.com/culiplan/home-assistant-culiplan).

## License

MIT — see [LICENSE](../LICENSE) in the repository root.
