/**
 * Culiplan Pantry Tracker Card
 *
 * LitElement-based Lovelace custom card. Shows pantry item tiles with
 * expiry warnings (red < 48 h, amber < 7 d) and a low-stock indicator.
 * Filter chips at the top let users scope the view to All / Expiring /
 * Low stock. Tapping a tile opens an inline action sheet with decrement
 * and add-to-shopping actions.
 *
 * Design tokens: all visual values come from ../tokens.css (loaded globally
 * by __init__.py). Brand source: mobile/theme.ts orange/green palette.
 *
 * Registration: culiplan-pantry-tracker
 */

import { LitElement, html, css } from "lit";

// ── Types ─────────────────────────────────────────────────────────────────

interface PantryItem {
  id: string;
  name: string;
  quantity: number;
  unit?: string;
  expiresAt?: string | null;  // ISO 8601 date string
  lowStockThreshold?: number;
  category?: string;
  imageUrl?: string;
}

type FilterMode = "all" | "expiring" | "low_stock";

interface CardConfig {
  /** HA entity_id of the expiring pantry sensor (default: sensor.culiplan_expiring_pantry) */
  entity?: string;
  /** HA entity_id of the todo entity for add-to-shopping (default: todo.culiplan_shopping_list) */
  shopping_entity?: string;
  /** Override the card title */
  title?: string;
  /** Maximum tiles to show per filter (default: 12) */
  max_items?: number;
}

// ── Constants ─────────────────────────────────────────────────────────────

const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;

const FILTER_LABELS: Record<FilterMode, string> = {
  all: "All",
  expiring: "Expiring",
  low_stock: "Low stock",
};

// ── Icons ─────────────────────────────────────────────────────────────────

