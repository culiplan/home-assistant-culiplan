/**
 * Culiplan Blueprint Generator Card (task-1400)
 *
 * LitElement-based Lovelace custom card.
 *
 * Provides a text input for entering a natural language automation description,
 * a "Generate" button that calls culiplan.generate_blueprint, a YAML preview
 * area with copy-to-clipboard, and an "Install" button to write the blueprint
 * to config/blueprints/automation/culiplan/.
 *
 * States: idle → loading → result (yaml preview) | error
 * Listens for culiplan_blueprint_generated HA event to display the result.
 *
 * Registration: culiplan-blueprint-generator
 */

import { LitElement, html, css } from "lit";
import { property, state } from "lit/decorators.js";

// ── HA types (minimal surface — no external imports) ──────────────────────

interface HomeAssistant {
  callService(domain: string, service: string, data: Record<string, unknown>): Promise<void>;
  connection: {
    subscribeEvents(
      callback: (event: HAEvent) => void,
      eventType: string,
    ): Promise<() => void>;
  };
  language: string;
}

interface HAEvent {
  data: BlueprintEventData;
}

interface CardConfig {
  /** Card title override */
  title?: string;
  /**
   * When true the "Install" button is shown after successful generation.
   * Default: true.
   */
  show_install?: boolean;
  /**
   * Comma-separated or array of HA entity IDs to pass as available_entities
   * when calling the service. Optional.
   */
  available_entities?: string | string[];
}

interface BlueprintEventData {
  name: string;
  description: string;
  yaml: string;
  valid: boolean;
  warnings: string[];
  mode: string;
  installed_path?: string | null;
}

// ── Icons ─────────────────────────────────────────────────────────────────

