/**
 * Culiplan Kitchen Dashboard Card — v1.0.0
 *
 * Pre-built distribution bundle for Home Assistant Lovelace.
 * Source: lovelace/cards/kitchen-dashboard.ts
 *
 * Build: esbuild kitchen-dashboard.ts --bundle --format=esm --outfile=dist/kitchen-dashboard.js
 * (No build infrastructure required for HA — this file is loaded directly as a Lovelace resource.)
 *
 * Loaded automatically by custom_components/culiplan/__init__.py as a Lovelace JS resource.
 * Registered element: flavorplan-kitchen-dashboard
 */

// Inline LitElement dependency via CDN import (avoids bundling 40 kB into the file)
// HA 2023.4+ supports native ES modules; this import resolves in browser context only.
import { LitElement, html, css } from "https://unpkg.com/lit@2/index.js?module";

const MEAL_TYPE_LABELS = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

const ICON_CHEF_HAT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>`;
const ICON_CLOCK = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
const ICON_USERS = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
const ICON_SHOPPING = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>`;
const ICON_CALENDAR = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;
const ICON_ARROW_RIGHT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;

class FlavorplanKitchenDashboard extends LitElement {
  static get properties() {
    return { _config: { type: Object }, _hass: { type: Object } };
  }

  setConfig(config) {
    this._config = {
      entity: "calendar.culiplan_meal_plan",
      shopping_entity: "todo.culiplan_shopping_list",
      title: "What's for Dinner?",
      show_shopping: true,
      max_meals: 3,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.requestUpdate();
  }

  getCardSize() { return 4; }

  _getMeals() {
    if (!this._hass || !this._config.entity) return [];
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) return [];
    const raw = stateObj.attributes?.today_meals;
    if (!raw) return [];
    try {
      const meals = typeof raw === "string" ? JSON.parse(raw) : raw;
      return meals.slice(0, this._config.max_meals ?? 3);
    } catch { return []; }
  }

  _getShoppingCount() {
    if (!this._hass || !this._config.shopping_entity) return 0;
    const stateObj = this._hass.states[this._config.shopping_entity];
    return stateObj?.attributes?.items_count ?? 0;
  }

  _getTotalTime(meal) {
    const total = (meal.prepTimeMins ?? 0) + (meal.cookTimeMins ?? 0);
    if (total === 0) return "";
    return total < 60 ? `${total} min` : `${Math.floor(total / 60)}h ${total % 60}m`;
  }

