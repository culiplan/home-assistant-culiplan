/**
 * culiplan-panel.js
 *
 * Custom Lit panel for the Culiplan Home Assistant integration.
 *
 * Why a custom panel instead of the built-in iframe panel:
 *   HA's iframe panel navigates the top-level browser context to the panel
 *   URL, so the Authorization header is never sent — the view returns 401.
 *   This panel runs inside HA's authenticated frontend, fetches the SSO
 *   redirect URL via XHR (with the HA bearer token in the header), then sets
 *   the iframe src to the returned URL.  The code lives in the fragment (#),
 *   so it is never sent to any server after the initial navigation.
 *
 * Panel JS smoke test note:
 *   There is no JS test harness in this repo.  Manual smoke testing covers:
 *   - Happy path: panel renders iframe pointing at culiplan.com/ha-bridge#<code>
 *   - No config entry: error card with "no_entry" message
 *   - Backend down: error card with "exchange_failed" message
 *   - Retry button triggers re-fetch (backend codes are single-use)
 *   - HA design tokens applied in error card (looks native)
 *
 * @license Apache-2.0
 */

import { LitElement, html, css } from "lit";

/**
 * How long (in ms) we consider the fetched code still valid before
 * forcing a re-fetch.  The backend issues 60-second codes; we use 50s
 * to give a comfortable margin for the iframe load.
 */
const CODE_VALID_MS = 50_000;

class CuliplanPanel extends LitElement {
  static properties = {
    hass: { type: Object },
    narrow: { type: Boolean },
    route: { type: Object },
    panel: { type: Object },
    // Internal state
    _state: { type: String },   // "loading" | "ready" | "error"
    _redirectUrl: { type: String },
    _errorCode: { type: String },
    _errorMessage: { type: String },
  };

  static styles = css`
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

    .error-container {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      padding: 24px;
      box-sizing: border-box;
    }

    .error-card {
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
      border-radius: 12px;
      padding: 32px 40px;
      max-width: 480px;
      width: 100%;
      box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12));
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

    .retry-button:hover {
      opacity: 0.85;
    }

    .retry-button:active {
      opacity: 0.7;
    }

    .loading-container {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--secondary-text-color, #727272);
      font-size: 1rem;
      gap: 12px;
    }

    .spinner {
      width: 24px;
      height: 24px;
      border: 3px solid var(--divider-color, #e0e0e0);
      border-top-color: var(--primary-color, #03a9f4);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `;

  constructor() {
    super();
    this._state = "loading";
    this._redirectUrl = "";
    this._errorCode = "";
    this._errorMessage = "";
    /** @type {number | null} Timestamp (Date.now()) when the current code was fetched */
    this._fetchedAt = null;
  }

  firstUpdated() {
    this._launch();
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
    if (this._isCodeFresh()) {
      // Code still within the validity window — reuse it (browser back/fwd).
      return;
    }

    this._state = "loading";
    this._redirectUrl = "";
    this._errorCode = "";
    this._errorMessage = "";

    let token;
    try {
      token = this.hass?.auth?.data?.access_token;
    } catch (_) {
      token = undefined;
    }

    if (!token) {
      this._state = "error";
      this._errorCode = "no_token";
      this._errorMessage =
        "Home Assistant access token not available. Try refreshing the page.";
      return;
    }

    let response;
    try {
      response = await fetch("/api/culiplan/launch", {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (networkErr) {
      this._state = "error";
      this._errorCode = "network_error";
      this._errorMessage =
        "Could not reach the Culiplan integration. Check your internet connection.";
      return;
    }

    let data;
    try {
      data = await response.json();
    } catch (_) {
      data = {};
    }

    if (!response.ok) {
      this._state = "error";
      this._errorCode = data.error ?? `http_${response.status}`;
      this._errorMessage =
        data.message ??
        `Unexpected error from launch endpoint (HTTP ${response.status}).`;
      return;
    }

    const redirectUrl = data.redirect_url;
    if (!redirectUrl || typeof redirectUrl !== "string") {
      this._state = "error";
      this._errorCode = "bad_response";
      this._errorMessage =
        "Culiplan returned an unexpected response. Please try again.";
      return;
    }

    this._redirectUrl = redirectUrl;
    this._fetchedAt = Date.now();
    this._state = "ready";
  }

  _onIframeError() {
    // The iframe itself failed to load (CSP block, network partition, etc.).
    // Invalidate the code so retry issues a fresh one.
    this._fetchedAt = null;
    this._state = "error";
    this._errorCode = "iframe_load_error";
    this._errorMessage =
      "The Culiplan page could not load inside Home Assistant. " +
      "This may be a content security policy issue or a temporary outage.";
  }

  _retry() {
    // Always re-fetch: backend codes are single-use.
    this._fetchedAt = null;
    this._launch();
  }

  render() {
    if (this._state === "loading") {
      return html`
        <div class="loading-container">
          <div class="spinner"></div>
          <span>Connecting to Culiplan…</span>
        </div>
      `;
    }

    if (this._state === "error") {
      return html`
        <div class="error-container">
          <div class="error-card">
            <div class="error-icon">⚠️</div>
            <p class="error-title">Could not open Culiplan</p>
            <p class="error-message">${this._errorMessage}</p>
            <button class="retry-button" @click=${this._retry}>
              Try again
            </button>
          </div>
        </div>
      `;
    }

    // state === "ready"
    return html`
      <iframe
        class="fill"
        src=${this._redirectUrl}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        @error=${this._onIframeError}
        title="Culiplan"
      ></iframe>
    `;
  }
}

customElements.define("culiplan-panel", CuliplanPanel);
