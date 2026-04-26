/**
 * Culiplan Lovelace Card — pre-built distribution bundle.
 * Built from lovelace/cards/<source>.ts via esbuild.
 * lit is INLINED — this file has zero runtime external imports.
 *
 * Source-of-truth: see lovelace/cards/<source>.ts in the repo for
 * the un-bundled, type-checked source.
 */

var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/css-tag.js
/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var t = window;
var e = t.ShadowRoot && (void 0 === t.ShadyCSS || t.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype;
var s = Symbol();
var n = /* @__PURE__ */ new WeakMap();
var o = class {
  constructor(t3, e4, n5) {
    if (this._$cssResult$ = true, n5 !== s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t3, this.t = e4;
  }
  get styleSheet() {
    let t3 = this.o;
    const s5 = this.t;
    if (e && void 0 === t3) {
      const e4 = void 0 !== s5 && 1 === s5.length;
      e4 && (t3 = n.get(s5)), void 0 === t3 && ((this.o = t3 = new CSSStyleSheet()).replaceSync(this.cssText), e4 && n.set(s5, t3));
    }
    return t3;
  }
  toString() {
    return this.cssText;
  }
};
var r = (t3) => new o("string" == typeof t3 ? t3 : t3 + "", void 0, s);
var i = (t3, ...e4) => {
  const n5 = 1 === t3.length ? t3[0] : e4.reduce((e5, s5, n6) => e5 + ((t4) => {
    if (true === t4._$cssResult$) return t4.cssText;
    if ("number" == typeof t4) return t4;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + t4 + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s5) + t3[n6 + 1], t3[0]);
  return new o(n5, t3, s);
};
var S = (s5, n5) => {
  e ? s5.adoptedStyleSheets = n5.map((t3) => t3 instanceof CSSStyleSheet ? t3 : t3.styleSheet) : n5.forEach((e4) => {
    const n6 = document.createElement("style"), o5 = t.litNonce;
    void 0 !== o5 && n6.setAttribute("nonce", o5), n6.textContent = e4.cssText, s5.appendChild(n6);
  });
};
var c = e ? (t3) => t3 : (t3) => t3 instanceof CSSStyleSheet ? ((t4) => {
  let e4 = "";
  for (const s5 of t4.cssRules) e4 += s5.cssText;
  return r(e4);
})(t3) : t3;

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/reactive-element.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var s2;
var e2 = window;
var r2 = e2.trustedTypes;
var h = r2 ? r2.emptyScript : "";
var o2 = e2.reactiveElementPolyfillSupport;
var n2 = { toAttribute(t3, i3) {
  switch (i3) {
    case Boolean:
      t3 = t3 ? h : null;
      break;
    case Object:
    case Array:
      t3 = null == t3 ? t3 : JSON.stringify(t3);
  }
  return t3;
}, fromAttribute(t3, i3) {
  let s5 = t3;
  switch (i3) {
    case Boolean:
      s5 = null !== t3;
      break;
    case Number:
      s5 = null === t3 ? null : Number(t3);
      break;
    case Object:
    case Array:
      try {
        s5 = JSON.parse(t3);
      } catch (t4) {
        s5 = null;
      }
  }
  return s5;
} };
var a = (t3, i3) => i3 !== t3 && (i3 == i3 || t3 == t3);
var l = { attribute: true, type: String, converter: n2, reflect: false, hasChanged: a };
var d = "finalized";
var u = class extends HTMLElement {
  constructor() {
    super(), this._$Ei = /* @__PURE__ */ new Map(), this.isUpdatePending = false, this.hasUpdated = false, this._$El = null, this._$Eu();
  }
  static addInitializer(t3) {
    var i3;
    this.finalize(), (null !== (i3 = this.h) && void 0 !== i3 ? i3 : this.h = []).push(t3);
  }
  static get observedAttributes() {
    this.finalize();
    const t3 = [];
    return this.elementProperties.forEach((i3, s5) => {
      const e4 = this._$Ep(s5, i3);
      void 0 !== e4 && (this._$Ev.set(e4, s5), t3.push(e4));
    }), t3;
  }
  static createProperty(t3, i3 = l) {
    if (i3.state && (i3.attribute = false), this.finalize(), this.elementProperties.set(t3, i3), !i3.noAccessor && !this.prototype.hasOwnProperty(t3)) {
      const s5 = "symbol" == typeof t3 ? Symbol() : "__" + t3, e4 = this.getPropertyDescriptor(t3, s5, i3);
      void 0 !== e4 && Object.defineProperty(this.prototype, t3, e4);
    }
  }
  static getPropertyDescriptor(t3, i3, s5) {
    return { get() {
      return this[i3];
    }, set(e4) {
      const r4 = this[t3];
      this[i3] = e4, this.requestUpdate(t3, r4, s5);
    }, configurable: true, enumerable: true };
  }
  static getPropertyOptions(t3) {
    return this.elementProperties.get(t3) || l;
  }
  static finalize() {
    if (this.hasOwnProperty(d)) return false;
    this[d] = true;
    const t3 = Object.getPrototypeOf(this);
    if (t3.finalize(), void 0 !== t3.h && (this.h = [...t3.h]), this.elementProperties = new Map(t3.elementProperties), this._$Ev = /* @__PURE__ */ new Map(), this.hasOwnProperty("properties")) {
      const t4 = this.properties, i3 = [...Object.getOwnPropertyNames(t4), ...Object.getOwnPropertySymbols(t4)];
      for (const s5 of i3) this.createProperty(s5, t4[s5]);
    }
    return this.elementStyles = this.finalizeStyles(this.styles), true;
  }
  static finalizeStyles(i3) {
    const s5 = [];
    if (Array.isArray(i3)) {
      const e4 = new Set(i3.flat(1 / 0).reverse());
      for (const i4 of e4) s5.unshift(c(i4));
    } else void 0 !== i3 && s5.push(c(i3));
    return s5;
  }
  static _$Ep(t3, i3) {
    const s5 = i3.attribute;
    return false === s5 ? void 0 : "string" == typeof s5 ? s5 : "string" == typeof t3 ? t3.toLowerCase() : void 0;
  }
  _$Eu() {
    var t3;
    this._$E_ = new Promise((t4) => this.enableUpdating = t4), this._$AL = /* @__PURE__ */ new Map(), this._$Eg(), this.requestUpdate(), null === (t3 = this.constructor.h) || void 0 === t3 || t3.forEach((t4) => t4(this));
  }
  addController(t3) {
    var i3, s5;
    (null !== (i3 = this._$ES) && void 0 !== i3 ? i3 : this._$ES = []).push(t3), void 0 !== this.renderRoot && this.isConnected && (null === (s5 = t3.hostConnected) || void 0 === s5 || s5.call(t3));
  }
  removeController(t3) {
    var i3;
    null === (i3 = this._$ES) || void 0 === i3 || i3.splice(this._$ES.indexOf(t3) >>> 0, 1);
  }
  _$Eg() {
    this.constructor.elementProperties.forEach((t3, i3) => {
      this.hasOwnProperty(i3) && (this._$Ei.set(i3, this[i3]), delete this[i3]);
    });
  }
  createRenderRoot() {
    var t3;
    const s5 = null !== (t3 = this.shadowRoot) && void 0 !== t3 ? t3 : this.attachShadow(this.constructor.shadowRootOptions);
    return S(s5, this.constructor.elementStyles), s5;
  }
  connectedCallback() {
    var t3;
    void 0 === this.renderRoot && (this.renderRoot = this.createRenderRoot()), this.enableUpdating(true), null === (t3 = this._$ES) || void 0 === t3 || t3.forEach((t4) => {
      var i3;
      return null === (i3 = t4.hostConnected) || void 0 === i3 ? void 0 : i3.call(t4);
    });
  }
  enableUpdating(t3) {
  }
  disconnectedCallback() {
    var t3;
    null === (t3 = this._$ES) || void 0 === t3 || t3.forEach((t4) => {
      var i3;
      return null === (i3 = t4.hostDisconnected) || void 0 === i3 ? void 0 : i3.call(t4);
    });
  }
  attributeChangedCallback(t3, i3, s5) {
    this._$AK(t3, s5);
  }
  _$EO(t3, i3, s5 = l) {
    var e4;
    const r4 = this.constructor._$Ep(t3, s5);
    if (void 0 !== r4 && true === s5.reflect) {
      const h3 = (void 0 !== (null === (e4 = s5.converter) || void 0 === e4 ? void 0 : e4.toAttribute) ? s5.converter : n2).toAttribute(i3, s5.type);
      this._$El = t3, null == h3 ? this.removeAttribute(r4) : this.setAttribute(r4, h3), this._$El = null;
    }
  }
  _$AK(t3, i3) {
    var s5;
    const e4 = this.constructor, r4 = e4._$Ev.get(t3);
    if (void 0 !== r4 && this._$El !== r4) {
      const t4 = e4.getPropertyOptions(r4), h3 = "function" == typeof t4.converter ? { fromAttribute: t4.converter } : void 0 !== (null === (s5 = t4.converter) || void 0 === s5 ? void 0 : s5.fromAttribute) ? t4.converter : n2;
      this._$El = r4, this[r4] = h3.fromAttribute(i3, t4.type), this._$El = null;
    }
  }
  requestUpdate(t3, i3, s5) {
    let e4 = true;
    void 0 !== t3 && (((s5 = s5 || this.constructor.getPropertyOptions(t3)).hasChanged || a)(this[t3], i3) ? (this._$AL.has(t3) || this._$AL.set(t3, i3), true === s5.reflect && this._$El !== t3 && (void 0 === this._$EC && (this._$EC = /* @__PURE__ */ new Map()), this._$EC.set(t3, s5))) : e4 = false), !this.isUpdatePending && e4 && (this._$E_ = this._$Ej());
  }
  async _$Ej() {
    this.isUpdatePending = true;
    try {
      await this._$E_;
    } catch (t4) {
      Promise.reject(t4);
    }
    const t3 = this.scheduleUpdate();
    return null != t3 && await t3, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    var t3;
    if (!this.isUpdatePending) return;
    this.hasUpdated, this._$Ei && (this._$Ei.forEach((t4, i4) => this[i4] = t4), this._$Ei = void 0);
    let i3 = false;
    const s5 = this._$AL;
    try {
      i3 = this.shouldUpdate(s5), i3 ? (this.willUpdate(s5), null === (t3 = this._$ES) || void 0 === t3 || t3.forEach((t4) => {
        var i4;
        return null === (i4 = t4.hostUpdate) || void 0 === i4 ? void 0 : i4.call(t4);
      }), this.update(s5)) : this._$Ek();
    } catch (t4) {
      throw i3 = false, this._$Ek(), t4;
    }
    i3 && this._$AE(s5);
  }
  willUpdate(t3) {
  }
  _$AE(t3) {
    var i3;
    null === (i3 = this._$ES) || void 0 === i3 || i3.forEach((t4) => {
      var i4;
      return null === (i4 = t4.hostUpdated) || void 0 === i4 ? void 0 : i4.call(t4);
    }), this.hasUpdated || (this.hasUpdated = true, this.firstUpdated(t3)), this.updated(t3);
  }
  _$Ek() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = false;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$E_;
  }
  shouldUpdate(t3) {
    return true;
  }
  update(t3) {
    void 0 !== this._$EC && (this._$EC.forEach((t4, i3) => this._$EO(i3, this[i3], t4)), this._$EC = void 0), this._$Ek();
  }
  updated(t3) {
  }
  firstUpdated(t3) {
  }
};
u[d] = true, u.elementProperties = /* @__PURE__ */ new Map(), u.elementStyles = [], u.shadowRootOptions = { mode: "open" }, null == o2 || o2({ ReactiveElement: u }), (null !== (s2 = e2.reactiveElementVersions) && void 0 !== s2 ? s2 : e2.reactiveElementVersions = []).push("1.6.3");

// node_modules/.pnpm/lit-html@2.8.0/node_modules/lit-html/lit-html.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var t2;
var i2 = window;
var s3 = i2.trustedTypes;
var e3 = s3 ? s3.createPolicy("lit-html", { createHTML: (t3) => t3 }) : void 0;
var o3 = "$lit$";
var n3 = `lit$${(Math.random() + "").slice(9)}$`;
var l2 = "?" + n3;
var h2 = `<${l2}>`;
var r3 = document;
var u2 = () => r3.createComment("");
var d2 = (t3) => null === t3 || "object" != typeof t3 && "function" != typeof t3;
var c2 = Array.isArray;
var v = (t3) => c2(t3) || "function" == typeof (null == t3 ? void 0 : t3[Symbol.iterator]);
var a2 = "[ 	\n\f\r]";
var f = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;
var _ = /-->/g;
var m = />/g;
var p = RegExp(`>|${a2}(?:([^\\s"'>=/]+)(${a2}*=${a2}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g");
var g = /'/g;
var $ = /"/g;
var y = /^(?:script|style|textarea|title)$/i;
var w = (t3) => (i3, ...s5) => ({ _$litType$: t3, strings: i3, values: s5 });
var x = w(1);
var b = w(2);
var T = Symbol.for("lit-noChange");
var A = Symbol.for("lit-nothing");
var E = /* @__PURE__ */ new WeakMap();
var C = r3.createTreeWalker(r3, 129, null, false);
function P(t3, i3) {
  if (!Array.isArray(t3) || !t3.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return void 0 !== e3 ? e3.createHTML(i3) : i3;
}
var V = (t3, i3) => {
  const s5 = t3.length - 1, e4 = [];
  let l4, r4 = 2 === i3 ? "<svg>" : "", u3 = f;
  for (let i4 = 0; i4 < s5; i4++) {
    const s6 = t3[i4];
    let d3, c3, v2 = -1, a3 = 0;
    for (; a3 < s6.length && (u3.lastIndex = a3, c3 = u3.exec(s6), null !== c3); ) a3 = u3.lastIndex, u3 === f ? "!--" === c3[1] ? u3 = _ : void 0 !== c3[1] ? u3 = m : void 0 !== c3[2] ? (y.test(c3[2]) && (l4 = RegExp("</" + c3[2], "g")), u3 = p) : void 0 !== c3[3] && (u3 = p) : u3 === p ? ">" === c3[0] ? (u3 = null != l4 ? l4 : f, v2 = -1) : void 0 === c3[1] ? v2 = -2 : (v2 = u3.lastIndex - c3[2].length, d3 = c3[1], u3 = void 0 === c3[3] ? p : '"' === c3[3] ? $ : g) : u3 === $ || u3 === g ? u3 = p : u3 === _ || u3 === m ? u3 = f : (u3 = p, l4 = void 0);
    const w2 = u3 === p && t3[i4 + 1].startsWith("/>") ? " " : "";
    r4 += u3 === f ? s6 + h2 : v2 >= 0 ? (e4.push(d3), s6.slice(0, v2) + o3 + s6.slice(v2) + n3 + w2) : s6 + n3 + (-2 === v2 ? (e4.push(void 0), i4) : w2);
  }
  return [P(t3, r4 + (t3[s5] || "<?>") + (2 === i3 ? "</svg>" : "")), e4];
};
var N = class _N {
  constructor({ strings: t3, _$litType$: i3 }, e4) {
    let h3;
    this.parts = [];
    let r4 = 0, d3 = 0;
    const c3 = t3.length - 1, v2 = this.parts, [a3, f2] = V(t3, i3);
    if (this.el = _N.createElement(a3, e4), C.currentNode = this.el.content, 2 === i3) {
      const t4 = this.el.content, i4 = t4.firstChild;
      i4.remove(), t4.append(...i4.childNodes);
    }
    for (; null !== (h3 = C.nextNode()) && v2.length < c3; ) {
      if (1 === h3.nodeType) {
        if (h3.hasAttributes()) {
          const t4 = [];
          for (const i4 of h3.getAttributeNames()) if (i4.endsWith(o3) || i4.startsWith(n3)) {
            const s5 = f2[d3++];
            if (t4.push(i4), void 0 !== s5) {
              const t5 = h3.getAttribute(s5.toLowerCase() + o3).split(n3), i5 = /([.?@])?(.*)/.exec(s5);
              v2.push({ type: 1, index: r4, name: i5[2], strings: t5, ctor: "." === i5[1] ? H : "?" === i5[1] ? L : "@" === i5[1] ? z : k });
            } else v2.push({ type: 6, index: r4 });
          }
          for (const i4 of t4) h3.removeAttribute(i4);
        }
        if (y.test(h3.tagName)) {
          const t4 = h3.textContent.split(n3), i4 = t4.length - 1;
          if (i4 > 0) {
            h3.textContent = s3 ? s3.emptyScript : "";
            for (let s5 = 0; s5 < i4; s5++) h3.append(t4[s5], u2()), C.nextNode(), v2.push({ type: 2, index: ++r4 });
            h3.append(t4[i4], u2());
          }
        }
      } else if (8 === h3.nodeType) if (h3.data === l2) v2.push({ type: 2, index: r4 });
      else {
        let t4 = -1;
        for (; -1 !== (t4 = h3.data.indexOf(n3, t4 + 1)); ) v2.push({ type: 7, index: r4 }), t4 += n3.length - 1;
      }
      r4++;
    }
  }
  static createElement(t3, i3) {
    const s5 = r3.createElement("template");
    return s5.innerHTML = t3, s5;
  }
};
function S2(t3, i3, s5 = t3, e4) {
  var o5, n5, l4, h3;
  if (i3 === T) return i3;
  let r4 = void 0 !== e4 ? null === (o5 = s5._$Co) || void 0 === o5 ? void 0 : o5[e4] : s5._$Cl;
  const u3 = d2(i3) ? void 0 : i3._$litDirective$;
  return (null == r4 ? void 0 : r4.constructor) !== u3 && (null === (n5 = null == r4 ? void 0 : r4._$AO) || void 0 === n5 || n5.call(r4, false), void 0 === u3 ? r4 = void 0 : (r4 = new u3(t3), r4._$AT(t3, s5, e4)), void 0 !== e4 ? (null !== (l4 = (h3 = s5)._$Co) && void 0 !== l4 ? l4 : h3._$Co = [])[e4] = r4 : s5._$Cl = r4), void 0 !== r4 && (i3 = S2(t3, r4._$AS(t3, i3.values), r4, e4)), i3;
}
var M = class {
  constructor(t3, i3) {
    this._$AV = [], this._$AN = void 0, this._$AD = t3, this._$AM = i3;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t3) {
    var i3;
    const { el: { content: s5 }, parts: e4 } = this._$AD, o5 = (null !== (i3 = null == t3 ? void 0 : t3.creationScope) && void 0 !== i3 ? i3 : r3).importNode(s5, true);
    C.currentNode = o5;
    let n5 = C.nextNode(), l4 = 0, h3 = 0, u3 = e4[0];
    for (; void 0 !== u3; ) {
      if (l4 === u3.index) {
        let i4;
        2 === u3.type ? i4 = new R(n5, n5.nextSibling, this, t3) : 1 === u3.type ? i4 = new u3.ctor(n5, u3.name, u3.strings, this, t3) : 6 === u3.type && (i4 = new Z(n5, this, t3)), this._$AV.push(i4), u3 = e4[++h3];
      }
      l4 !== (null == u3 ? void 0 : u3.index) && (n5 = C.nextNode(), l4++);
    }
    return C.currentNode = r3, o5;
  }
  v(t3) {
    let i3 = 0;
    for (const s5 of this._$AV) void 0 !== s5 && (void 0 !== s5.strings ? (s5._$AI(t3, s5, i3), i3 += s5.strings.length - 2) : s5._$AI(t3[i3])), i3++;
  }
};
var R = class _R {
  constructor(t3, i3, s5, e4) {
    var o5;
    this.type = 2, this._$AH = A, this._$AN = void 0, this._$AA = t3, this._$AB = i3, this._$AM = s5, this.options = e4, this._$Cp = null === (o5 = null == e4 ? void 0 : e4.isConnected) || void 0 === o5 || o5;
  }
  get _$AU() {
    var t3, i3;
    return null !== (i3 = null === (t3 = this._$AM) || void 0 === t3 ? void 0 : t3._$AU) && void 0 !== i3 ? i3 : this._$Cp;
  }
  get parentNode() {
    let t3 = this._$AA.parentNode;
    const i3 = this._$AM;
    return void 0 !== i3 && 11 === (null == t3 ? void 0 : t3.nodeType) && (t3 = i3.parentNode), t3;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t3, i3 = this) {
    t3 = S2(this, t3, i3), d2(t3) ? t3 === A || null == t3 || "" === t3 ? (this._$AH !== A && this._$AR(), this._$AH = A) : t3 !== this._$AH && t3 !== T && this._(t3) : void 0 !== t3._$litType$ ? this.g(t3) : void 0 !== t3.nodeType ? this.$(t3) : v(t3) ? this.T(t3) : this._(t3);
  }
  k(t3) {
    return this._$AA.parentNode.insertBefore(t3, this._$AB);
  }
  $(t3) {
    this._$AH !== t3 && (this._$AR(), this._$AH = this.k(t3));
  }
  _(t3) {
    this._$AH !== A && d2(this._$AH) ? this._$AA.nextSibling.data = t3 : this.$(r3.createTextNode(t3)), this._$AH = t3;
  }
  g(t3) {
    var i3;
    const { values: s5, _$litType$: e4 } = t3, o5 = "number" == typeof e4 ? this._$AC(t3) : (void 0 === e4.el && (e4.el = N.createElement(P(e4.h, e4.h[0]), this.options)), e4);
    if ((null === (i3 = this._$AH) || void 0 === i3 ? void 0 : i3._$AD) === o5) this._$AH.v(s5);
    else {
      const t4 = new M(o5, this), i4 = t4.u(this.options);
      t4.v(s5), this.$(i4), this._$AH = t4;
    }
  }
  _$AC(t3) {
    let i3 = E.get(t3.strings);
    return void 0 === i3 && E.set(t3.strings, i3 = new N(t3)), i3;
  }
  T(t3) {
    c2(this._$AH) || (this._$AH = [], this._$AR());
    const i3 = this._$AH;
    let s5, e4 = 0;
    for (const o5 of t3) e4 === i3.length ? i3.push(s5 = new _R(this.k(u2()), this.k(u2()), this, this.options)) : s5 = i3[e4], s5._$AI(o5), e4++;
    e4 < i3.length && (this._$AR(s5 && s5._$AB.nextSibling, e4), i3.length = e4);
  }
  _$AR(t3 = this._$AA.nextSibling, i3) {
    var s5;
    for (null === (s5 = this._$AP) || void 0 === s5 || s5.call(this, false, true, i3); t3 && t3 !== this._$AB; ) {
      const i4 = t3.nextSibling;
      t3.remove(), t3 = i4;
    }
  }
  setConnected(t3) {
    var i3;
    void 0 === this._$AM && (this._$Cp = t3, null === (i3 = this._$AP) || void 0 === i3 || i3.call(this, t3));
  }
};
var k = class {
  constructor(t3, i3, s5, e4, o5) {
    this.type = 1, this._$AH = A, this._$AN = void 0, this.element = t3, this.name = i3, this._$AM = e4, this.options = o5, s5.length > 2 || "" !== s5[0] || "" !== s5[1] ? (this._$AH = Array(s5.length - 1).fill(new String()), this.strings = s5) : this._$AH = A;
  }
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t3, i3 = this, s5, e4) {
    const o5 = this.strings;
    let n5 = false;
    if (void 0 === o5) t3 = S2(this, t3, i3, 0), n5 = !d2(t3) || t3 !== this._$AH && t3 !== T, n5 && (this._$AH = t3);
    else {
      const e5 = t3;
      let l4, h3;
      for (t3 = o5[0], l4 = 0; l4 < o5.length - 1; l4++) h3 = S2(this, e5[s5 + l4], i3, l4), h3 === T && (h3 = this._$AH[l4]), n5 || (n5 = !d2(h3) || h3 !== this._$AH[l4]), h3 === A ? t3 = A : t3 !== A && (t3 += (null != h3 ? h3 : "") + o5[l4 + 1]), this._$AH[l4] = h3;
    }
    n5 && !e4 && this.j(t3);
  }
  j(t3) {
    t3 === A ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, null != t3 ? t3 : "");
  }
};
var H = class extends k {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t3) {
    this.element[this.name] = t3 === A ? void 0 : t3;
  }
};
var I = s3 ? s3.emptyScript : "";
var L = class extends k {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t3) {
    t3 && t3 !== A ? this.element.setAttribute(this.name, I) : this.element.removeAttribute(this.name);
  }
};
var z = class extends k {
  constructor(t3, i3, s5, e4, o5) {
    super(t3, i3, s5, e4, o5), this.type = 5;
  }
  _$AI(t3, i3 = this) {
    var s5;
    if ((t3 = null !== (s5 = S2(this, t3, i3, 0)) && void 0 !== s5 ? s5 : A) === T) return;
    const e4 = this._$AH, o5 = t3 === A && e4 !== A || t3.capture !== e4.capture || t3.once !== e4.once || t3.passive !== e4.passive, n5 = t3 !== A && (e4 === A || o5);
    o5 && this.element.removeEventListener(this.name, this, e4), n5 && this.element.addEventListener(this.name, this, t3), this._$AH = t3;
  }
  handleEvent(t3) {
    var i3, s5;
    "function" == typeof this._$AH ? this._$AH.call(null !== (s5 = null === (i3 = this.options) || void 0 === i3 ? void 0 : i3.host) && void 0 !== s5 ? s5 : this.element, t3) : this._$AH.handleEvent(t3);
  }
};
var Z = class {
  constructor(t3, i3, s5) {
    this.element = t3, this.type = 6, this._$AN = void 0, this._$AM = i3, this.options = s5;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t3) {
    S2(this, t3);
  }
};
var B = i2.litHtmlPolyfillSupport;
null == B || B(N, R), (null !== (t2 = i2.litHtmlVersions) && void 0 !== t2 ? t2 : i2.litHtmlVersions = []).push("2.8.0");
var D = (t3, i3, s5) => {
  var e4, o5;
  const n5 = null !== (e4 = null == s5 ? void 0 : s5.renderBefore) && void 0 !== e4 ? e4 : i3;
  let l4 = n5._$litPart$;
  if (void 0 === l4) {
    const t4 = null !== (o5 = null == s5 ? void 0 : s5.renderBefore) && void 0 !== o5 ? o5 : null;
    n5._$litPart$ = l4 = new R(i3.insertBefore(u2(), t4), t4, void 0, null != s5 ? s5 : {});
  }
  return l4._$AI(t3), l4;
};

// node_modules/.pnpm/lit-element@3.3.3/node_modules/lit-element/lit-element.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var l3;
var o4;
var s4 = class extends u {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    var t3, e4;
    const i3 = super.createRenderRoot();
    return null !== (t3 = (e4 = this.renderOptions).renderBefore) && void 0 !== t3 || (e4.renderBefore = i3.firstChild), i3;
  }
  update(t3) {
    const i3 = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t3), this._$Do = D(i3, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    var t3;
    super.connectedCallback(), null === (t3 = this._$Do) || void 0 === t3 || t3.setConnected(true);
  }
  disconnectedCallback() {
    var t3;
    super.disconnectedCallback(), null === (t3 = this._$Do) || void 0 === t3 || t3.setConnected(false);
  }
  render() {
    return T;
  }
};
s4.finalized = true, s4._$litElement$ = true, null === (l3 = globalThis.litElementHydrateSupport) || void 0 === l3 || l3.call(globalThis, { LitElement: s4 });
var n4 = globalThis.litElementPolyfillSupport;
null == n4 || n4({ LitElement: s4 });
(null !== (o4 = globalThis.litElementVersions) && void 0 !== o4 ? o4 : globalThis.litElementVersions = []).push("3.3.3");

// node_modules/.pnpm/lit-html@2.8.0/node_modules/lit-html/is-server.js
/**
 * @license
 * Copyright 2022 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// lovelace/cards/cooking-mode.ts
var ICON_CHEF_HAT = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>`;
var ICON_PLAY = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
var ICON_PAUSE = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
var ICON_ARROW_RIGHT = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
var ICON_CLOCK = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
var ICON_MIC = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
var ICON_CHECK = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
var ICON_UTENSILS = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>`;
function fmtCountdown(secs) {
  const m2 = Math.floor(secs / 60);
  const s5 = secs % 60;
  return `${m2}:${s5.toString().padStart(2, "0")}`;
}
var FlavorplanCookingMode = class extends s4 {
  constructor() {
    super(...arguments);
    __publicField(this, "_config", {});
    __publicField(this, "_hass", null);
    // State flags
    __publicField(this, "_isAdvancing", false);
    // debounce step advance taps
    __publicField(this, "_isToggling", false);
  }
  // debounce pause/resume taps
  static get properties() {
    return {
      _config: { type: Object },
      _hass: { type: Object },
      _isAdvancing: { type: Boolean },
      _isToggling: { type: Boolean }
    };
  }
  // ── HA lifecycle ──────────────────────────────────────────────────────────
  setConfig(config) {
    this._config = {
      entity: "sensor.culiplan_active_cooking_session",
      title: "Cooking",
      show_step_numbers: true,
      max_timers: 3,
      ...config
    };
  }
  set hass(hass) {
    this._hass = hass;
    this.requestUpdate();
  }
  getCardSize() {
    return 5;
  }
  // ── Data extraction ───────────────────────────────────────────────────────
  _getEntityState() {
    if (!this._hass || !this._config.entity) return null;
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) return null;
    return { state: stateObj.state, attributes: stateObj.attributes || {} };
  }
  _getSession() {
    const entityState = this._getEntityState();
    if (!entityState) return null;
    if (entityState.state === "idle" || !entityState.attributes.session) return null;
    return entityState.attributes.session;
  }
  _getTimerEntityState(entityId) {
    if (!this._hass || !entityId) return null;
    const stateObj = this._hass.states[entityId];
    if (!stateObj) return null;
    return { state: stateObj.state, attributes: stateObj.attributes || {} };
  }
  /** Get remaining seconds from HA timer entity (HA-native countdown) */
  _getHATimerRemaining(haEntityId) {
    const stateObj = this._getTimerEntityState(haEntityId);
    if (!stateObj) return null;
    if (stateObj.state === "active" && stateObj.attributes.finishes_at) {
      const msLeft = new Date(stateObj.attributes.finishes_at).getTime() - Date.now();
      return Math.max(0, Math.floor(msLeft / 1e3));
    }
    if (stateObj.state === "idle") return 0;
    return null;
  }
  // ── Actions ───────────────────────────────────────────────────────────────
  /** Advance to the next step by calling the culiplan.advance_cooking_step service */
  async _advanceStep(session) {
    if (this._isAdvancing) return;
    if (session.currentStep >= session.totalSteps - 1) return;
    this._isAdvancing = true;
    this.requestUpdate();
    try {
      await this._hass.callService("culiplan", "advance_cooking_step", {
        session_id: session.id,
        step: session.currentStep + 1,
        surface: "home-assistant"
      });
    } finally {
      setTimeout(() => {
        this._isAdvancing = false;
        this.requestUpdate();
      }, 1e3);
    }
  }
  /** Jump to a specific step by tapping it in the list */
  async _goToStep(session, stepIndex) {
    if (stepIndex === session.currentStep) return;
    await this._hass.callService("culiplan", "advance_cooking_step", {
      session_id: session.id,
      step: stepIndex,
      surface: "home-assistant"
    });
  }
  /** Toggle pause / resume */
  async _togglePause(session) {
    if (this._isToggling) return;
    this._isToggling = true;
    this.requestUpdate();
    const newStatus = session.status === "active" ? "paused" : "active";
    try {
      await this._hass.callService("culiplan", "update_cooking_session", {
        session_id: session.id,
        status: newStatus,
        surface: "home-assistant"
      });
    } finally {
      setTimeout(() => {
        this._isToggling = false;
        this.requestUpdate();
      }, 500);
    }
  }
  /** Open the recipe entity's more-info panel (navigates to a recipe deep-link) */
  _openRecipe(session) {
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId: `sensor.culiplan_recipe_${session.recipeId}` },
      bubbles: true,
      composed: true
    });
    this.dispatchEvent(event);
  }
  // ── Render ────────────────────────────────────────────────────────────────
  render() {
    if (!this._hass) {
      return x`<ha-card><div class="loading">Loading…</div></ha-card>`;
    }
    const session = this._getSession();
    if (!session) {
      return this._renderFallback();
    }
    return this._renderSession(session);
  }
  /** Graceful fallback when no active session (AC#5) */
  _renderFallback() {
    return x`
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
  _renderSession(session) {
    const entityState = this._getEntityState();
    const attrs = entityState?.attributes ?? {};
    const recipeTitle = attrs.recipe_title ?? `Recipe ${session.recipeId}`;
    const recipeImage = attrs.recipe_image_url;
    const steps = attrs.steps ?? [];
    const isPaused = session.status === "paused";
    const isCompleted = session.status === "completed";
    const maxTimers = this._config.max_timers ?? 3;
    const progressPct = session.totalSteps > 0 ? Math.round(session.currentStep / session.totalSteps * 100) : 0;
    const stepsRemaining = session.totalSteps - session.currentStep;
    return x`
      <ha-card class="cooking-card ${isPaused ? "cooking-card--paused" : ""} ${isCompleted ? "cooking-card--done" : ""}">

        <!-- ── Header ──────────────────────────────────────────── -->
        <div class="card-header" @click=${() => this._openRecipe(session)}>
          ${recipeImage ? x`<img class="header-image" src="${recipeImage}" alt="${recipeTitle}" />` : x`<div class="header-image-placeholder">${ICON_CHEF_HAT}</div>`}
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
            @click=${(e4) => {
      e4.stopPropagation();
      this._togglePause(session);
    }}
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
          ${session.totalSteps > 0 ? Array.from({ length: session.totalSteps }, (_2, i3) => {
      const isActive = i3 === session.currentStep;
      const isDone = i3 < session.currentStep;
      const stepText = steps[i3] ?? `Step ${i3 + 1}`;
      return x`
                  <div
                    class="step-row ${isActive ? "step-row--active" : ""} ${isDone ? "step-row--done" : ""}"
                    @click=${() => this._goToStep(session, i3)}
                    tabindex="${isActive ? -1 : 0}"
                    role="button"
                    aria-label="Go to step ${i3 + 1}"
                  >
                    <div class="step-indicator">
                      ${isDone ? x`<span class="step-check">${ICON_CHECK}</span>` : x`<span class="step-number">${this._config.show_step_numbers ? i3 + 1 : ""}</span>`}
                    </div>
                    <div class="step-text">${stepText}</div>
                    ${isActive ? x`<div class="step-current-marker">${ICON_ARROW_RIGHT}</div>` : ""}
                  </div>
                `;
    }) : x`<p class="no-steps">No step data available. Steps appear here when synced from the app.</p>`}
        </div>

        <!-- ── Footer: Next step / Done ────────────────────────── -->
        ${!isCompleted ? x`
          <div class="card-footer">
            <button
              class="next-btn ${this._isAdvancing ? "next-btn--loading" : ""}"
              @click=${() => this._advanceStep(session)}
              ?disabled=${this._isAdvancing || isPaused || session.currentStep >= session.totalSteps - 1}
            >
              ${session.currentStep >= session.totalSteps - 1 ? x`${ICON_CHECK} <span>All steps done!</span>` : x`<span>Next step</span> ${ICON_ARROW_RIGHT}`}
            </button>
            <div class="voice-hint">
              ${ICON_MIC}
              <span>Say "next step" to advance</span>
            </div>
          </div>
        ` : x`
          <div class="card-footer card-footer--done">
            ${ICON_CHECK}
            <span>Cooking complete — enjoy your meal!</span>
          </div>
        `}

      </ha-card>
    `;
  }
  /** Render the active timers section with HA-native countdown */
  _renderTimers(timers) {
    return x`
      <div class="timers-section">
        <div class="timers-heading">
          ${ICON_CLOCK}
          <span>Active timers</span>
        </div>
        ${timers.map((timer) => {
      const haRemaining = timer.haTimerEntityId ? this._getHATimerRemaining(timer.haTimerEntityId) : null;
      const secsLeft = haRemaining !== null ? haRemaining : timer.remainingSec;
      const progress = timer.durationSec > 0 ? Math.min(100, secsLeft / timer.durationSec * 100) : 0;
      const isExpired = secsLeft <= 0;
      return x`
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
    return i`
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
};
if (!customElements.get("flavorplan-cooking-mode")) {
  customElements.define("flavorplan-cooking-mode", FlavorplanCookingMode);
}