  _openShoppingList() {
    const entity = this._config.shopping_entity;
    if (!entity || !this._hass) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      detail: { entityId: entity },
      bubbles: true,
      composed: true,
    }));
  }

  _openMealDetail() {
    if (!this._hass) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      detail: { entityId: this._config.entity },
      bubbles: true,
      composed: true,
    }));
  }

  _renderMealCard(meal) {
    const time = this._getTotalTime(meal);
    const mealLabel = MEAL_TYPE_LABELS[meal.mealType ?? ""] ?? "";
    const hasImage = !!meal.imageUrl;
    const cdnBase = "https://cdn.culiplan.com";
    const imgSrc = meal.imageUrl?.startsWith("http") ? meal.imageUrl : `${cdnBase}/${meal.imageUrl}`;

    return html`
      <article class="meal-card"
        @click=${() => this._openMealDetail()}
        role="button" tabindex="0"
        @keydown=${(e) => e.key === "Enter" && this._openMealDetail()}
        aria-label="View details for ${meal.title}">
        <div class="meal-image-wrapper">
          ${hasImage
            ? html`<img class="meal-image" src="${imgSrc}" alt="${meal.title}" loading="lazy"/>`
            : html`<div class="meal-image-placeholder"><span class="placeholder-icon">${ICON_CHEF_HAT}</span></div>`}
          ${mealLabel ? html`<span class="meal-type-badge">${mealLabel}</span>` : ""}
        </div>
        <div class="meal-info">
          <h3 class="meal-title">${meal.title}</h3>
          <div class="meal-meta">
            ${meal.servings ? html`<span class="meta-item"><span class="meta-icon">${ICON_USERS}</span>${meal.servings}</span>` : ""}
            ${time ? html`<span class="meta-item"><span class="meta-icon">${ICON_CLOCK}</span>${time}</span>` : ""}
          </div>
        </div>
        <div class="meal-arrow" aria-hidden="true">${ICON_ARROW_RIGHT}</div>
      </article>`;
  }

  _renderEmptyState() {
    return html`
      <div class="empty-state">
        <div class="empty-icon">${ICON_CALENDAR}</div>
        <p class="empty-title">No meals planned today</p>
        <p class="empty-subtitle">Open Flavorplan to add meals to your plan.</p>
      </div>`;
  }

  _renderShoppingShortcut() {
    if (!this._config.show_shopping) return "";
    const count = this._getShoppingCount();
    return html`
      <button class="shopping-shortcut" @click=${this._openShoppingList}
        aria-label="Open shopping list${count > 0 ? ` — ${count} items` : ""}">
        <span class="shopping-icon">${ICON_SHOPPING}</span>
        <span class="shopping-label">Shopping list</span>
        ${count > 0 ? html`<span class="shopping-badge">${count}</span>` : ""}
        <span class="shopping-arrow">${ICON_ARROW_RIGHT}</span>
      </button>`;
  }

  render() {
    const meals = this._getMeals();
    const title = this._config?.title ?? "What's for Dinner?";
    if (!this._hass) {
      return html`<ha-card><div class="card-content loading">
        <div class="skeleton-header"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
      </div></ha-card>`;
    }
    return html`
      <ha-card>
        <div class="card-header">
          <span class="header-icon">${ICON_CHEF_HAT}</span>
          <h2 class="header-title">${title}</h2>
        </div>
        <div class="card-content">
          <div class="meals-section">
            ${meals.length > 0 ? meals.map((m) => this._renderMealCard(m)) : this._renderEmptyState()}
          </div>
          ${this._renderShoppingShortcut()}
        </div>
      </ha-card>`;
  }

  static get styles() {
    return css`
      :host { display: block; font-family: var(--culiplan-font-body, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif); }
      ha-card { overflow: hidden; background: var(--culiplan-surface, var(--card-background-color, #fff)); box-shadow: var(--culiplan-shadow-card, 0 2px 12px 0 rgba(242,103,68,0.08)); border-radius: var(--culiplan-radius-xl, 12px); border: 1px solid var(--culiplan-border, #e5e7eb); }
      .card-header { display: flex; align-items: center; gap: 8px; padding: 16px 16px 8px; background: var(--culiplan-gradient-hero, linear-gradient(135deg, #f26744 0%, #f58566 50%, #ffb89a 100%)); color: #fff; }
      .header-icon { width: 24px; height: 24px; flex-shrink: 0; display: flex; align-items: center; }
      .header-icon svg { width: 100%; height: 100%; }
      .header-title { margin: 0; font-size: var(--culiplan-text-lg, 18px); font-weight: var(--culiplan-font-semibold, 600); line-height: 1.25; color: inherit; }
      .card-content { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
      .meals-section { display: flex; flex-direction: column; gap: 8px; }
      .meal-card { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: var(--culiplan-surface, #fff); border: 1px solid var(--culiplan-border, #e5e7eb); border-radius: var(--culiplan-radius-lg, 8px); cursor: pointer; transition: all 150ms cubic-bezier(0,0,0.2,1); }
      .meal-card:hover { background: var(--culiplan-surface-hover, #f9fafb); border-color: var(--culiplan-primary, #f26744); box-shadow: 0 1px 3px 0 rgba(0,0,0,0.06); transform: translateY(-1px); }
      .meal-card:focus-visible { outline: 2px solid var(--culiplan-primary, #f26744); outline-offset: 2px; }
      .meal-image-wrapper { position: relative; flex-shrink: 0; width: 64px; height: 64px; border-radius: 6px; overflow: hidden; background: var(--culiplan-muted, #f3f4f6); }
      .meal-image { width: 100%; height: 100%; object-fit: cover; }
      .meal-image-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, #fffbf7 0%, #faf8f5 100%); }
      .placeholder-icon { width: 28px; height: 28px; color: var(--culiplan-primary, #f26744); opacity: 0.6; display: flex; align-items: center; }
      .placeholder-icon svg { width: 100%; height: 100%; }
      .meal-type-badge { position: absolute; bottom: 4px; left: 4px; font-size: 12px; font-weight: 500; color: #fff; background: rgba(0,0,0,0.55); padding: 1px 5px; border-radius: 9999px; line-height: 1.4; white-space: nowrap; }
      .meal-info { flex: 1; min-width: 0; }
      .meal-title { margin: 0 0 4px; font-size: var(--culiplan-text-sm, 14px); font-weight: 600; color: var(--culiplan-text-primary, #1c1917); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.25; }
      .meal-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
      .meta-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--culiplan-text-secondary, #6b7280); }
      .meta-icon { width: 14px; height: 14px; display: flex; align-items: center; flex-shrink: 0; }
      .meta-icon svg { width: 100%; height: 100%; }
      .meal-arrow { width: 16px; height: 16px; color: var(--culiplan-text-muted, #9ca3af); flex-shrink: 0; display: flex; align-items: center; }
      .meal-arrow svg { width: 100%; height: 100%; }
      .empty-state { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 32px 16px; gap: 8px; }
      .empty-icon { width: 48px; height: 48px; color: var(--culiplan-primary, #f26744); opacity: 0.4; display: flex; align-items: center; }
      .empty-icon svg { width: 100%; height: 100%; }
      .empty-title { margin: 0; font-size: 14px; font-weight: 600; color: var(--culiplan-text-primary, #1c1917); }
      .empty-subtitle { margin: 0; font-size: 12px; color: var(--culiplan-text-secondary, #6b7280); }
      .shopping-shortcut { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px; background: var(--culiplan-secondary, #16A34A); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-family: inherit; font-size: 14px; font-weight: 600; transition: all 150ms cubic-bezier(0,0,0.2,1); text-align: left; }
      .shopping-shortcut:hover { background: var(--culiplan-secondary-dark, #15803d); transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.07); }
      .shopping-shortcut:focus-visible { outline: 2px solid var(--culiplan-secondary, #16A34A); outline-offset: 2px; }
      .shopping-icon { width: 18px; height: 18px; flex-shrink: 0; display: flex; align-items: center; }
      .shopping-icon svg { width: 100%; height: 100%; }
      .shopping-label { flex: 1; }
      .shopping-badge { background: rgba(255,255,255,0.25); font-size: 12px; font-weight: 700; padding: 1px 7px; border-radius: 9999px; min-width: 20px; text-align: center; }
      .shopping-arrow { width: 16px; height: 16px; flex-shrink: 0; display: flex; align-items: center; }
      .shopping-arrow svg { width: 100%; height: 100%; }
      .loading { gap: 8px; }
      @keyframes skeleton-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      .skeleton-header, .skeleton-card { background: var(--culiplan-muted, #f3f4f6); border-radius: 6px; animation: skeleton-pulse 1.8s ease-in-out infinite; }
      .skeleton-header { height: 28px; width: 50%; }
      .skeleton-card { height: 80px; }
    `;
  }
}

customElements.define("flavorplan-kitchen-dashboard", FlavorplanKitchenDashboard);

window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "flavorplan-kitchen-dashboard",
  name: "Flavorplan Kitchen Dashboard",
  description: "Today's meal plan with shopping list shortcut. Part of the Culiplan integration card pack.",
  preview: true,
  documentationURL: "https://github.com/culiplan/home-assistant-culiplan/tree/main/lovelace",
});
