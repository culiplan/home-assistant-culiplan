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

// lovelace/cards/kitchen-dashboard.ts
var MEAL_TYPE_LABELS = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack"
};
var ICON_CHEF_HAT = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>`;
var ICON_CLOCK = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
var ICON_USERS = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
var ICON_SHOPPING = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>`;
var ICON_CALENDAR = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;
var ICON_ARROW_RIGHT = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
var FlavorplanKitchenDashboard = class extends s4 {
  constructor() {
    super(...arguments);
    // HA card lifecycle properties
    __publicField(this, "_config", {});
    __publicField(this, "_hass", null);
  }
  static get properties() {
    return {
      _config: { type: Object },
      _hass: { type: Object }
    };
  }
  // Called by HA with the YAML config block
  setConfig(config) {
    this._config = {
      entity: "calendar.culiplan_meal_plan",
      shopping_entity: "todo.culiplan_shopping_list",
      title: "What's for Dinner?",
      show_shopping: true,
      max_meals: 3,
      ...config
    };
  }
  // Called by HA on state updates
  set hass(hass) {
    this._hass = hass;
    this.requestUpdate();
  }
  // Required by HA to determine card height in the dashboard grid
  getCardSize() {
    return 4;
  }
  // ── Data extraction ──────────────────────────────────────────────────────
  _getMeals() {
    if (!this._hass || !this._config.entity) return [];
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) return [];
    const raw = stateObj.attributes?.today_meals;
    if (!raw) return [];
    try {
      const meals = typeof raw === "string" ? JSON.parse(raw) : raw;
      return meals.slice(0, this._config.max_meals ?? 3);
    } catch {
      return [];
    }
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
  // ── Event handlers ────────────────────────────────────────────────────────
  _openShoppingList() {
    const entity = this._config.shopping_entity;
    if (!entity || !this._hass) return;
    this._hass.callService("frontend", "navigate", {
      path: `/lovelace/shopping`
    });
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId: entity },
      bubbles: true,
      composed: true
    });
    this.dispatchEvent(event);
  }
  _openMealDetail(meal) {
    if (!this._hass) return;
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId: this._config.entity },
      bubbles: true,
      composed: true
    });
    this.dispatchEvent(event);
  }
  // ── Render helpers ────────────────────────────────────────────────────────
  _renderMealCard(meal) {
    const time = this._getTotalTime(meal);
    const mealLabel = MEAL_TYPE_LABELS[meal.mealType ?? ""] ?? "";
    const hasImage = !!meal.imageUrl;
    const cdnBase = "https://cdn.culiplan.com";
    const imgSrc = meal.imageUrl?.startsWith("http") ? meal.imageUrl : `${cdnBase}/${meal.imageUrl}`;
    return x`
      <article
        class="meal-card"
        @click=${() => this._openMealDetail(meal)}
        role="button"
        tabindex="0"
        @keydown=${(e4) => e4.key === "Enter" && this._openMealDetail(meal)}
        aria-label="View details for ${meal.title}"
      >
        <div class="meal-image-wrapper">
          ${hasImage ? x`<img
                class="meal-image"
                src="${imgSrc}"
                alt="${meal.title}"
                loading="lazy"
              />` : x`<div class="meal-image-placeholder">
                <span class="placeholder-icon">${ICON_CHEF_HAT}</span>
              </div>`}
          ${mealLabel ? x`<span class="meal-type-badge">${mealLabel}</span>` : ""}
        </div>
        <div class="meal-info">
          <h3 class="meal-title">${meal.title}</h3>
          <div class="meal-meta">
            ${meal.servings ? x`<span class="meta-item">
                  <span class="meta-icon">${ICON_USERS}</span>
                  ${meal.servings}
                </span>` : ""}
            ${time ? x`<span class="meta-item">
                  <span class="meta-icon">${ICON_CLOCK}</span>
                  ${time}
                </span>` : ""}
          </div>
        </div>
        <div class="meal-arrow" aria-hidden="true">${ICON_ARROW_RIGHT}</div>
      </article>
    `;
  }
  _renderEmptyState() {
    return x`
      <div class="empty-state">
        <div class="empty-icon">${ICON_CALENDAR}</div>
        <p class="empty-title">No meals planned today</p>
        <p class="empty-subtitle">Open Flavorplan to add meals to your plan.</p>
      </div>
    `;
  }
  _renderShoppingShortcut() {
    if (!this._config.show_shopping) return "";
    const count = this._getShoppingCount();
    return x`
      <button
        class="shopping-shortcut"
        @click=${this._openShoppingList}
        aria-label="Open shopping list${count > 0 ? ` \u2014 ${count} items` : ""}"
      >
        <span class="shopping-icon">${ICON_SHOPPING}</span>
        <span class="shopping-label">Shopping list</span>
        ${count > 0 ? x`<span class="shopping-badge">${count}</span>` : ""}
        <span class="shopping-arrow">${ICON_ARROW_RIGHT}</span>
      </button>
    `;
  }
  // ── Main render ───────────────────────────────────────────────────────────
  render() {
    const meals = this._getMeals();
    const title = this._config.title ?? "What's for Dinner?";
    const isLoading = !this._hass;
    if (isLoading) {
      return x`
        <ha-card>
          <div class="card-content loading">
            <div class="skeleton-header"></div>
            <div class="skeleton-card"></div>
            <div class="skeleton-card"></div>
          </div>
        </ha-card>
      `;
    }
    return x`
      <ha-card>
        <div class="card-header">
          <span class="header-icon">${ICON_CHEF_HAT}</span>
          <h2 class="header-title">${title}</h2>
        </div>
        <div class="card-content">
          <div class="meals-section">
            ${meals.length > 0 ? meals.map((m2) => this._renderMealCard(m2)) : this._renderEmptyState()}
          </div>
          ${this._renderShoppingShortcut()}
        </div>
      </ha-card>
    `;
  }
  // ── Styles ────────────────────────────────────────────────────────────────
  static get styles() {
    return i`
      /* ── Host ─────────────────────────────────────────────────── */
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
        background: var(--culiplan-gradient-hero,
          linear-gradient(135deg, #f26744 0%, #f58566 50%, #ffb89a 100%));
        color: var(--culiplan-white, #fff);
      }

      .header-icon {
        width: 24px;
        height: 24px;
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
        font-size: var(--culiplan-text-lg, 18px);
        font-weight: var(--culiplan-font-semibold, 600);
        line-height: var(--culiplan-leading-tight, 1.25);
        color: inherit;
      }

      /* ── Card content ─────────────────────────────────────────── */
      .card-content {
        padding: var(--culiplan-space-3, 12px);
        display: flex;
        flex-direction: column;
        gap: var(--culiplan-space-2, 8px);
      }

      /* ── Meals section ────────────────────────────────────────── */
      .meals-section {
        display: flex;
        flex-direction: column;
        gap: var(--culiplan-space-2, 8px);
      }

      /* ── Meal card ────────────────────────────────────────────── */
      .meal-card {
        display: flex;
        align-items: center;
        gap: var(--culiplan-space-3, 12px);
        padding: var(--culiplan-space-2, 8px) var(--culiplan-space-3, 12px);
        background: var(--culiplan-surface, #fff);
        border: 1px solid var(--culiplan-border, #e5e7eb);
        border-radius: var(--culiplan-radius-lg, 8px);
        cursor: pointer;
        transition: var(--culiplan-transition-fast,
          all 150ms cubic-bezier(0,0,0.2,1));
        text-decoration: none;
      }

      .meal-card:hover {
        background: var(--culiplan-surface-hover, #f9fafb);
        border-color: var(--culiplan-primary, #f26744);
        box-shadow: var(--culiplan-shadow-soft,
          0 1px 3px 0 rgba(0,0,0,0.06));
        transform: translateY(-1px);
      }

      .meal-card:focus-visible {
        outline: 2px solid var(--culiplan-primary, #f26744);
        outline-offset: 2px;
      }

      /* ── Meal image ───────────────────────────────────────────── */
      .meal-image-wrapper {
        position: relative;
        flex-shrink: 0;
        width: 64px;
        height: 64px;
        border-radius: var(--culiplan-radius-md, 6px);
        overflow: hidden;
        background: var(--culiplan-muted, #f3f4f6);
      }

      .meal-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .meal-image-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--culiplan-gradient-subtle,
          linear-gradient(180deg, #fffbf7 0%, #faf8f5 100%));
      }

      .placeholder-icon {
        width: 28px;
        height: 28px;
        color: var(--culiplan-primary, #f26744);
        opacity: 0.6;
        display: flex;
        align-items: center;
      }

      .placeholder-icon svg {
        width: 100%;
        height: 100%;
      }

      .meal-type-badge {
        position: absolute;
        bottom: 4px;
        left: 4px;
        font-size: var(--culiplan-text-xs, 12px);
        font-weight: var(--culiplan-font-medium, 500);
        color: var(--culiplan-white, #fff);
        background: rgba(0, 0, 0, 0.55);
        padding: 1px 5px;
        border-radius: var(--culiplan-radius-full, 9999px);
        line-height: 1.4;
        white-space: nowrap;
      }

      /* ── Meal info ────────────────────────────────────────────── */
      .meal-info {
        flex: 1;
        min-width: 0;
      }

      .meal-title {
        margin: 0 0 4px;
        font-size: var(--culiplan-text-sm, 14px);
        font-weight: var(--culiplan-font-semibold, 600);
        color: var(--culiplan-text-primary, #1c1917);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: var(--culiplan-leading-tight, 1.25);
      }

      .meal-meta {
        display: flex;
        align-items: center;
        gap: var(--culiplan-space-3, 12px);
        flex-wrap: wrap;
      }

      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: var(--culiplan-text-xs, 12px);
        color: var(--culiplan-text-secondary, #6b7280);
      }

      .meta-icon {
        width: 14px;
        height: 14px;
        display: flex;
        align-items: center;
        flex-shrink: 0;
      }

      .meta-icon svg {
        width: 100%;
        height: 100%;
      }

      .meal-arrow {
        width: 16px;
        height: 16px;
        color: var(--culiplan-text-muted, #9ca3af);
        flex-shrink: 0;
        display: flex;
        align-items: center;
      }

      .meal-arrow svg {
        width: 100%;
        height: 100%;
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
        width: 48px;
        height: 48px;
        color: var(--culiplan-primary, #f26744);
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

      /* ── Shopping shortcut ────────────────────────────────────── */
      .shopping-shortcut {
        display: flex;
        align-items: center;
        gap: var(--culiplan-space-2, 8px);
        width: 100%;
        padding: var(--culiplan-space-2-5, 10px) var(--culiplan-space-3, 12px);
        background: var(--culiplan-secondary, #16A34A);
        color: var(--culiplan-white, #fff);
        border: none;
        border-radius: var(--culiplan-radius-lg, 8px);
        cursor: pointer;
        font-family: inherit;
        font-size: var(--culiplan-text-sm, 14px);
        font-weight: var(--culiplan-font-semibold, 600);
        transition: var(--culiplan-transition-fast,
          all 150ms cubic-bezier(0,0,0.2,1));
        text-align: left;
      }

      .shopping-shortcut:hover {
        background: var(--culiplan-secondary-dark, #15803d);
        transform: translateY(-1px);
        box-shadow: var(--culiplan-shadow-medium,
          0 4px 6px -1px rgba(0,0,0,0.07));
      }

      .shopping-shortcut:focus-visible {
        outline: 2px solid var(--culiplan-secondary, #16A34A);
        outline-offset: 2px;
      }

      .shopping-icon {
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
      }

      .shopping-icon svg {
        width: 100%;
        height: 100%;
      }

      .shopping-label {
        flex: 1;
      }

      .shopping-badge {
        background: rgba(255, 255, 255, 0.25);
        font-size: var(--culiplan-text-xs, 12px);
        font-weight: var(--culiplan-font-bold, 700);
        padding: 1px 7px;
        border-radius: var(--culiplan-radius-full, 9999px);
        min-width: 20px;
        text-align: center;
      }

      .shopping-arrow {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
      }

      .shopping-arrow svg {
        width: 100%;
        height: 100%;
      }

      /* ── Loading skeletons ────────────────────────────────────── */
      .loading {
        gap: var(--culiplan-space-2, 8px);
      }

      @keyframes skeleton-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
      }

      .skeleton-header,
      .skeleton-card {
        background: var(--culiplan-muted, #f3f4f6);
        border-radius: var(--culiplan-radius-md, 6px);
        animation: skeleton-pulse 1.8s ease-in-out infinite;
      }

      .skeleton-header {
        height: 28px;
        width: 50%;
      }

      .skeleton-card {
        height: 80px;
      }

      /* ── Responsive — phone (< 400 px card width) ─────────────── */
      @container (max-width: 400px) {
        .meal-image-wrapper {
          width: 52px;
          height: 52px;
        }

        .meal-title {
          font-size: var(--culiplan-text-xs, 12px);
        }
      }
    `;
  }
};
customElements.define("culiplan-kitchen-dashboard", FlavorplanKitchenDashboard);
window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "culiplan-kitchen-dashboard",
  name: "Culiplan Kitchen Dashboard",
  description: "Today's meal plan with shopping list shortcut. Part of the Culiplan integration card pack.",
  preview: true,
  documentationURL: "https://github.com/culiplan/home-assistant-culiplan/tree/main/lovelace"
});
