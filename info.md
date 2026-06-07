# Culiplan for Home Assistant

Bring your [Culiplan](https://culiplan.com) meal-planning account into Home Assistant.

## What you get

- **Calendar** — one event per planned meal (`calendar.culiplan_meal_plan`).
- **Shopping list** — `todo.culiplan_shopping_list` synced both ways.
- **Sensors** — meals today, unchecked shopping items, pantry items expiring within 3 days, planned cooking energy (kWh).
- **Voice** — Assist intents like *"Add bread to the shopping list"* or *"What's for dinner tonight?"*.
- **Three custom Lovelace cards** — Kitchen Dashboard, Pantry Tracker, Cooking Mode — installed automatically.
- **Four ready-made dashboards** — kitchen tablet, phone, Voice PE companion, energy.
- **Self-updates** — auto-updates default-on; manual *Install* button via `update.culiplan_update`.

## Setup

1. After install, go to **Settings → Devices & Services → Add Integration → Culiplan**.
2. A browser window opens — log in with your Culiplan account and approve the requested scopes.
3. Choose your AI mode (Cloud is the default and easiest).
4. Entities appear within a few seconds.

Full setup, AI modes, and dashboard documentation: see the [README](https://github.com/culiplan/home-assistant-culiplan/blob/main/README.md).
