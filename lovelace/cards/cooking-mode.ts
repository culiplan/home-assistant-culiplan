/**
 * Culiplan Cooking Mode Card — Phase 3 (task-1383)
 *
 * LitElement-based Lovelace custom card. Displays the active cooking session
 * from the Culiplan backend: step list with current step highlighted, active
 * timers with HA-native countdown, and a voice-ready "next step" action.
 *
 * Architecture (§8 Q7 + §6.2):
 *   - Reads cooking session state from sensor.culiplan_active_cooking_session
 *     (attributes carry the full CookingSession shape, coordinator polls the
 *     /api/cooking-sessions endpoint and updates the sensor on every mutation).
 *   - Step advancement calls the culiplan.advance_cooking_step HA service,
 *     which in turn PATCHes /api/cooking-sessions/:id with the next step and
 *     surface = 'HOME_ASSISTANT'.
 *   - Timers are mirrored to HA timer entities (timer.culiplan_step_<n>) by
 *     the coordinator; the card reads countdown state directly from HA, so
 *     HA owns the countdown UI as required by §6.2.
 *   - When no active session exists (sensor state = 'idle'), the card shows
 *     a graceful fallback CTA: "Start cooking from a recipe".
 *   - Voice 'next step' intent is handled by the existing Assist intent
 *     registered in custom_components/culiplan/intent_scripts.yaml.
 *
 * Design tokens: all visual values from ../tokens.css (auto-loaded by __init__.py).
 *
 * Registration: culiplan-cooking-mode
 */

import { LitElement, html, css } from "lit";

// ── Types ─────────────────────────────────────────────────────────────────────

interface CookingTimer {
  id: string;
  label: string;
  startedAt: string;       // ISO 8601
  durationSec: number;
  remainingSec: number;    // recomputed on read (not stored)
  stepIndex: number | null;
  /** HA timer entity_id if one has been created (e.g. timer.culiplan_step_2) */
  haTimerEntityId?: string;
}

interface CookingSession {
  id: string;
  userId: string;
  recipeId: string;
  servings: number;
  startedAt: string;
  currentStep: number;     // 0-indexed
  totalSteps: number;
  stepStartedAt: string | null;
  timers: CookingTimer[];
  status: "active" | "paused" | "completed" | "abandoned";
  surface: "mobile" | "web" | "home-assistant";
  updatedAt: string;
}

/** Attributes on sensor.culiplan_active_cooking_session */
interface CookingSessionSensorAttributes {
  /** Full CookingSession object, or null when no active session */
  session?: CookingSession | null;
  /** Recipe title for display */
  recipe_title?: string;
  /** Recipe image URL */
  recipe_image_url?: string;
  /** Array of step descriptions, index = step number */
  steps?: string[];
  friendly_name?: string;
}

interface CardConfig {
  /** HA entity_id for the cooking session sensor (default: sensor.culiplan_active_cooking_session) */
  entity?: string;
  /** Override the card title */
  title?: string;
  /** Show the step index numbers in the step list (default: true) */
  show_step_numbers?: boolean;
  /** Max timers to display prominently (default: 3) */
  max_timers?: number;
}

// ── Icons ─────────────────────────────────────────────────────────────────────

