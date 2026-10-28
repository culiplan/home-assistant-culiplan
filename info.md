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
2. A browser window opens. Log in with your Culiplan account (free) and approve access.
3. Done. Entities appear within a few seconds. Cloud AI is the default; change it any time under **Configure**.

If the browser doesn't return to Home Assistant after you approve, set an external URL (Settings → System → Network) or enable My Home Assistant, then try again.

Full setup, AI modes, and dashboard documentation: see the [README](https://github.com/culiplan/home-assistant-culiplan/blob/main/README.md).