const ICON_WAND = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8 19 13"/><path d="M15 9h0"/><path d="M17.8 6.2 19 5"/><path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/></svg>`;
const ICON_COPY = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_INSTALL = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
const ICON_SPINNER = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`;
const ICON_ALERT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
const ICON_CHECK = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;

// ── Card class ──────────────────────────────────────────────────────────────

type CardState = "idle" | "loading" | "result" | "error";

class CuliplanBlueprintGeneratorCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;

  @state() private _config: CardConfig = {};
  @state() private _prompt = "";
  @state() private _cardState: CardState = "idle";
  @state() private _result: BlueprintEventData | null = null;
  @state() private _errorMessage = "";
  @state() private _copied = false;
  @state() private _installed = false;

  private _unsubscribeEvent: (() => void) | null = null;

  setConfig(config: CardConfig): void {
    this._config = { show_install: true, ...config };
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._subscribeToEvents();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._unsubscribeEvent) {
      this._unsubscribeEvent();
      this._unsubscribeEvent = null;
    }
  }

  private async _subscribeToEvents(): Promise<void> {
    if (!this.hass) return;
    try {
      this._unsubscribeEvent = await this.hass.connection.subscribeEvents(
        (event: HAEvent) => this._handleBlueprintEvent(event),
        "culiplan_blueprint_generated",
      );
    } catch {
      // Non-fatal — events won't auto-populate the result
    }
  }

  private _handleBlueprintEvent(event: HAEvent): void {
    if (this._cardState !== "loading") return;
    this._result = event.data;
    this._cardState = "result";
    this._installed = !!event.data.installed_path;
  }

  private _getAvailableEntities(): string[] | undefined {
    const ae = this._config.available_entities;
    if (!ae) return undefined;
    if (Array.isArray(ae)) return ae;
    return ae.split(",").map((s) => s.trim()).filter(Boolean);
  }

  private async _handleGenerate(): Promise<void> {
    const prompt = this._prompt.trim();
    if (prompt.length < 5) {
      this._errorMessage = "Please enter at least 5 characters.";
      this._cardState = "error";
      return;
    }

    this._cardState = "loading";
    this._result = null;
    this._errorMessage = "";
    this._installed = false;

    const serviceData: Record<string, unknown> = { prompt };
    const entities = this._getAvailableEntities();
    if (entities?.length) serviceData["available_entities"] = entities;

    try {
      await this.hass.callService("culiplan", "generate_blueprint", serviceData);
      // Result arrives via culiplan_blueprint_generated event
      // Fallback timeout: if no event in 60s, show a timeout error
      setTimeout(() => {
        if (this._cardState === "loading") {
          this._errorMessage = "Blueprint generation timed out. Please try again.";
          this._cardState = "error";
        }
      }, 60_000);
    } catch (err) {
      this._errorMessage = err instanceof Error ? err.message : String(err);
      this._cardState = "error";
    }
  }

  private async _handleInstall(): Promise<void> {
    if (!this._result?.yaml) return;
    this._cardState = "loading";
    try {
      const serviceData: Record<string, unknown> = {
        prompt: this._prompt.trim(),
        install: true,
      };
      const entities = this._getAvailableEntities();
      if (entities?.length) serviceData["available_entities"] = entities;
      await this.hass.callService("culiplan", "generate_blueprint", serviceData);
    } catch (err) {
      this._errorMessage = err instanceof Error ? err.message : String(err);
      this._cardState = "error";
    }
  }

  private async _handleCopy(): Promise<void> {
    if (!this._result?.yaml) return;
    try {
      await navigator.clipboard.writeText(this._result.yaml);
      this._copied = true;
      setTimeout(() => { this._copied = false; }, 2000);
    } catch {
      // clipboard API not available
    }
  }

  private _handleReset(): void {
    this._cardState = "idle";
    this._result = null;
    this._errorMessage = "";
    this._prompt = "";
  }

  static get styles() {
    return css`
      :host {
        display: block;
        --fp-primary: var(--primary-color, #e67e22);
        --fp-surface: var(--card-background-color, #fff);
        --fp-on-surface: var(--primary-text-color, #333);
        --fp-muted: var(--secondary-text-color, #666);
        --fp-border: var(--divider-color, #e0e0e0);
        --fp-error: var(--error-color, #db4437);
        --fp-success: var(--success-color, #43a047);
        --fp-radius: 12px;
        --fp-gap: 12px;
      }

      ha-card {
        padding: 16px;
        border-radius: var(--fp-radius);
      }

      .header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: var(--fp-gap);
      }

      .header svg {
        width: 20px;
        height: 20px;
        color: var(--fp-primary);
        flex-shrink: 0;
      }

      h3 {
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
        color: var(--fp-on-surface);
      }

      textarea {
        width: 100%;
        min-height: 80px;
        padding: 10px 12px;
        border: 1.5px solid var(--fp-border);
        border-radius: 8px;
        font-size: 0.9rem;
        font-family: inherit;
        color: var(--fp-on-surface);
        background: transparent;
        resize: vertical;
        box-sizing: border-box;
        transition: border-color 0.15s;
        outline: none;
      }

      textarea:focus {
        border-color: var(--fp-primary);
      }

      .actions {
        display: flex;
        gap: 8px;
        margin-top: 10px;
        flex-wrap: wrap;
      }

      button {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        border: none;
        border-radius: 8px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: opacity 0.15s, background 0.15s;
      }

      button:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }

      button svg {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
      }

      .btn-primary {
        background: var(--fp-primary);
        color: #fff;
      }

      .btn-primary:not(:disabled):hover {
        opacity: 0.88;
      }

      .btn-secondary {
        background: transparent;
        color: var(--fp-on-surface);
        border: 1.5px solid var(--fp-border);
      }

      .btn-secondary:not(:disabled):hover {
        background: var(--fp-border);
      }

      .btn-ghost {
        background: transparent;
        color: var(--fp-muted);
        padding: 4px 8px;
        font-size: 0.8rem;
      }

      /* Loading state */
      .loading-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 0;
        color: var(--fp-muted);
        font-size: 0.875rem;
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      .spin {
        animation: spin 1.2s linear infinite;
        width: 18px;
        height: 18px;
      }

      /* Result state */
      .result-header {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-bottom: 8px;
      }

      .result-header svg {
        width: 18px;
        height: 18px;
        color: var(--fp-success);
        flex-shrink: 0;
        margin-top: 2px;
      }

      .result-meta {
        flex: 1;
      }

      .result-name {
        font-weight: 600;
        font-size: 0.95rem;
        color: var(--fp-on-surface);
      }

      .result-desc {
        font-size: 0.8rem;
        color: var(--fp-muted);
        margin-top: 2px;
      }

      .yaml-preview {
        background: var(--code-editor-background-color, #1e1e2e);
        color: var(--code-editor-text-color, #cdd6f4);
        border-radius: 8px;
        padding: 12px;
        font-family: monospace;
        font-size: 0.78rem;
        line-height: 1.5;
        max-height: 280px;
        overflow: auto;
        white-space: pre;
        margin: 10px 0;
        box-sizing: border-box;
      }

      .warnings {
        background: #fff8e1;
        border-left: 3px solid #ffc107;
        padding: 8px 12px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.8rem;
        color: #5d4037;
      }

      .warnings ul {
        margin: 4px 0 0 0;
        padding-left: 16px;
      }

      /* Error state */
      .error-row {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 10px 12px;
        background: #fce4ec;
        border-radius: 8px;
        margin-top: 8px;
        font-size: 0.875rem;
        color: var(--fp-error);
      }

      .error-row svg {
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        margin-top: 1px;
      }

      .installed-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: #e8f5e9;
        color: var(--fp-success);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
      }

      .installed-badge svg {
        width: 14px;
        height: 14px;
      }
    `;
  }

  render() {
    const title = this._config.title ?? "Blueprint Generator";
    const showInstall = this._config.show_install !== false;

    return html`
      <ha-card>
        <div class="header">
          ${ICON_WAND}
          <h3>${title}</h3>
        </div>

        ${this._cardState !== "result" ? html`
          <textarea
            .value=${this._prompt}
            @input=${(e: Event) => { this._prompt = (e.target as HTMLTextAreaElement).value; }}
            placeholder="Describe the automation you want — e.g. 'Notify me at 7am with today's meal plan'"
            ?disabled=${this._cardState === "loading"}
          ></textarea>
        ` : ""}

        ${this._cardState === "idle" || this._cardState === "error" ? html`
          <div class="actions">
            <button
              class="btn-primary"
              @click=${this._handleGenerate}
              ?disabled=${this._prompt.trim().length < 5}
            >
              ${ICON_WAND}
              Generate blueprint
            </button>
          </div>
        ` : ""}

        ${this._cardState === "loading" ? html`
          <div class="loading-row">
            ${ICON_SPINNER}
            Generating blueprint…
          </div>
        ` : ""}

        ${this._cardState === "error" ? html`
          <div class="error-row">
            ${ICON_ALERT}
            <span>${this._errorMessage || "Blueprint generation failed. Please try again."}</span>
          </div>
        ` : ""}

        ${this._cardState === "result" && this._result ? html`
          <div class="result-header">
            ${ICON_CHECK}
            <div class="result-meta">
              <div class="result-name">${this._result.name}</div>
              ${this._result.description ? html`<div class="result-desc">${this._result.description}</div>` : ""}
            </div>
          </div>

          ${this._result.warnings?.length ? html`
            <div class="warnings">
              <strong>Warnings</strong>
              <ul>
                ${this._result.warnings.map((w) => html`<li>${w}</li>`)}
              </ul>
            </div>
          ` : ""}

          <div class="yaml-preview">${this._result.yaml}</div>

          <div class="actions">
            ${this._installed ? html`
              <span class="installed-badge">
                ${ICON_CHECK}
                Installed
              </span>
            ` : showInstall && this._result.valid ? html`
              <button class="btn-primary" @click=${this._handleInstall}>
                ${ICON_INSTALL}
                Install
              </button>
            ` : ""}

            <button class="btn-secondary" @click=${this._handleCopy}>
              ${ICON_COPY}
              ${this._copied ? "Copied!" : "Copy YAML"}
            </button>

            <button class="btn-ghost" @click=${this._handleReset}>
              New blueprint
            </button>
          </div>
        ` : ""}
      </ha-card>
    `;
  }
}

customElements.define(
  "culiplan-blueprint-generator",
  CuliplanBlueprintGeneratorCard,
);

declare global {
  interface HTMLElementTagNameMap {
    "culiplan-blueprint-generator": CuliplanBlueprintGeneratorCard;
  }
}
