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