const ICON_CHEF_HAT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>`;
const ICON_PLAY = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
const ICON_PAUSE = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
const ICON_ARROW_RIGHT = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
const ICON_CLOCK = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
const ICON_MIC = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
const ICON_CHECK = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_UTENSILS = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>`;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format seconds as mm:ss for countdown display */
function fmtCountdown(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Compute progress bar width for a timer */
function timerProgress(timer: CookingTimer): number {
  if (!timer.durationSec) return 0;
  return Math.max(0, Math.min(100, (timer.remainingSec / timer.durationSec) * 100));
}

// ── Component ─────────────────────────────────────────────────────────────────

class FlavorplanCookingMode extends LitElement {
  private _config: CardConfig = {};
  private _hass: any = null;

  // State flags
  private _isAdvancing = false;      // debounce step advance taps
  private _isToggling = false;       // debounce pause/resume taps

  static get properties() {
    return {
      _config: { type: Object },
      _hass: { type: Object },
      _isAdvancing: { type: Boolean },
      _isToggling: { type: Boolean },
    };
  }

  // ── HA lifecycle ──────────────────────────────────────────────────────────

  setConfig(config: CardConfig) {
    this._config = {
      entity: "sensor.culiplan_active_cooking_session",
      title: "Cooking",
      show_step_numbers: true,
      max_timers: 3,
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

  // ── Data extraction ───────────────────────────────────────────────────────

  private _getEntityState(): { state: string; attributes: CookingSessionSensorAttributes } | null {
    if (!this._hass || !this._config.entity) return null;
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) return null;
    return { state: stateObj.state, attributes: stateObj.attributes || {} };
  }

  private _getSession(): CookingSession | null {
    const entityState = this._getEntityState();
    if (!entityState) return null;
    if (entityState.state === "idle" || !entityState.attributes.session) return null;
    return entityState.attributes.session;
  }

  private _getTimerEntityState(entityId: string): { state: string; attributes: any } | null {
    if (!this._hass || !entityId) return null;
    const stateObj = this._hass.states[entityId];
    if (!stateObj) return null;
    return { state: stateObj.state, attributes: stateObj.attributes || {} };
  }

  /** Get remaining seconds from HA timer entity (HA-native countdown) */
  private _getHATimerRemaining(haEntityId: string): number | null {
    const stateObj = this._getTimerEntityState(haEntityId);
    if (!stateObj) return null;
    // HA timer entity stores finishes_at as ISO timestamp in attributes
    if (stateObj.state === "active" && stateObj.attributes.finishes_at) {
      const msLeft = new Date(stateObj.attributes.finishes_at).getTime() - Date.now();
      return Math.max(0, Math.floor(msLeft / 1000));
    }
    if (stateObj.state === "idle") return 0;
    return null;
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  /** Advance to the next step by calling the culiplan.advance_cooking_step service */
  private async _advanceStep(session: CookingSession): Promise<void> {
    if (this._isAdvancing) return;
    if (session.currentStep >= session.totalSteps - 1) return; // already at last step
    this._isAdvancing = true;
    this.requestUpdate();

    try {
      await this._hass.callService("culiplan", "advance_cooking_step", {
        session_id: session.id,
        step: session.currentStep + 1,
        surface: "home-assistant",
      });
    } finally {
      // Reset after 1s to prevent double-tap
      setTimeout(() => {
        this._isAdvancing = false;
        this.requestUpdate();
      }, 1000);
    }
  }

  /** Jump to a specific step by tapping it in the list */
  private async _goToStep(session: CookingSession, stepIndex: number): Promise<void> {
    if (stepIndex === session.currentStep) return; // already there
    await this._hass.callService("culiplan", "advance_cooking_step", {
      session_id: session.id,
      step: stepIndex,
      surface: "home-assistant",
    });
  }

  /** Toggle pause / resume */
  private async _togglePause(session: CookingSession): Promise<void> {
    if (this._isToggling) return;
    this._isToggling = true;
    this.requestUpdate();

    const newStatus = session.status === "active" ? "paused" : "active";
    try {
      await this._hass.callService("culiplan", "update_cooking_session", {
        session_id: session.id,
        status: newStatus,
        surface: "home-assistant",
      });
    } finally {
      setTimeout(() => {
        this._isToggling = false;
        this.requestUpdate();
      }, 500);
    }
  }

  /** Open the recipe entity's more-info panel (navigates to a recipe deep-link) */
  private _openRecipe(session: CookingSession): void {
    // Fire the standard HA navigate event to open a culiplan recipe deep-link
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId: `sensor.culiplan_recipe_${session.recipeId}` },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  render() {
    if (!this._hass) {
      return html`<ha-card><div class="loading">Loading…</div></ha-card>`;
    }

    const session = this._getSession();

    if (!session) {
      return this._renderFallback();
    }

    return this._renderSession(session);
  }

  /** Graceful fallback when no active session (AC#5) */
  private _renderFallback() {
    return html`
      <ha-card class="cooking-card cooking-card--idle">
        <div class="card-header">
          <span class="header-icon">${ICON_CHEF_HAT}</span>
          <span class="header-title">${this._config.title ?? "Cooking"}</span>
        </div>
        <div class="fallback-body">
          <div class="fallback-illustration">${ICON_UTENSILS}</div>
          <p class="fallback-headline">No active cooking session</p>
          <p class="fallback-subtext">
            Start cooking from a recipe in the Culiplan app, or say
            <em>"Hey Google, start cooking [recipe name]"</em>
          </p>
          <div class="fallback-hint">
            ${ICON_MIC}
            <span>Voice: "Hey Google, start cooking pasta"</span>
          </div>
        </div>
      </ha-card>
    `;
  }

  private _renderSession(session: CookingSession) {
    const entityState = this._getEntityState();
    const attrs = entityState?.attributes ?? {};
    const recipeTitle = attrs.recipe_title ?? `Recipe ${session.recipeId}`;
    const recipeImage = attrs.recipe_image_url;
    const steps: string[] = attrs.steps ?? [];
    const isPaused = session.status === "paused";
    const isCompleted = session.status === "completed";
    const maxTimers = this._config.max_timers ?? 3;

    // Progress metrics
    const progressPct = session.totalSteps > 0
      ? Math.round((session.currentStep / session.totalSteps) * 100)
      : 0;
    const stepsRemaining = session.totalSteps - session.currentStep;

    return html`
      <ha-card class="cooking-card ${isPaused ? "cooking-card--paused" : ""} ${isCompleted ? "cooking-card--done" : ""}">

        <!-- ── Header ──────────────────────────────────────────── -->
        <div class="card-header" @click=${() => this._openRecipe(session)}>
          ${recipeImage
            ? html`<img class="header-image" src="${recipeImage}" alt="${recipeTitle}" />`
            : html`<div class="header-image-placeholder">${ICON_CHEF_HAT}</div>`
          }
          <div class="header-meta">
            <span class="header-title">${recipeTitle}</span>
            <span class="header-subtitle">
              ${session.servings} serving${session.servings !== 1 ? "s" : ""}
              &middot;
              ${isPaused ? "Paused" : isCompleted ? "Done" : `Step ${session.currentStep + 1} of ${session.totalSteps}`}
            </span>
          </div>
          <button
            class="pause-btn ${isPaused ? "pause-btn--paused" : ""}"
            @click=${(e: Event) => { e.stopPropagation(); this._togglePause(session); }}
            title="${isPaused ? "Resume" : "Pause"}"
            ?disabled=${this._isToggling || isCompleted}
          >
            ${isPaused ? ICON_PLAY : ICON_PAUSE}
          </button>
        </div>

        <!-- ── Progress bar ────────────────────────────────────── -->
        <div class="progress-bar-track">
          <div class="progress-bar-fill" style="width: ${progressPct}%"></div>
        </div>
        <div class="progress-label">
          <span>${progressPct}% complete</span>
          <span>${stepsRemaining} step${stepsRemaining !== 1 ? "s" : ""} remaining</span>
        </div>

        <!-- ── Active timers ───────────────────────────────────── -->
        ${session.timers.length > 0 ? this._renderTimers(session.timers.slice(0, maxTimers)) : ""}

        <!-- ── Step list ───────────────────────────────────────── -->
        <div class="steps-list">
          ${session.totalSteps > 0
            ? Array.from({ length: session.totalSteps }, (_, i) => {
                const isActive = i === session.currentStep;
                const isDone = i < session.currentStep;
                const stepText = steps[i] ?? `Step ${i + 1}`;
                return html`
                  <div
                    class="step-row ${isActive ? "step-row--active" : ""} ${isDone ? "step-row--done" : ""}"
                    @click=${() => this._goToStep(session, i)}
                    tabindex="${isActive ? -1 : 0}"
                    role="button"
                    aria-label="Go to step ${i + 1}"
                  >
                    <div class="step-indicator">
                      ${isDone
                        ? html`<span class="step-check">${ICON_CHECK}</span>`
                        : html`<span class="step-number">${this._config.show_step_numbers ? i + 1 : ""}</span>`
                      }
                    </div>
                    <div class="step-text">${stepText}</div>
                    ${isActive
                      ? html`<div class="step-current-marker">${ICON_ARROW_RIGHT}</div>`
                      : ""
                    }
                  </div>
                `;
              })
            : html`<p class="no-steps">No step data available. Steps appear here when synced from the app.</p>`
          }
        </div>

        <!-- ── Footer: Next step / Done ────────────────────────── -->
        ${!isCompleted ? html`
          <div class="card-footer">
            <button
              class="next-btn ${this._isAdvancing ? "next-btn--loading" : ""}"
              @click=${() => this._advanceStep(session)}
              ?disabled=${this._isAdvancing || isPaused || session.currentStep >= session.totalSteps - 1}
            >
              ${session.currentStep >= session.totalSteps - 1
                ? html`${ICON_CHECK} <span>All steps done!</span>`
                : html`<span>Next step</span> ${ICON_ARROW_RIGHT}`
              }
            </button>
            <div class="voice-hint">
              ${ICON_MIC}
              <span>Say "next step" to advance</span>
            </div>
          </div>
        ` : html`
          <div class="card-footer card-footer--done">
            ${ICON_CHECK}
            <span>Cooking complete — enjoy your meal!</span>
          </div>
        `}

      </ha-card>
    `;
  }

  /** Render the active timers section with HA-native countdown */
  private _renderTimers(timers: CookingTimer[]) {
    return html`
      <div class="timers-section">
        <div class="timers-heading">
          ${ICON_CLOCK}
          <span>Active timers</span>
        </div>
        ${timers.map((timer) => {
          // Prefer HA timer entity countdown (HA owns the UI); fallback to remainingSec
          const haRemaining = timer.haTimerEntityId
            ? this._getHATimerRemaining(timer.haTimerEntityId)
            : null;
          const secsLeft = haRemaining !== null ? haRemaining : timer.remainingSec;
          const progress = timer.durationSec > 0
            ? Math.min(100, (secsLeft / timer.durationSec) * 100)
            : 0;
          const isExpired = secsLeft <= 0;

          return html`
            <div class="timer-row ${isExpired ? "timer-row--expired" : ""}">
              <div class="timer-label">${timer.label}</div>
              <div class="timer-countdown ${isExpired ? "timer-countdown--expired" : ""}">
                ${isExpired ? "Done!" : fmtCountdown(secsLeft)}
              </div>
              <div class="timer-bar-track">
                <div class="timer-bar-fill ${isExpired ? "timer-bar-fill--expired" : ""}" style="width: ${progress}%"></div>
              </div>
            </div>
          `;
        })}
      </div>
    `;
  }

  // ── Styles ────────────────────────────────────────────────────────────────

  static get styles() {
    return css`
      /* === Root variables — all from tokens.css on :root === */
      :host {
        --card-bg:           var(--culiplan-surface-default, #fff);
        --card-radius:       var(--culiplan-radius-2xl, 1.25rem);
        --primary:           var(--culiplan-primary, #f26744);
        --primary-light:     var(--culiplan-primary-light, #f58566);
        --secondary:         var(--culiplan-secondary, #16A34A);
        --text-primary:      var(--culiplan-text-primary, #111827);
        --text-secondary:    var(--culiplan-text-secondary, #4B5563);
        --text-muted:        var(--culiplan-text-muted, #9CA3AF);
        --border:            var(--culiplan-border-subtle, #E5E7EB);
        --step-active-bg:    var(--culiplan-surface-highlight, #FFF7F5);
        --step-done-color:   var(--culiplan-secondary, #16A34A);
        --progress-track:    var(--culiplan-surface-secondary, #F3F4F6);
        --shadow-sm:         var(--culiplan-shadow-sm, 0 1px 3px rgba(0,0,0,0.08));
        --motion-spring:     var(--culiplan-motion-spring, cubic-bezier(0.34,1.56,0.64,1));
        --space-xs:          var(--culiplan-space-1, 0.25rem);
        --space-sm:          var(--culiplan-space-2, 0.5rem);
        --space-md:          var(--culiplan-space-4, 1rem);
        --space-lg:          var(--culiplan-space-6, 1.5rem);
        --font-sm:           var(--culiplan-font-sm, 0.875rem);
        --font-base:         var(--culiplan-font-base, 1rem);
        --font-lg:           var(--culiplan-font-lg, 1.125rem);
        --font-xl:           var(--culiplan-font-xl, 1.25rem);
      }

      ha-card.cooking-card {
        background: var(--card-bg);
        border-radius: var(--card-radius);
        box-shadow: var(--shadow-sm);
        overflow: hidden;
        font-family: var(--culiplan-font-family, system-ui, sans-serif);
        color: var(--text-primary);
      }

      /* ── Loading ───────────────────────────────────────────── */
      .loading {
        padding: var(--space-lg);
        text-align: center;
        color: var(--text-muted);
        font-size: var(--font-sm);
      }

      /* ── Fallback (idle) ──────────────────────────────────── */
      .cooking-card--idle {
        border: 2px dashed var(--primary);
        opacity: 0.85;
      }

      .card-header {
        display: flex;
        align-items: center;
        gap: var(--space-md);
        padding: var(--space-md);
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
        color: #fff;
        cursor: pointer;
        user-select: none;
      }

      .header-icon {
        width: 2rem;
        height: 2rem;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .header-icon svg {
        width: 100%;
        height: 100%;
      }

      .header-image {
        width: 4rem;
        height: 4rem;
        border-radius: var(--culiplan-radius-lg, 0.75rem);
        object-fit: cover;
        flex-shrink: 0;
        border: 2px solid rgba(255,255,255,0.3);
      }

      .header-image-placeholder {
        width: 4rem;
        height: 4rem;
        border-radius: var(--culiplan-radius-lg, 0.75rem);
        background: rgba(255,255,255,0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .header-image-placeholder svg {
        width: 2rem;
        height: 2rem;
        color: rgba(255,255,255,0.8);
      }

      .header-meta {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
      }

      .header-title {
        font-size: var(--font-xl);
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: 1.2;
        letter-spacing: -0.01em;
      }

      .header-subtitle {
        font-size: var(--font-sm);
        opacity: 0.85;
      }

      .pause-btn {
        width: 2.5rem;
        height: 2.5rem;
        border: 2px solid rgba(255,255,255,0.4);
        border-radius: 50%;
        background: rgba(255,255,255,0.15);
        color: #fff;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: background 0.15s ease;
        padding: 0;
      }

      .pause-btn:hover:not(:disabled) {
        background: rgba(255,255,255,0.3);
      }

      .pause-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }

      .pause-btn svg {
        width: 1rem;
        height: 1rem;
      }

      .pause-btn--paused {
        background: rgba(255,255,255,0.3);
        border-color: rgba(255,255,255,0.7);
      }

      /* ── Progress bar ─────────────────────────────────────── */
      .progress-bar-track {
        height: 4px;
        background: var(--progress-track);
        overflow: hidden;
      }

      .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
        transition: width 0.6s var(--motion-spring);
      }

      .progress-label {
        display: flex;
        justify-content: space-between;
        padding: var(--space-xs) var(--space-md);
        font-size: 0.75rem;
        color: var(--text-muted);
      }

      /* ── Timers ───────────────────────────────────────────── */
      .timers-section {
        margin: 0 var(--space-md);
        padding: var(--space-md);
        background: #FFF8F5;
        border-radius: var(--culiplan-radius-lg, 0.75rem);
        border: 1px solid rgba(242,103,68,0.15);
        margin-bottom: var(--space-sm);
      }

      .timers-heading {
        display: flex;
        align-items: center;
        gap: var(--space-sm);
        font-size: var(--font-sm);
        font-weight: 600;
        color: var(--primary);
        margin-bottom: var(--space-sm);
      }

      .timers-heading svg {
        width: 1rem;
        height: 1rem;
      }

      .timer-row {
        display: flex;
        align-items: center;
        gap: var(--space-sm);
        margin-bottom: var(--space-sm);
      }

      .timer-row:last-child {
        margin-bottom: 0;
      }

      .timer-label {
        flex: 1;
        font-size: var(--font-sm);
        color: var(--text-secondary);
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .timer-countdown {
        font-size: var(--font-lg);
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: var(--primary);
        width: 4.5rem;
        text-align: right;
        flex-shrink: 0;
      }

      .timer-countdown--expired {
        color: var(--secondary);
      }

      .timer-bar-track {
        width: 5rem;
        height: 4px;
        background: rgba(242,103,68,0.15);
        border-radius: 2px;
        overflow: hidden;
        flex-shrink: 0;
      }

      .timer-bar-fill {
        height: 100%;
        background: var(--primary);
        transition: width 1s linear;
        border-radius: 2px;
      }

      .timer-bar-fill--expired {
        background: var(--secondary);
      }

      .timer-row--expired .timer-label {
        opacity: 0.6;
      }

      /* ── Step list ────────────────────────────────────────── */
      .steps-list {
        padding: var(--space-sm) 0;
        max-height: 22rem;
        overflow-y: auto;
        scrollbar-width: thin;
        scrollbar-color: var(--border) transparent;
      }

      .step-row {
        display: flex;
        align-items: flex-start;
        gap: var(--space-md);
        padding: var(--space-sm) var(--space-md);
        cursor: pointer;
        border-left: 3px solid transparent;
        transition: background 0.15s ease, border-color 0.15s ease;
      }

      .step-row:hover {
        background: var(--step-active-bg);
      }

      .step-row--active {
        background: var(--step-active-bg);
        border-left-color: var(--primary);
      }

      .step-row--done {
        opacity: 0.55;
      }

      .step-indicator {
        width: 1.75rem;
        height: 1.75rem;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        background: var(--progress-track);
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--text-muted);
      }

      .step-row--active .step-indicator {
        background: var(--primary);
        color: #fff;
      }

      .step-row--done .step-indicator {
        background: var(--secondary);
        color: #fff;
      }

      .step-check svg,
      .step-number {
        display: block;
        width: 0.875rem;
        height: 0.875rem;
      }

      .step-check svg {
        stroke: #fff;
      }

      .step-text {
        flex: 1;
        font-size: var(--font-base);
        line-height: 1.5;
        color: var(--text-primary);
        padding-top: 0.125rem;
      }

      .step-row--active .step-text {
        font-weight: 600;
      }

      .step-current-marker {
        width: 1.25rem;
        flex-shrink: 0;
        color: var(--primary);
        display: flex;
        align-items: center;
        padding-top: 0.2rem;
      }

      .step-current-marker svg {
        width: 1rem;
        height: 1rem;
      }

      .no-steps {
        padding: var(--space-md);
        font-size: var(--font-sm);
        color: var(--text-muted);
        text-align: center;
      }

      /* ── Footer ───────────────────────────────────────────── */
      .card-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--space-md);
        border-top: 1px solid var(--border);
        gap: var(--space-md);
      }

      .card-footer--done {
        background: #f0fdf4;
        color: var(--secondary);
        font-weight: 600;
        justify-content: center;
        gap: var(--space-sm);
      }

      .card-footer--done svg {
        width: 1.25rem;
        height: 1.25rem;
      }

      .next-btn {
        display: flex;
        align-items: center;
        gap: var(--space-sm);
        padding: 0.625rem var(--space-lg);
        border: none;
        border-radius: var(--culiplan-radius-xl, 1rem);
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
        color: #fff;
        font-size: var(--font-base);
        font-weight: 600;
        cursor: pointer;
        transition: opacity 0.15s ease, transform 0.1s var(--motion-spring);
        white-space: nowrap;
      }

      .next-btn:hover:not(:disabled) {
        opacity: 0.9;
        transform: scale(1.02);
      }

      .next-btn:active:not(:disabled) {
        transform: scale(0.98);
      }

      .next-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
        transform: none;
      }

      .next-btn--loading {
        opacity: 0.7;
      }

      .next-btn svg {
        width: 1rem;
        height: 1rem;
      }

      .voice-hint {
        display: flex;
        align-items: center;
        gap: var(--space-xs);
        font-size: 0.75rem;
        color: var(--text-muted);
      }

      .voice-hint svg {
        width: 0.875rem;
        height: 0.875rem;
        flex-shrink: 0;
      }

      /* ── Paused overlay tint ─────────────────────────────── */
      .cooking-card--paused .steps-list {
        opacity: 0.7;
      }

      /* ── Fallback layout ──────────────────────────────────── */
      .fallback-body {
        padding: var(--space-lg);
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--space-md);
        color: var(--text-secondary);
      }

      .fallback-illustration {
        width: 4rem;
        height: 4rem;
        color: var(--primary);
        opacity: 0.5;
      }

      .fallback-illustration svg {
        width: 100%;
        height: 100%;
      }

      .fallback-headline {
        margin: 0;
        font-size: var(--font-lg);
        font-weight: 600;
        color: var(--text-primary);
      }

      .fallback-subtext {
        margin: 0;
        font-size: var(--font-sm);
        max-width: 28ch;
        line-height: 1.5;
      }

      .fallback-hint {
        display: flex;
        align-items: center;
        gap: var(--space-sm);
        font-size: var(--font-sm);
        padding: var(--space-sm) var(--space-md);
        background: var(--step-active-bg);
        border-radius: var(--culiplan-radius-full, 9999px);
        color: var(--primary);
        font-weight: 500;
      }

      .fallback-hint svg {
        width: 1rem;
        height: 1rem;
      }

      /* ── Dark mode ────────────────────────────────────────── */
      @media (prefers-color-scheme: dark) {
        :host {
          --card-bg:          var(--culiplan-surface-default-dark, #1c1c1e);
          --text-primary:     var(--culiplan-text-primary-dark, #f2f2f7);
          --text-secondary:   var(--culiplan-text-secondary-dark, #aeaeb2);
          --text-muted:       var(--culiplan-text-muted-dark, #636366);
          --border:           var(--culiplan-border-subtle-dark, #3a3a3c);
          --step-active-bg:   rgba(242, 103, 68, 0.08);
          --progress-track:   rgba(255,255,255,0.08);
        }

        .timers-section {
          background: rgba(242, 103, 68, 0.06);
          border-color: rgba(242, 103, 68, 0.12);
        }

        .card-footer--done {
          background: rgba(22, 163, 74, 0.1);
        }
      }
    `;
  }
}

// ── Registration ──────────────────────────────────────────────────────────────

if (!customElements.get("culiplan-cooking-mode")) {
  customElements.define("culiplan-cooking-mode", FlavorplanCookingMode);
}