const ICON_BOX = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`;
const ICON_MINUS = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
const ICON_PLUS = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
const ICON_CART = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>`;
const ICON_X = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
const ICON_ALERT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
const ICON_TRENDING_DOWN = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>`;

// ── Helper functions ──────────────────────────────────────────────────────

function getExpiryStatus(expiresAt: string | null | undefined): {
  label: string;
  severity: "critical" | "warning" | "ok" | "none";
  msRemaining: number;
} {
  if (!expiresAt) return { label: "", severity: "none", msRemaining: Infinity };
  const now = Date.now();
  const exp = new Date(expiresAt).getTime();
  const ms = exp - now;
  if (ms <= 0) return { label: "Expired", severity: "critical", msRemaining: ms };
  if (ms <= 2 * MS_PER_DAY) {
    const hours = Math.ceil(ms / MS_PER_HOUR);
    return { label: `${hours}h`, severity: "critical", msRemaining: ms };
  }
  if (ms <= 7 * MS_PER_DAY) {
    const days = Math.ceil(ms / MS_PER_DAY);
    return { label: `${days}d`, severity: "warning", msRemaining: ms };
  }
  const days = Math.floor(ms / MS_PER_DAY);
  return { label: `${days}d`, severity: "ok", msRemaining: ms };
}

function isLowStock(item: PantryItem): boolean {
  if (item.quantity <= 0) return true;
  if (item.lowStockThreshold !== undefined && item.quantity <= item.lowStockThreshold) return true;
  return false;
}

// ── Component ─────────────────────────────────────────────────────────────

class CuliplanPantryTracker extends LitElement {
  private _config: CardConfig = {};
  private _hass: any = null;
  private _activeFilter: FilterMode = "all";
  private _selectedItemId: string | null = null;

  static get properties() {
    return {
      _config: { type: Object },
      _hass: { type: Object },
      _activeFilter: { type: String },
      _selectedItemId: { type: String },
    };
  }

  setConfig(config: CardConfig) {
    this._config = {
      entity: "sensor.culiplan_expiring_pantry",
      shopping_entity: "todo.culiplan_shopping_list",
      title: "Pantry",
      max_items: 12,
      ...config,
    };
  }

  set hass(hass: any) {
    this._hass = hass;
    this.requestUpdate();
  }

  getCardSize(): number {
    return 5;
  }

  // ── Data ──────────────────────────────────────────────────────────────────

  private _getAllItems(): PantryItem[] {
    if (!this._hass || !this._config.entity) return [];
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) return [];
    const raw = stateObj.attributes?.items;
    if (!raw) return [];
    try {
      return typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch {
      return [];
    }
  }

  private _getFilteredItems(): PantryItem[] {
    const all = this._getAllItems();
    let filtered: PantryItem[];
    switch (this._activeFilter) {
      case "expiring":
        filtered = all.filter((item) => {
          const { severity } = getExpiryStatus(item.expiresAt);
          return severity === "critical" || severity === "warning";
        });
        break;
      case "low_stock":
        filtered = all.filter(isLowStock);
        break;
      default:
        filtered = all;
    }
    // Sort: critical expiry first, then warning, then low-stock, then name
    return filtered
      .slice()
      .sort((a, b) => {
        const aMsR = getExpiryStatus(a.expiresAt).msRemaining;
        const bMsR = getExpiryStatus(b.expiresAt).msRemaining;
        if (aMsR !== bMsR) return aMsR - bMsR;
        return a.name.localeCompare(b.name);
      })
      .slice(0, this._config.max_items ?? 12);
  }

  private _getSummary() {
    const all = this._getAllItems();
    const expiring = all.filter((i) => {
      const { severity } = getExpiryStatus(i.expiresAt);
      return severity === "critical" || severity === "warning";
    });
    const lowStock = all.filter(isLowStock);
    return { total: all.length, expiring: expiring.length, lowStock: lowStock.length };
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  private _decrementItem(itemId: string, event: Event) {
    event.stopPropagation();
    if (!this._hass) return;
    this._hass
      .callService("culiplan", "pantry_decrement", { item_id: itemId })
      .catch(() => {/* HA will show error toast */});
  }

  private _addToShopping(item: PantryItem, event: Event) {
    event.stopPropagation();
    if (!this._hass || !this._config.shopping_entity) return;
    this._hass
      .callService("todo", "add_item", {
        entity_id: this._config.shopping_entity,
        item: `${item.name}${item.unit ? ` (${item.unit})` : ""}`,
      })
      .catch(() => {});
  }

  private _toggleActionSheet(itemId: string, event: Event) {
    event.stopPropagation();
    this._selectedItemId = this._selectedItemId === itemId ? null : itemId;
  }

  private _closeActionSheet() {
    this._selectedItemId = null;
  }

  private _setFilter(filter: FilterMode) {
    this._activeFilter = filter;
    this._selectedItemId = null;
  }

  // ── Render helpers ────────────────────────────────────────────────────────

  private _renderFilterChips(summary: ReturnType<typeof this._getSummary>) {
    const chips: Array<{ key: FilterMode; label: string; count: number }> = [
      { key: "all", label: "All", count: summary.total },
      { key: "expiring", label: "Expiring", count: summary.expiring },
      { key: "low_stock", label: "Low stock", count: summary.lowStock },
    ];
    return html`
      <div class="filter-chips" role="group" aria-label="Filter pantry items">
        ${chips.map(
          (chip) => html`
            <button
              class="chip ${this._activeFilter === chip.key ? "chip--active" : ""}"
              @click=${() => this._setFilter(chip.key)}
              aria-pressed="${this._activeFilter === chip.key}"
            >
              ${chip.label}
              ${chip.count > 0 ? html`<span class="chip-count">${chip.count}</span>` : ""}
            </button>
          `
        )}
      </div>
    `;
  }

  private _renderTile(item: PantryItem) {
    const expiry = getExpiryStatus(item.expiresAt);
    const low = isLowStock(item);
    const isOpen = this._selectedItemId === item.id;

    const severityClass =
      expiry.severity === "critical"
        ? "tile--critical"
        : expiry.severity === "warning"
        ? "tile--warning"
        : "";

    return html`
      <article
        class="tile ${severityClass} ${isOpen ? "tile--open" : ""}"
        @click=${(e: Event) => this._toggleActionSheet(item.id, e)}
        role="button"
        tabindex="0"
        @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this._toggleActionSheet(item.id, e)}
        aria-expanded="${isOpen}"
        aria-label="${item.name}, quantity ${item.quantity}${item.unit ? " " + item.unit : ""}"
      >
        <div class="tile-main">
          <div class="tile-name-row">
            <span class="tile-name">${item.name}</span>
            <div class="tile-badges">
              ${expiry.severity === "critical" || expiry.severity === "warning"
                ? html`<span class="badge badge--expiry badge--${expiry.severity}">
                    <span class="badge-icon">${ICON_ALERT}</span>
                    ${expiry.label}
                  </span>`
                : ""}
              ${low
                ? html`<span class="badge badge--low-stock">
                    <span class="badge-icon">${ICON_TRENDING_DOWN}</span>
                    Low
                  </span>`
                : ""}
            </div>
          </div>
          <div class="tile-quantity">
            <span class="quantity-value">${item.quantity}</span>
            ${item.unit ? html`<span class="quantity-unit">${item.unit}</span>` : ""}
          </div>
        </div>

        ${isOpen
          ? html`
              <div
                class="action-sheet"
                @click=${(e: Event) => e.stopPropagation()}
                role="group"
                aria-label="Actions for ${item.name}"
              >
                <button
                  class="action-btn action-btn--decrement"
                  @click=${(e: Event) => this._decrementItem(item.id, e)}
                  aria-label="Use one ${item.unit ?? "unit"} of ${item.name}"
                >
                  <span class="action-icon">${ICON_MINUS}</span>
                  Use one
                </button>
                <button
                  class="action-btn action-btn--shopping"
                  @click=${(e: Event) => this._addToShopping(item, e)}
                  aria-label="Add ${item.name} to shopping list"
                >
                  <span class="action-icon">${ICON_CART}</span>
                  Add to shopping
                </button>
                <button
                  class="action-btn action-btn--close"
                  @click=${(e: Event) => { e.stopPropagation(); this._closeActionSheet(); }}
                  aria-label="Close actions"
                >
                  <span class="action-icon">${ICON_X}</span>
                </button>
              </div>
            `
          : ""}
      </article>
    `;
  }

  private _renderEmptyState() {
    const filterLabel = FILTER_LABELS[this._activeFilter];
    return html`
      <div class="empty-state">
        <div class="empty-icon">${ICON_BOX}</div>
        <p class="empty-title">
          ${this._activeFilter === "all"
            ? "Pantry is empty"
            : `No items matching "${filterLabel}"`}
        </p>
        <p class="empty-subtitle">
          ${this._activeFilter === "all"
            ? "Add items in the Culiplan app to track your pantry here."
            : "Try switching to a different filter."}
        </p>
      </div>
    `;
  }

  // ── Main render ───────────────────────────────────────────────────────────

  render() {
    const isLoading = !this._hass;
    const summary = this._getSummary();
    const items = this._getFilteredItems();
    const title = this._config.title ?? "Pantry";

    if (isLoading) {
      return html`
        <ha-card>
          <div class="card-content loading">
            <div class="skeleton-header"></div>
            <div class="skeleton-chips"></div>
            <div class="tile-grid">
              ${[1, 2, 3, 4, 5, 6].map(() => html`<div class="skeleton-tile"></div>`)}
            </div>
          </div>
        </ha-card>
      `;
    }

    return html`
      <ha-card>
        <div class="card-header">
          <span class="header-icon">${ICON_BOX}</span>
          <h2 class="header-title">${title}</h2>
          <div class="header-summary">
            ${summary.expiring > 0
              ? html`<span class="summary-badge summary-badge--warning" aria-label="${summary.expiring} items expiring soon">
                  ${summary.expiring}
                </span>`
              : ""}
            ${summary.lowStock > 0
              ? html`<span class="summary-badge summary-badge--low" aria-label="${summary.lowStock} items low in stock">
                  ${summary.lowStock}
                </span>`
              : ""}
          </div>
        </div>
        <div class="card-content">
          ${this._renderFilterChips(summary)}
          ${items.length > 0
            ? html`<div class="tile-grid">${items.map((i) => this._renderTile(i))}</div>`
            : this._renderEmptyState()}
        </div>
      </ha-card>
    `;
  }

  // ── Styles ────────────────────────────────────────────────────────────────

  static get styles() {
    return css`
      :host {
        display: block;
        font-family: var(--culiplan-font-body, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
      }

      ha-card {
        overflow: hidden;
        background: var(--culiplan-surface, var(--card-background-color, #fff));
        box-shadow: var(--culiplan-shadow-card,
          var(--ha-card-box-shadow, 0 2px 12px 0 rgba(242,103,68,0.08)));
        border-radius: var(--culiplan-radius-xl, 12px);
        border: 1px solid var(--culiplan-border, var(--divider-color, #e5e7eb));
      }

      /* ── Header ───────────────────────────────────────────────── */
      .card-header {
        display: flex;
        align-items: center;
        gap: var(--culiplan-space-2, 8px);
        padding: var(--culiplan-space-4, 16px) var(--culiplan-space-4, 16px)
                 var(--culiplan-space-2, 8px);
        background: var(--culiplan-gradient-green,
          linear-gradient(135deg, #16A34A 0%, #22C55E 100%));
        color: var(--culiplan-white, #fff);
      }

      .header-icon {
        width: 22px;
        height: 22px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
      }

      .header-icon svg {
        width: 100%;
        height: 100%;
      }

      .header-title {
        margin: 0;
        flex: 1;
        font-size: var(--culiplan-text-lg, 18px);
        font-weight: var(--culiplan-font-semibold, 600);
        line-height: var(--culiplan-leading-tight, 1.25);
        color: inherit;
      }

      .header-summary {
        display: flex;
        gap: var(--culiplan-space-1, 4px);
      }

      .summary-badge {
        font-size: var(--culiplan-text-xs, 12px);
        font-weight: var(--culiplan-font-bold, 700);
        padding: 2px 8px;
        border-radius: var(--culiplan-radius-full, 9999px);
        line-height: 1.4;
      }

      .summary-badge--warning {
        background: var(--culiplan-error, #ef4444);
        color: var(--culiplan-white, #fff);
      }

      .summary-badge--low {
        background: var(--culiplan-warning, #eab308);
        color: var(--culiplan-black, #000);
      }

      /* ── Card content ─────────────────────────────────────────── */
      .card-content {
        padding: var(--culiplan-space-3, 12px);
        display: flex;
        flex-direction: column;
        gap: var(--culiplan-space-3, 12px);
      }

      /* ── Filter chips ─────────────────────────────────────────── */
      .filter-chips {
        display: flex;
        gap: var(--culiplan-space-2, 8px);
        flex-wrap: wrap;
      }

      .chip {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 4px 12px;
        border-radius: var(--culiplan-radius-full, 9999px);
        border: 1.5px solid var(--culiplan-border, #e5e7eb);
        background: transparent;
        color: var(--culiplan-text-secondary, #6b7280);
        font-family: inherit;
        font-size: var(--culiplan-text-xs, 12px);
        font-weight: var(--culiplan-font-medium, 500);
        cursor: pointer;
        transition: var(--culiplan-transition-fast, all 150ms cubic-bezier(0,0,0.2,1));
      }

      .chip:hover {
        border-color: var(--culiplan-primary, #f26744);
        color: var(--culiplan-primary, #f26744);
      }

      .chip--active {
        background: var(--culiplan-primary, #f26744);
        border-color: var(--culiplan-primary, #f26744);
        color: var(--culiplan-white, #fff);
      }

      .chip--active:hover {
        background: var(--culiplan-primary-dark, #d94d2a);
        border-color: var(--culiplan-primary-dark, #d94d2a);
        color: var(--culiplan-white, #fff);
      }

      .chip:focus-visible {
        outline: 2px solid var(--culiplan-primary, #f26744);
        outline-offset: 2px;
      }

      .chip-count {
        background: rgba(0, 0, 0, 0.12);
        border-radius: var(--culiplan-radius-full, 9999px);
        padding: 0 5px;
        font-size: 10px;
        font-weight: var(--culiplan-font-bold, 700);
        line-height: 1.6;
        min-width: 16px;
        text-align: center;
      }

      .chip--active .chip-count {
        background: rgba(255, 255, 255, 0.25);
      }

      /* ── Tile grid ────────────────────────────────────────────── */
      .tile-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: var(--culiplan-space-2, 8px);
      }

      /* ── Tile ─────────────────────────────────────────────────── */
      .tile {
        background: var(--culiplan-surface, #fff);
        border: 1.5px solid var(--culiplan-border, #e5e7eb);
        border-radius: var(--culiplan-radius-lg, 8px);
        padding: var(--culiplan-space-2, 8px) var(--culiplan-space-3, 12px);
        cursor: pointer;
        transition: var(--culiplan-transition-fast, all 150ms cubic-bezier(0,0,0.2,1));
        display: flex;
        flex-direction: column;
        gap: var(--culiplan-space-2, 8px);
        position: relative;
      }

      .tile:hover {
        border-color: var(--culiplan-primary, #f26744);
        box-shadow: var(--culiplan-shadow-soft, 0 1px 3px 0 rgba(0,0,0,0.06));
        transform: translateY(-1px);
      }

      .tile:focus-visible {
        outline: 2px solid var(--culiplan-primary, #f26744);
        outline-offset: 2px;
      }

      .tile--critical {
        border-color: var(--culiplan-error, #ef4444);
        background: rgba(239, 68, 68, 0.04);
      }

      .tile--warning {
        border-color: var(--culiplan-warning, #eab308);
        background: rgba(234, 179, 8, 0.04);
      }

      .tile--open {
        border-color: var(--culiplan-primary, #f26744);
        box-shadow: var(--culiplan-shadow-medium, 0 4px 6px -1px rgba(0,0,0,0.07));
      }

      /* ── Tile main area ───────────────────────────────────────── */
      .tile-main {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .tile-name-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 4px;
      }

      .tile-name {
        font-size: var(--culiplan-text-sm, 14px);
        font-weight: var(--culiplan-font-semibold, 600);
        color: var(--culiplan-text-primary, #1c1917);
        line-height: var(--culiplan-leading-tight, 1.25);
        word-break: break-word;
      }

      .tile-badges {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
        flex-shrink: 0;
      }

      .badge {
        display: flex;
        align-items: center;
        gap: 2px;
        font-size: 10px;
        font-weight: var(--culiplan-font-bold, 700);
        padding: 1px 5px;
        border-radius: var(--culiplan-radius-full, 9999px);
        white-space: nowrap;
        line-height: 1.4;
      }

      .badge-icon {
        width: 10px;
        height: 10px;
        display: flex;
        align-items: center;
      }

      .badge-icon svg {
        width: 100%;
        height: 100%;
      }

      .badge--critical {
        background: var(--culiplan-error, #ef4444);
        color: var(--culiplan-white, #fff);
      }

      .badge--warning {
        background: var(--culiplan-warning, #eab308);
        color: var(--culiplan-black, #000);
      }

      .badge--low-stock {
        background: var(--culiplan-muted, #f3f4f6);
        color: var(--culiplan-text-secondary, #6b7280);
        border: 1px solid var(--culiplan-border, #e5e7eb);
      }

      .tile-quantity {
        display: flex;
        align-items: baseline;
        gap: 3px;
      }

      .quantity-value {
        font-size: var(--culiplan-text-xl, 20px);
        font-weight: var(--culiplan-font-bold, 700);
        color: var(--culiplan-text-primary, #1c1917);
        line-height: 1;
      }

      .quantity-unit {
        font-size: var(--culiplan-text-xs, 12px);
        color: var(--culiplan-text-secondary, #6b7280);
        font-weight: var(--culiplan-font-medium, 500);
      }

      /* ── Action sheet ─────────────────────────────────────────── */
      .action-sheet {
        display: flex;
        gap: var(--culiplan-space-1, 4px);
        flex-wrap: wrap;
        padding-top: var(--culiplan-space-1, 4px);
        border-top: 1px solid var(--culiplan-border-subtle, #f3f4f6);
      }

      .action-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 5px 10px;
        border: none;
        border-radius: var(--culiplan-radius-md, 6px);
        cursor: pointer;
        font-family: inherit;
        font-size: var(--culiplan-text-xs, 12px);
        font-weight: var(--culiplan-font-semibold, 600);
        transition: var(--culiplan-transition-fast, all 150ms cubic-bezier(0,0,0.2,1));
        flex: 1;
        min-width: 0;
        justify-content: center;
      }

      .action-btn:focus-visible {
        outline: 2px solid var(--culiplan-primary, #f26744);
        outline-offset: 2px;
      }

      .action-icon {
        width: 12px;
        height: 12px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
      }

      .action-icon svg {
        width: 100%;
        height: 100%;
      }

      .action-btn--decrement {
        background: var(--culiplan-muted, #f3f4f6);
        color: var(--culiplan-text-primary, #1c1917);
      }

      .action-btn--decrement:hover {
        background: var(--culiplan-gray-200, #e5e7eb);
      }

      .action-btn--shopping {
        background: var(--culiplan-secondary, #16A34A);
        color: var(--culiplan-white, #fff);
      }

      .action-btn--shopping:hover {
        background: var(--culiplan-secondary-dark, #15803d);
      }

      .action-btn--close {
        flex: 0;
        padding: 5px 8px;
        background: transparent;
        color: var(--culiplan-text-muted, #9ca3af);
      }

      .action-btn--close:hover {
        background: var(--culiplan-muted, #f3f4f6);
        color: var(--culiplan-text-primary, #1c1917);
      }

      /* ── Empty state ──────────────────────────────────────────── */
      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: var(--culiplan-space-8, 32px) var(--culiplan-space-4, 16px);
        gap: var(--culiplan-space-2, 8px);
      }

      .empty-icon {
        width: 40px;
        height: 40px;
        color: var(--culiplan-secondary, #16A34A);
        opacity: 0.4;
        display: flex;
        align-items: center;
      }

      .empty-icon svg {
        width: 100%;
        height: 100%;
      }

      .empty-title {
        margin: 0;
        font-size: var(--culiplan-text-sm, 14px);
        font-weight: var(--culiplan-font-semibold, 600);
        color: var(--culiplan-text-primary, #1c1917);
      }

      .empty-subtitle {
        margin: 0;
        font-size: var(--culiplan-text-xs, 12px);
        color: var(--culiplan-text-secondary, #6b7280);
      }

      /* ── Loading skeletons ────────────────────────────────────── */
      .loading {
        gap: var(--culiplan-space-3, 12px);
      }

      @keyframes skeleton-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
      }

      .skeleton-header,
      .skeleton-chips,
      .skeleton-tile {
        background: var(--culiplan-muted, #f3f4f6);
        border-radius: var(--culiplan-radius-md, 6px);
        animation: skeleton-pulse 1.8s ease-in-out infinite;
      }

      .skeleton-header { height: 28px; width: 40%; }
      .skeleton-chips  { height: 32px; width: 70%; }
      .skeleton-tile   { height: 72px; }

      /* ── Responsive ───────────────────────────────────────────── */
      @container (max-width: 360px) {
        .tile-grid {
          grid-template-columns: 1fr 1fr;
        }
        .tile-name {
          font-size: var(--culiplan-text-xs, 12px);
        }
        .quantity-value {
          font-size: var(--culiplan-text-lg, 18px);
        }
      }

      @container (min-width: 600px) {
        .tile-grid {
          grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        }
      }
    `;
  }
}

customElements.define("culiplan-pantry-tracker", CuliplanPantryTracker);

(window as any).customCards = (window as any).customCards ?? [];
(window as any).customCards.push({
  type: "culiplan-pantry-tracker",
  name: "Culiplan Pantry Tracker",
  description: "Track pantry stock levels with expiry warnings and low-stock indicators. Part of the Culiplan integration card pack.",
  preview: true,
  documentationURL: "https://github.com/culiplan/home-assistant-culiplan/tree/main/lovelace",
});
