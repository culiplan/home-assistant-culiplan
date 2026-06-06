/**
 * culiplan-panel.js
 *
 * Custom HA sidebar panel for the Culiplan integration.
 *
 * Why a custom panel instead of the built-in iframe panel:
 *   HA's iframe panel navigates the top-level browser context to the panel
 *   URL, so the Authorization header is never sent — the view returns 401.
 *   This panel runs inside HA's authenticated frontend, fetches the SSO
 *   redirect URL via XHR (with the HA bearer token in the header), then sets
 *   the iframe src to the returned URL. The code lives in the fragment (#),
 *   so it is never sent to any server after the initial navigation.
 *
 * Why vanilla web components rather than Lit:
 *   HA serves panel module URLs straight to the browser as ES modules — there
 *   is no bundler step, so `import { LitElement } from "lit"` (bare specifier)
 *   does not resolve. Rather than vendoring lit (~50KB of third-party JS) or
 *   depending on a CDN, this file uses plain Custom Elements + Shadow DOM.
 *   The component surface (loading / ready / error states with retry) is small
 *   enough that the manual DOM code is shorter than the Lit version would have
 *   been once `lit-all.min.js` is included.
 *
 * Smoke test cases (manual, no test harness):
 *   - Happy path: panel renders iframe pointing at culiplan.com/ha-bridge#<code>
 *   - No config entry: error card with "no_entry" message
 *   - Backend down: error card with "exchange_failed" message
 *   - Retry button triggers re-fetch (backend codes are single-use)
 *   - HA design tokens applied in error card (looks native)
 *
 * @license Apache-2.0
 */

/**
 * How long (in ms) we consider the fetched code still valid before
 * forcing a re-fetch. The backend issues 60-second codes; we use 50s
 * to give a comfortable margin for the iframe load.
 */
const CODE_VALID_MS = 50_000;

/**
 * Origin of the embedded Culiplan web app. The launch endpoint returns a
 * `redirect_url` on this origin (https://culiplan.com/ha-bridge#...), so
 * postMessage must target it explicitly — `"*"` would leak the message to
 * whatever happens to be in the iframe if the URL ever changed.
 */
const CULIPLAN_ORIGIN = "https://culiplan.com";

/**
 * HA design tokens we forward to the embedded app. The web app keeps a
 * matching whitelist so an arbitrary postMessage cannot inject arbitrary
 * CSS variables. Keep this list in sync with `ALLOWED_HA_TOKENS` in
 * `packages/front/src/main.tsx`.
 */
const HA_THEME_TOKEN_NAMES = [
  "--primary-color",
  "--primary-background-color",
  "--secondary-background-color",
  "--card-background-color",
  "--primary-text-color",
  "--secondary-text-color",
  "--divider-color",
  "--text-primary-color",
  "--accent-color",
  "--error-color",
  "--success-color",
  "--warning-color",
];

const STYLES = `
  :host {
    display: block;
    height: 100%;
    width: 100%;
  }
  .fill {
    width: 100%;
    height: 100%;
    border: none;
    display: block;
  }
  .error-container,
  .loading-container {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 24px;
    box-sizing: border-box;
  }
  .loading-container {
    color: var(--secondary-text-color, #727272);
    font-size: 1rem;
    gap: 12px;
  }
  .error-card {
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
    border-radius: 12px;
    padding: 32px 40px;
    max-width: 480px;
    width: 100%;
    box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.12));
    text-align: center;
  }
  .error-icon {
    font-size: 48px;
    margin-bottom: 16px;
  }
  .error-title {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 8px;
    color: var(--primary-text-color, #212121);
  }
  .error-message {
    font-size: 0.95rem;
    color: var(--secondary-text-color, #727272);
    margin: 0 0 24px;
    line-height: 1.5;
  }
  .retry-button {
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .retry-button:hover { opacity: 0.85; }
  .retry-button:active { opacity: 0.7; }
  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--divider-color, #e0e0e0);
    border-top-color: var(--primary-color, #03a9f4);
    border-radius: 50%;
    animation: culiplan-spin 0.8s linear infinite;
  }
  @keyframes culiplan-spin { to { transform: rotate(360deg); } }
`;

class CuliplanPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    // Internal state — re-render is triggered via _render() after each mutation.
    this._state = "loading"; // "loading" | "ready" | "error"
    this._redirectUrl = "";
    this._errorMessage = "";
    /** @type {number | null} Timestamp when the current code was fetched */
    this._fetchedAt = null;

    /** @type {object | null} HA frontend injects this after the element is attached. */
    this._hass = null;
    this._hasLaunched = false;

    /**
     * Reference to the currently-mounted iframe (once `state === "ready"`),
     * and a flag set after its `load` event has fired. The hass setter uses
     * these to forward theme-token updates without re-posting before the
     * iframe is ready to receive them.
     * @type {HTMLIFrameElement | null}
     */
    this._iframe = null;
    this._iframeLoaded = false;

    // Bound once so addEventListener/removeEventListener pair up correctly.
    this._onMessage = this._onMessage.bind(this);
  }

  /**
   * HA's frontend sets the `hass` property on the panel element on every
   * state update. We trigger the first launch as soon as it appears so we
   * can read the access token. We also re-post the theme tokens on every
   * update so a user switching HA themes mid-session sees the embedded app
   * follow along.
   */
  set hass(value) {
    this._hass = value;
    if (!this._hasLaunched) {
      this._hasLaunched = true;
      this._launch();
    }
    if (this._iframe && this._iframeLoaded) {
      this._postThemeTokens(this._iframe);
      this._postIntegrationStatus(this._iframe);
    }
  }
  get hass() {
    return this._hass;
  }

  /**
   * Read HA's design tokens off `document.documentElement` and post them
   * to the embedded Culiplan app. Called on iframe load and on every
   * `hass` state update (cheap — getComputedStyle reads are fast, and the
   * receiving side ignores unknown keys).
   *
   * Wrapped in try/catch because postMessage can throw if the iframe has
   * been torn down between scheduling and firing.
   */
  _postThemeTokens(iframe) {
    try {
      if (!iframe || !iframe.contentWindow) return;
      const styles = getComputedStyle(document.documentElement);
      /** @type {Record<string, string>} */
      const tokens = {};
      for (const name of HA_THEME_TOKEN_NAMES) {
        const value = styles.getPropertyValue(name);
        if (value && value.trim()) {
          tokens[name] = value.trim();
        }
      }
      iframe.contentWindow.postMessage(
        { type: "culiplan.theme", tokens },
        CULIPLAN_ORIGIN,
      );
    } catch (_) {
      // Defensive: never let theme bridging affect the rest of the panel.
    }
  }

  /**
   * Find the HACS-managed `update.*` entity for this integration, if present.
   * HACS exposes one update entity per managed repo; we match by entity_id or
   * its `title`/friendly name containing "culiplan". Returns the HA state
   * object or null (e.g. integration installed manually, or HACS update
   * entities disabled).
   */
  _findUpdateEntity() {
    const states = this._hass && this._hass.states;
    if (!states) return null;
    for (const entityId in states) {
      if (!entityId.startsWith("update.")) continue;
      const st = states[entityId];
      const attrs = (st && st.attributes) || {};
      const title = String(attrs.title || attrs.friendly_name || "").toLowerCase();
      if (entityId.toLowerCase().includes("culiplan") || title.includes("culiplan")) {
        return st;
      }
    }
    return null;
  }

  /**
   * Post the integration's update status into the embedded app so it can show
   * the in-panel nudge / Settings section. Sourced from the HACS update entity
   * (installed/latest versions, whether an update is available). The web app
   * sends `culiplan.haUpdateCommand` messages back (see `_onMessage`).
   */
  _postIntegrationStatus(iframe) {
    try {
      if (!iframe || !iframe.contentWindow) return;
      const st = this._findUpdateEntity();
      let payload;
      if (st) {
        const attrs = st.attributes || {};
        payload = {
          type: "culiplan.haUpdate",
          hasEntity: true,
          entityId: st.entity_id,
          installed: attrs.installed_version || null,
          latest: attrs.latest_version || null,
          updateAvailable: st.state === "on",
          inProgress: !!attrs.in_progress,
          releaseUrl: attrs.release_url || null,
        };
      } else {
        payload = { type: "culiplan.haUpdate", hasEntity: false };
      }
      iframe.contentWindow.postMessage(payload, CULIPLAN_ORIGIN);
    } catch (_) {
      // Defensive: never let status bridging affect the rest of the panel.
    }
  }

  /**
   * Handle commands the embedded app sends back: refresh (force HACS to
   * re-check GitHub), install (download the new version via HACS), restart
   * (apply it). Strictly validated: must come from our iframe at the Culiplan
   * origin, and only the three known actions are honoured.
   */
  _onMessage(event) {
    try {
      if (event.origin !== CULIPLAN_ORIGIN) return;
      const iframe = this._iframe;
      if (!iframe || event.source !== iframe.contentWindow) return;
      const data = event.data;
      if (!data) return;

      // Session re-launch: the embedded app's short-lived access token expired
      // (the iframe holds no refresh token by design). Fetch a fresh one-time
      // launch code and reload the iframe with a new session — instead of the
      // app falling back to the web login, which can't work in an iframe
      // (Google blocks its OAuth pages from being framed).
      if (data.type === "culiplan.haRelaunch") {
        this._fetchedAt = null; // force _isCodeFresh() to return false
        this._launch();
        return;
      }

      if (data.type !== "culiplan.haUpdateCommand") return;
      if (!this._hass || typeof this._hass.callService !== "function") return;

      const entityId = data.entityId;
      const post = (extra) => {
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage(
            { type: "culiplan.haUpdate", ...extra },
            CULIPLAN_ORIGIN,
          );
        }
      };

      switch (data.action) {
        case "refresh":
          if (entityId) {
            this._hass
              .callService("homeassistant", "update_entity", { entity_id: entityId })
              .catch(() => {});
          }
          // Re-post once the refreshed state has had time to propagate.
          setTimeout(() => this._postIntegrationStatus(this._iframe), 4000);
          break;
        case "install":
          if (!entityId) return;
          this._hass
            .callService("update", "install", { entity_id: entityId })
            .then(() => {
              post({ installComplete: true });
              this._postIntegrationStatus(this._iframe);
            })
            .catch((e) => post({ installError: String((e && e.message) || e) }));
          break;
        case "restart":
          this._hass.callService("homeassistant", "restart").catch(() => {});
          break;
      }
    } catch (_) {
      // Never let a stray message break the panel.
    }
  }

  connectedCallback() {
    window.addEventListener("message", this._onMessage);
    this._render();
  }

  disconnectedCallback() {
    window.removeEventListener("message", this._onMessage);
  }

  /**
   * Returns true if we have a redirect URL that has not yet expired.
   * Browser back/forward: if the panel is re-mounted within CODE_VALID_MS of
   * the last fetch, we reuse the existing URL instead of spending another
   * single-use code.
   */
  _isCodeFresh() {
    return (
      this._state === "ready" &&
      this._redirectUrl &&
      this._fetchedAt !== null &&
      Date.now() - this._fetchedAt < CODE_VALID_MS
    );
  }

  async _launch() {
    if (this._isCodeFresh()) return;

    this._state = "loading";
    this._redirectUrl = "";
    this._errorMessage = "";
    this._render();

    // Use hass.callApi() rather than a raw fetch + manual token extraction.
    // It pulls a valid token off the hass object internally and handles
    // refresh across HA versions, so we never have to read the private
    // _hass.auth.data.access_token field (which broke when HA rotated the
    // session today). Path is "culiplan/launch" — callApi auto-prefixes /api/.
    // On non-2xx, callApi throws { status_code, body }.
    if (!this._hass || typeof this._hass.callApi !== "function") {
      this._fail(
        "Home Assistant is not ready yet. Try refreshing the page.",
      );
      return;
    }

    let data;
    try {
      data = await this._hass.callApi("GET", "culiplan/launch");
    } catch (err) {
      this._fetchedAt = null;
      if (err && err.status_code === 401) {
        this._fail(
          "Home Assistant session expired. Refresh the page and try again.",
        );
        return;
      }
      const message =
        err?.body?.message ??
        `Unexpected error from launch endpoint${err?.status_code ? ` (HTTP ${err.status_code})` : ""}.`;
      this._fail(message);
      return;
    }

    const redirectUrl = data?.redirect_url;
    if (!redirectUrl || typeof redirectUrl !== "string") {
      this._fail(
        "Culiplan returned an unexpected response. Please try again.",
      );
      return;
    }

    this._redirectUrl = redirectUrl;
    this._fetchedAt = Date.now();
    this._state = "ready";
    this._render();
  }

  _fail(message) {
    this._state = "error";
    this._errorMessage = message;
    this._render();
  }

  _onIframeError = () => {
    this._fetchedAt = null;
    this._fail(
      "The Culiplan page could not load inside Home Assistant. " +
        "This may be a content security policy issue or a temporary outage.",
    );
  };

  _retry = () => {
    this._fetchedAt = null;
    this._launch();
  };

  _render() {
    const shadow = this.shadowRoot;
    if (!shadow) return;

    // Idempotent first render: inject the stylesheet once, then swap the body.
    if (!shadow.querySelector("style")) {
      const style = document.createElement("style");
      style.textContent = STYLES;
      shadow.appendChild(style);
    }
    let body = shadow.querySelector(".culiplan-body");
    if (!body) {
      body = document.createElement("div");
      body.className = "culiplan-body";
      body.style.height = "100%";
      shadow.appendChild(body);
    }
    body.replaceChildren(this._buildContent());
  }

  _buildContent() {
    // Any non-"ready" state means the iframe is being torn down. Drop the
    // stale ref so the hass setter doesn't try to postMessage into it.
    if (this._state !== "ready") {
      this._iframe = null;
      this._iframeLoaded = false;
    }

    if (this._state === "loading") {
      const wrap = document.createElement("div");
      wrap.className = "loading-container";
      const spinner = document.createElement("div");
      spinner.className = "spinner";
      const label = document.createElement("span");
      label.textContent = "Connecting to Culiplan…";
      wrap.append(spinner, label);
      return wrap;
    }

    if (this._state === "error") {
      const wrap = document.createElement("div");
      wrap.className = "error-container";
      const card = document.createElement("div");
      card.className = "error-card";

      const icon = document.createElement("div");
      icon.className = "error-icon";
      icon.textContent = "⚠️";

      const title = document.createElement("p");
      title.className = "error-title";
      title.textContent = "Could not open Culiplan";

      const msg = document.createElement("p");
      msg.className = "error-message";
      msg.textContent = this._errorMessage;

      const button = document.createElement("button");
      button.className = "retry-button";
      button.textContent = "Try again";
      button.addEventListener("click", this._retry);

      card.append(icon, title, msg, button);
      wrap.append(card);
      return wrap;
    }

    // state === "ready"
    const iframe = document.createElement("iframe");
    iframe.className = "fill";
    iframe.title = "Culiplan";
    iframe.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms allow-popups",
    );
    // Delegate camera permission into the cross-origin iframe so the embedded
    // Culiplan app can call getUserMedia for barcode scanning (kitchen-tablet
    // use case — scan a product to add it to the pantry). HA's *built-in*
    // iframe panel hardcodes allow="fullscreen" and can't do this, but this
    // custom panel owns its iframe, so we grant camera here. On a wall-mounted
    // tablet the app defaults to the front camera (the rear faces the wall).
    iframe.setAttribute("allow", "camera; fullscreen");
    iframe.addEventListener("error", this._onIframeError);
    // Attach the load handler BEFORE setting `src` so we don't miss the
    // load event for fast-cached responses. The handler forwards HA's
    // current theme tokens into the iframe; the hass setter re-posts on
    // every subsequent state update.
    this._iframeLoaded = false;
    iframe.addEventListener("load", () => {
      this._iframeLoaded = true;
      this._postThemeTokens(iframe);
      this._postIntegrationStatus(iframe);
    });
    iframe.src = this._redirectUrl;
    this._iframe = iframe;
    return iframe;
  }
}

customElements.define("culiplan-panel", CuliplanPanel);
