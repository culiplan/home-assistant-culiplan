/**
 * Culiplan Lovelace Card — pre-built distribution bundle.
 * Built from lovelace/cards/<source>.ts via esbuild.
 * lit is INLINED — this file has zero runtime external imports.
 *
 * Source-of-truth: see lovelace/cards/<source>.ts in the repo for
 * the un-bundled, type-checked source.
 */

var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __knownSymbol = (name, symbol) => (symbol = Symbol[name]) ? symbol : Symbol.for("Symbol." + name);
var __typeError = (msg) => {
  throw TypeError(msg);
};
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });
var __decoratorStart = (base) => [, , , __create(base?.[__knownSymbol("metadata")] ?? null)];
var __decoratorStrings = ["class", "method", "getter", "setter", "accessor", "field", "value", "get", "set"];
var __expectFn = (fn) => fn !== void 0 && typeof fn !== "function" ? __typeError("Function expected") : fn;
var __decoratorContext = (kind, name, done, metadata, fns) => ({ kind: __decoratorStrings[kind], name, metadata, addInitializer: (fn) => done._ ? __typeError("Already initialized") : fns.push(__expectFn(fn || null)) });
var __decoratorMetadata = (array, target) => __defNormalProp(target, __knownSymbol("metadata"), array[3]);
var __runInitializers = (array, flags, self, value) => {
  for (var i4 = 0, fns = array[flags >> 1], n7 = fns && fns.length; i4 < n7; i4++) flags & 1 ? fns[i4].call(self) : value = fns[i4].call(self, value);
  return value;
};
var __decorateElement = (array, flags, name, decorators, target, extra) => {
  var fn, it, done, ctx, access, k2 = flags & 7, s5 = !!(flags & 8), p2 = !!(flags & 16);
  var j = k2 > 3 ? array.length + 1 : k2 ? s5 ? 1 : 2 : 0, key = __decoratorStrings[k2 + 5];
  var initializers = k2 > 3 && (array[j - 1] = []), extraInitializers = array[j] || (array[j] = []);
  var desc = k2 && (!p2 && !s5 && (target = target.prototype), k2 < 5 && (k2 > 3 || !p2) && __getOwnPropDesc(k2 < 4 ? target : { get [name]() {
    return __privateGet(this, extra);
  }, set [name](x2) {
    return __privateSet(this, extra, x2);
  } }, name));
  k2 ? p2 && k2 < 4 && __name(extra, (k2 > 2 ? "set " : k2 > 1 ? "get " : "") + name) : __name(target, name);
  for (var i4 = decorators.length - 1; i4 >= 0; i4--) {
    ctx = __decoratorContext(k2, name, done = {}, array[3], extraInitializers);
    if (k2) {
      ctx.static = s5, ctx.private = p2, access = ctx.access = { has: p2 ? (x2) => __privateIn(target, x2) : (x2) => name in x2 };
      if (k2 ^ 3) access.get = p2 ? (x2) => (k2 ^ 1 ? __privateGet : __privateMethod)(x2, target, k2 ^ 4 ? extra : desc.get) : (x2) => x2[name];
      if (k2 > 2) access.set = p2 ? (x2, y2) => __privateSet(x2, target, y2, k2 ^ 4 ? extra : desc.set) : (x2, y2) => x2[name] = y2;
    }
    it = (0, decorators[i4])(k2 ? k2 < 4 ? p2 ? extra : desc[key] : k2 > 4 ? void 0 : { get: desc.get, set: desc.set } : target, ctx), done._ = 1;
    if (k2 ^ 4 || it === void 0) __expectFn(it) && (k2 > 4 ? initializers.unshift(it) : k2 ? p2 ? extra = it : desc[key] = it : target = it);
    else if (typeof it !== "object" || it === null) __typeError("Object expected");
    else __expectFn(fn = it.get) && (desc.get = fn), __expectFn(fn = it.set) && (desc.set = fn), __expectFn(fn = it.init) && initializers.unshift(fn);
  }
  return k2 || __decoratorMetadata(array, target), desc && __defProp(target, name, desc), p2 ? k2 ^ 4 ? extra : desc : target;
};
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
var __privateIn = (member, obj) => Object(obj) !== obj ? __typeError('Cannot use the "in" operator on this value') : member.has(obj);
var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);

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
  constructor(t4, e6, n7) {
    if (this._$cssResult$ = true, n7 !== s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t4, this.t = e6;
  }
  get styleSheet() {
    let t4 = this.o;
    const s5 = this.t;
    if (e && void 0 === t4) {
      const e6 = void 0 !== s5 && 1 === s5.length;
      e6 && (t4 = n.get(s5)), void 0 === t4 && ((this.o = t4 = new CSSStyleSheet()).replaceSync(this.cssText), e6 && n.set(s5, t4));
    }
    return t4;
  }
  toString() {
    return this.cssText;
  }
};
var r = (t4) => new o("string" == typeof t4 ? t4 : t4 + "", void 0, s);
var i = (t4, ...e6) => {
  const n7 = 1 === t4.length ? t4[0] : e6.reduce((e7, s5, n8) => e7 + ((t5) => {
    if (true === t5._$cssResult$) return t5.cssText;
    if ("number" == typeof t5) return t5;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + t5 + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s5) + t4[n8 + 1], t4[0]);
  return new o(n7, t4, s);
};
var S = (s5, n7) => {
  e ? s5.adoptedStyleSheets = n7.map((t4) => t4 instanceof CSSStyleSheet ? t4 : t4.styleSheet) : n7.forEach((e6) => {
    const n8 = document.createElement("style"), o6 = t.litNonce;
    void 0 !== o6 && n8.setAttribute("nonce", o6), n8.textContent = e6.cssText, s5.appendChild(n8);
  });
};
var c = e ? (t4) => t4 : (t4) => t4 instanceof CSSStyleSheet ? ((t5) => {
  let e6 = "";
  for (const s5 of t5.cssRules) e6 += s5.cssText;
  return r(e6);
})(t4) : t4;

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
var n2 = { toAttribute(t4, i4) {
  switch (i4) {
    case Boolean:
      t4 = t4 ? h : null;
      break;
    case Object:
    case Array:
      t4 = null == t4 ? t4 : JSON.stringify(t4);
  }
  return t4;
}, fromAttribute(t4, i4) {
  let s5 = t4;
  switch (i4) {
    case Boolean:
      s5 = null !== t4;
      break;
    case Number:
      s5 = null === t4 ? null : Number(t4);
      break;
    case Object:
    case Array:
      try {
        s5 = JSON.parse(t4);
      } catch (t5) {
        s5 = null;
      }
  }
  return s5;
} };
var a = (t4, i4) => i4 !== t4 && (i4 == i4 || t4 == t4);
var l = { attribute: true, type: String, converter: n2, reflect: false, hasChanged: a };
var d = "finalized";
var u = class extends HTMLElement {
  constructor() {
    super(), this._$Ei = /* @__PURE__ */ new Map(), this.isUpdatePending = false, this.hasUpdated = false, this._$El = null, this._$Eu();
  }
  static addInitializer(t4) {
    var i4;
    this.finalize(), (null !== (i4 = this.h) && void 0 !== i4 ? i4 : this.h = []).push(t4);
  }
  static get observedAttributes() {
    this.finalize();
    const t4 = [];
    return this.elementProperties.forEach((i4, s5) => {
      const e6 = this._$Ep(s5, i4);
      void 0 !== e6 && (this._$Ev.set(e6, s5), t4.push(e6));
    }), t4;
  }
  static createProperty(t4, i4 = l) {
    if (i4.state && (i4.attribute = false), this.finalize(), this.elementProperties.set(t4, i4), !i4.noAccessor && !this.prototype.hasOwnProperty(t4)) {
      const s5 = "symbol" == typeof t4 ? Symbol() : "__" + t4, e6 = this.getPropertyDescriptor(t4, s5, i4);
      void 0 !== e6 && Object.defineProperty(this.prototype, t4, e6);
    }
  }
  static getPropertyDescriptor(t4, i4, s5) {
    return { get() {
      return this[i4];
    }, set(e6) {
      const r4 = this[t4];
      this[i4] = e6, this.requestUpdate(t4, r4, s5);
    }, configurable: true, enumerable: true };
  }
  static getPropertyOptions(t4) {
    return this.elementProperties.get(t4) || l;
  }
  static finalize() {
    if (this.hasOwnProperty(d)) return false;
    this[d] = true;
    const t4 = Object.getPrototypeOf(this);
    if (t4.finalize(), void 0 !== t4.h && (this.h = [...t4.h]), this.elementProperties = new Map(t4.elementProperties), this._$Ev = /* @__PURE__ */ new Map(), this.hasOwnProperty("properties")) {
      const t5 = this.properties, i4 = [...Object.getOwnPropertyNames(t5), ...Object.getOwnPropertySymbols(t5)];
      for (const s5 of i4) this.createProperty(s5, t5[s5]);
    }
    return this.elementStyles = this.finalizeStyles(this.styles), true;
  }
  static finalizeStyles(i4) {
    const s5 = [];
    if (Array.isArray(i4)) {
      const e6 = new Set(i4.flat(1 / 0).reverse());
      for (const i5 of e6) s5.unshift(c(i5));
    } else void 0 !== i4 && s5.push(c(i4));
    return s5;
  }
  static _$Ep(t4, i4) {
    const s5 = i4.attribute;
    return false === s5 ? void 0 : "string" == typeof s5 ? s5 : "string" == typeof t4 ? t4.toLowerCase() : void 0;
  }
  _$Eu() {
    var t4;
    this._$E_ = new Promise((t5) => this.enableUpdating = t5), this._$AL = /* @__PURE__ */ new Map(), this._$Eg(), this.requestUpdate(), null === (t4 = this.constructor.h) || void 0 === t4 || t4.forEach((t5) => t5(this));
  }
  addController(t4) {
    var i4, s5;
    (null !== (i4 = this._$ES) && void 0 !== i4 ? i4 : this._$ES = []).push(t4), void 0 !== this.renderRoot && this.isConnected && (null === (s5 = t4.hostConnected) || void 0 === s5 || s5.call(t4));
  }
  removeController(t4) {
    var i4;
    null === (i4 = this._$ES) || void 0 === i4 || i4.splice(this._$ES.indexOf(t4) >>> 0, 1);
  }
  _$Eg() {
    this.constructor.elementProperties.forEach((t4, i4) => {
      this.hasOwnProperty(i4) && (this._$Ei.set(i4, this[i4]), delete this[i4]);
    });
  }
  createRenderRoot() {
    var t4;
    const s5 = null !== (t4 = this.shadowRoot) && void 0 !== t4 ? t4 : this.attachShadow(this.constructor.shadowRootOptions);
    return S(s5, this.constructor.elementStyles), s5;
  }
  connectedCallback() {
    var t4;
    void 0 === this.renderRoot && (this.renderRoot = this.createRenderRoot()), this.enableUpdating(true), null === (t4 = this._$ES) || void 0 === t4 || t4.forEach((t5) => {
      var i4;
      return null === (i4 = t5.hostConnected) || void 0 === i4 ? void 0 : i4.call(t5);
    });
  }
  enableUpdating(t4) {
  }
  disconnectedCallback() {
    var t4;
    null === (t4 = this._$ES) || void 0 === t4 || t4.forEach((t5) => {
      var i4;
      return null === (i4 = t5.hostDisconnected) || void 0 === i4 ? void 0 : i4.call(t5);
    });
  }
  attributeChangedCallback(t4, i4, s5) {
    this._$AK(t4, s5);
  }
  _$EO(t4, i4, s5 = l) {
    var e6;
    const r4 = this.constructor._$Ep(t4, s5);
    if (void 0 !== r4 && true === s5.reflect) {
      const h3 = (void 0 !== (null === (e6 = s5.converter) || void 0 === e6 ? void 0 : e6.toAttribute) ? s5.converter : n2).toAttribute(i4, s5.type);
      this._$El = t4, null == h3 ? this.removeAttribute(r4) : this.setAttribute(r4, h3), this._$El = null;
    }
  }
  _$AK(t4, i4) {
    var s5;
    const e6 = this.constructor, r4 = e6._$Ev.get(t4);
    if (void 0 !== r4 && this._$El !== r4) {
      const t5 = e6.getPropertyOptions(r4), h3 = "function" == typeof t5.converter ? { fromAttribute: t5.converter } : void 0 !== (null === (s5 = t5.converter) || void 0 === s5 ? void 0 : s5.fromAttribute) ? t5.converter : n2;
      this._$El = r4, this[r4] = h3.fromAttribute(i4, t5.type), this._$El = null;
    }
  }
  requestUpdate(t4, i4, s5) {
    let e6 = true;
    void 0 !== t4 && (((s5 = s5 || this.constructor.getPropertyOptions(t4)).hasChanged || a)(this[t4], i4) ? (this._$AL.has(t4) || this._$AL.set(t4, i4), true === s5.reflect && this._$El !== t4 && (void 0 === this._$EC && (this._$EC = /* @__PURE__ */ new Map()), this._$EC.set(t4, s5))) : e6 = false), !this.isUpdatePending && e6 && (this._$E_ = this._$Ej());
  }
  async _$Ej() {
    this.isUpdatePending = true;
    try {
      await this._$E_;
    } catch (t5) {
      Promise.reject(t5);
    }
    const t4 = this.scheduleUpdate();
    return null != t4 && await t4, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    var t4;
    if (!this.isUpdatePending) return;
    this.hasUpdated, this._$Ei && (this._$Ei.forEach((t5, i5) => this[i5] = t5), this._$Ei = void 0);
    let i4 = false;
    const s5 = this._$AL;
    try {
      i4 = this.shouldUpdate(s5), i4 ? (this.willUpdate(s5), null === (t4 = this._$ES) || void 0 === t4 || t4.forEach((t5) => {
        var i5;
        return null === (i5 = t5.hostUpdate) || void 0 === i5 ? void 0 : i5.call(t5);
      }), this.update(s5)) : this._$Ek();
    } catch (t5) {
      throw i4 = false, this._$Ek(), t5;
    }
    i4 && this._$AE(s5);
  }
  willUpdate(t4) {
  }
  _$AE(t4) {
    var i4;
    null === (i4 = this._$ES) || void 0 === i4 || i4.forEach((t5) => {
      var i5;
      return null === (i5 = t5.hostUpdated) || void 0 === i5 ? void 0 : i5.call(t5);
    }), this.hasUpdated || (this.hasUpdated = true, this.firstUpdated(t4)), this.updated(t4);
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
  shouldUpdate(t4) {
    return true;
  }
  update(t4) {
    void 0 !== this._$EC && (this._$EC.forEach((t5, i4) => this._$EO(i4, this[i4], t5)), this._$EC = void 0), this._$Ek();
  }
  updated(t4) {
  }
  firstUpdated(t4) {
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
var e3 = s3 ? s3.createPolicy("lit-html", { createHTML: (t4) => t4 }) : void 0;
var o3 = "$lit$";
var n3 = `lit$${(Math.random() + "").slice(9)}$`;
var l2 = "?" + n3;
var h2 = `<${l2}>`;
var r3 = document;
var u2 = () => r3.createComment("");
var d2 = (t4) => null === t4 || "object" != typeof t4 && "function" != typeof t4;
var c2 = Array.isArray;
var v = (t4) => c2(t4) || "function" == typeof (null == t4 ? void 0 : t4[Symbol.iterator]);
var a2 = "[ 	\n\f\r]";
var f = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;
var _ = /-->/g;
var m = />/g;
var p = RegExp(`>|${a2}(?:([^\\s"'>=/]+)(${a2}*=${a2}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g");
var g = /'/g;
var $ = /"/g;
var y = /^(?:script|style|textarea|title)$/i;
var w = (t4) => (i4, ...s5) => ({ _$litType$: t4, strings: i4, values: s5 });
var x = w(1);
var b = w(2);
var T = Symbol.for("lit-noChange");
var A = Symbol.for("lit-nothing");
var E = /* @__PURE__ */ new WeakMap();
var C = r3.createTreeWalker(r3, 129, null, false);
function P(t4, i4) {
  if (!Array.isArray(t4) || !t4.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return void 0 !== e3 ? e3.createHTML(i4) : i4;
}
var V = (t4, i4) => {
  const s5 = t4.length - 1, e6 = [];
  let l5, r4 = 2 === i4 ? "<svg>" : "", u3 = f;
  for (let i5 = 0; i5 < s5; i5++) {
    const s6 = t4[i5];
    let d3, c3, v2 = -1, a3 = 0;
    for (; a3 < s6.length && (u3.lastIndex = a3, c3 = u3.exec(s6), null !== c3); ) a3 = u3.lastIndex, u3 === f ? "!--" === c3[1] ? u3 = _ : void 0 !== c3[1] ? u3 = m : void 0 !== c3[2] ? (y.test(c3[2]) && (l5 = RegExp("</" + c3[2], "g")), u3 = p) : void 0 !== c3[3] && (u3 = p) : u3 === p ? ">" === c3[0] ? (u3 = null != l5 ? l5 : f, v2 = -1) : void 0 === c3[1] ? v2 = -2 : (v2 = u3.lastIndex - c3[2].length, d3 = c3[1], u3 = void 0 === c3[3] ? p : '"' === c3[3] ? $ : g) : u3 === $ || u3 === g ? u3 = p : u3 === _ || u3 === m ? u3 = f : (u3 = p, l5 = void 0);
    const w2 = u3 === p && t4[i5 + 1].startsWith("/>") ? " " : "";
    r4 += u3 === f ? s6 + h2 : v2 >= 0 ? (e6.push(d3), s6.slice(0, v2) + o3 + s6.slice(v2) + n3 + w2) : s6 + n3 + (-2 === v2 ? (e6.push(void 0), i5) : w2);
  }
  return [P(t4, r4 + (t4[s5] || "<?>") + (2 === i4 ? "</svg>" : "")), e6];
};
var N = class _N {
  constructor({ strings: t4, _$litType$: i4 }, e6) {
    let h3;
    this.parts = [];
    let r4 = 0, d3 = 0;
    const c3 = t4.length - 1, v2 = this.parts, [a3, f2] = V(t4, i4);
    if (this.el = _N.createElement(a3, e6), C.currentNode = this.el.content, 2 === i4) {
      const t5 = this.el.content, i5 = t5.firstChild;
      i5.remove(), t5.append(...i5.childNodes);
    }
    for (; null !== (h3 = C.nextNode()) && v2.length < c3; ) {
      if (1 === h3.nodeType) {
        if (h3.hasAttributes()) {
          const t5 = [];
          for (const i5 of h3.getAttributeNames()) if (i5.endsWith(o3) || i5.startsWith(n3)) {
            const s5 = f2[d3++];
            if (t5.push(i5), void 0 !== s5) {
              const t6 = h3.getAttribute(s5.toLowerCase() + o3).split(n3), i6 = /([.?@])?(.*)/.exec(s5);
              v2.push({ type: 1, index: r4, name: i6[2], strings: t6, ctor: "." === i6[1] ? H : "?" === i6[1] ? L : "@" === i6[1] ? z : k });
            } else v2.push({ type: 6, index: r4 });
          }
          for (const i5 of t5) h3.removeAttribute(i5);
        }
        if (y.test(h3.tagName)) {
          const t5 = h3.textContent.split(n3), i5 = t5.length - 1;
          if (i5 > 0) {
            h3.textContent = s3 ? s3.emptyScript : "";
            for (let s5 = 0; s5 < i5; s5++) h3.append(t5[s5], u2()), C.nextNode(), v2.push({ type: 2, index: ++r4 });
            h3.append(t5[i5], u2());
          }
        }
      } else if (8 === h3.nodeType) if (h3.data === l2) v2.push({ type: 2, index: r4 });
      else {
        let t5 = -1;
        for (; -1 !== (t5 = h3.data.indexOf(n3, t5 + 1)); ) v2.push({ type: 7, index: r4 }), t5 += n3.length - 1;
      }
      r4++;
    }
  }
  static createElement(t4, i4) {
    const s5 = r3.createElement("template");
    return s5.innerHTML = t4, s5;
  }
};
function S2(t4, i4, s5 = t4, e6) {
  var o6, n7, l5, h3;
  if (i4 === T) return i4;
  let r4 = void 0 !== e6 ? null === (o6 = s5._$Co) || void 0 === o6 ? void 0 : o6[e6] : s5._$Cl;
  const u3 = d2(i4) ? void 0 : i4._$litDirective$;
  return (null == r4 ? void 0 : r4.constructor) !== u3 && (null === (n7 = null == r4 ? void 0 : r4._$AO) || void 0 === n7 || n7.call(r4, false), void 0 === u3 ? r4 = void 0 : (r4 = new u3(t4), r4._$AT(t4, s5, e6)), void 0 !== e6 ? (null !== (l5 = (h3 = s5)._$Co) && void 0 !== l5 ? l5 : h3._$Co = [])[e6] = r4 : s5._$Cl = r4), void 0 !== r4 && (i4 = S2(t4, r4._$AS(t4, i4.values), r4, e6)), i4;
}
var M = class {
  constructor(t4, i4) {
    this._$AV = [], this._$AN = void 0, this._$AD = t4, this._$AM = i4;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t4) {
    var i4;
    const { el: { content: s5 }, parts: e6 } = this._$AD, o6 = (null !== (i4 = null == t4 ? void 0 : t4.creationScope) && void 0 !== i4 ? i4 : r3).importNode(s5, true);
    C.currentNode = o6;
    let n7 = C.nextNode(), l5 = 0, h3 = 0, u3 = e6[0];
    for (; void 0 !== u3; ) {
      if (l5 === u3.index) {
        let i5;
        2 === u3.type ? i5 = new R(n7, n7.nextSibling, this, t4) : 1 === u3.type ? i5 = new u3.ctor(n7, u3.name, u3.strings, this, t4) : 6 === u3.type && (i5 = new Z(n7, this, t4)), this._$AV.push(i5), u3 = e6[++h3];
      }
      l5 !== (null == u3 ? void 0 : u3.index) && (n7 = C.nextNode(), l5++);
    }
    return C.currentNode = r3, o6;
  }
  v(t4) {
    let i4 = 0;
    for (const s5 of this._$AV) void 0 !== s5 && (void 0 !== s5.strings ? (s5._$AI(t4, s5, i4), i4 += s5.strings.length - 2) : s5._$AI(t4[i4])), i4++;
  }
};
var R = class _R {
  constructor(t4, i4, s5, e6) {
    var o6;
    this.type = 2, this._$AH = A, this._$AN = void 0, this._$AA = t4, this._$AB = i4, this._$AM = s5, this.options = e6, this._$Cp = null === (o6 = null == e6 ? void 0 : e6.isConnected) || void 0 === o6 || o6;
  }
  get _$AU() {
    var t4, i4;
    return null !== (i4 = null === (t4 = this._$AM) || void 0 === t4 ? void 0 : t4._$AU) && void 0 !== i4 ? i4 : this._$Cp;
  }
  get parentNode() {
    let t4 = this._$AA.parentNode;
    const i4 = this._$AM;
    return void 0 !== i4 && 11 === (null == t4 ? void 0 : t4.nodeType) && (t4 = i4.parentNode), t4;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t4, i4 = this) {
    t4 = S2(this, t4, i4), d2(t4) ? t4 === A || null == t4 || "" === t4 ? (this._$AH !== A && this._$AR(), this._$AH = A) : t4 !== this._$AH && t4 !== T && this._(t4) : void 0 !== t4._$litType$ ? this.g(t4) : void 0 !== t4.nodeType ? this.$(t4) : v(t4) ? this.T(t4) : this._(t4);
  }
  k(t4) {
    return this._$AA.parentNode.insertBefore(t4, this._$AB);
  }
  $(t4) {
    this._$AH !== t4 && (this._$AR(), this._$AH = this.k(t4));
  }
  _(t4) {
    this._$AH !== A && d2(this._$AH) ? this._$AA.nextSibling.data = t4 : this.$(r3.createTextNode(t4)), this._$AH = t4;
  }
  g(t4) {
    var i4;
    const { values: s5, _$litType$: e6 } = t4, o6 = "number" == typeof e6 ? this._$AC(t4) : (void 0 === e6.el && (e6.el = N.createElement(P(e6.h, e6.h[0]), this.options)), e6);
    if ((null === (i4 = this._$AH) || void 0 === i4 ? void 0 : i4._$AD) === o6) this._$AH.v(s5);
    else {
      const t5 = new M(o6, this), i5 = t5.u(this.options);
      t5.v(s5), this.$(i5), this._$AH = t5;
    }
  }
  _$AC(t4) {
    let i4 = E.get(t4.strings);
    return void 0 === i4 && E.set(t4.strings, i4 = new N(t4)), i4;
  }
  T(t4) {
    c2(this._$AH) || (this._$AH = [], this._$AR());
    const i4 = this._$AH;
    let s5, e6 = 0;
    for (const o6 of t4) e6 === i4.length ? i4.push(s5 = new _R(this.k(u2()), this.k(u2()), this, this.options)) : s5 = i4[e6], s5._$AI(o6), e6++;
    e6 < i4.length && (this._$AR(s5 && s5._$AB.nextSibling, e6), i4.length = e6);
  }
  _$AR(t4 = this._$AA.nextSibling, i4) {
    var s5;
    for (null === (s5 = this._$AP) || void 0 === s5 || s5.call(this, false, true, i4); t4 && t4 !== this._$AB; ) {
      const i5 = t4.nextSibling;
      t4.remove(), t4 = i5;
    }
  }
  setConnected(t4) {
    var i4;
    void 0 === this._$AM && (this._$Cp = t4, null === (i4 = this._$AP) || void 0 === i4 || i4.call(this, t4));
  }
};
var k = class {
  constructor(t4, i4, s5, e6, o6) {
    this.type = 1, this._$AH = A, this._$AN = void 0, this.element = t4, this.name = i4, this._$AM = e6, this.options = o6, s5.length > 2 || "" !== s5[0] || "" !== s5[1] ? (this._$AH = Array(s5.length - 1).fill(new String()), this.strings = s5) : this._$AH = A;
  }
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t4, i4 = this, s5, e6) {
    const o6 = this.strings;
    let n7 = false;
    if (void 0 === o6) t4 = S2(this, t4, i4, 0), n7 = !d2(t4) || t4 !== this._$AH && t4 !== T, n7 && (this._$AH = t4);
    else {
      const e7 = t4;
      let l5, h3;
      for (t4 = o6[0], l5 = 0; l5 < o6.length - 1; l5++) h3 = S2(this, e7[s5 + l5], i4, l5), h3 === T && (h3 = this._$AH[l5]), n7 || (n7 = !d2(h3) || h3 !== this._$AH[l5]), h3 === A ? t4 = A : t4 !== A && (t4 += (null != h3 ? h3 : "") + o6[l5 + 1]), this._$AH[l5] = h3;
    }
    n7 && !e6 && this.j(t4);
  }
  j(t4) {
    t4 === A ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, null != t4 ? t4 : "");
  }
};
var H = class extends k {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t4) {
    this.element[this.name] = t4 === A ? void 0 : t4;
  }
};
var I = s3 ? s3.emptyScript : "";
var L = class extends k {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t4) {
    t4 && t4 !== A ? this.element.setAttribute(this.name, I) : this.element.removeAttribute(this.name);
  }
};
var z = class extends k {
  constructor(t4, i4, s5, e6, o6) {
    super(t4, i4, s5, e6, o6), this.type = 5;
  }
  _$AI(t4, i4 = this) {
    var s5;
    if ((t4 = null !== (s5 = S2(this, t4, i4, 0)) && void 0 !== s5 ? s5 : A) === T) return;
    const e6 = this._$AH, o6 = t4 === A && e6 !== A || t4.capture !== e6.capture || t4.once !== e6.once || t4.passive !== e6.passive, n7 = t4 !== A && (e6 === A || o6);
    o6 && this.element.removeEventListener(this.name, this, e6), n7 && this.element.addEventListener(this.name, this, t4), this._$AH = t4;
  }
  handleEvent(t4) {
    var i4, s5;
    "function" == typeof this._$AH ? this._$AH.call(null !== (s5 = null === (i4 = this.options) || void 0 === i4 ? void 0 : i4.host) && void 0 !== s5 ? s5 : this.element, t4) : this._$AH.handleEvent(t4);
  }
};
var Z = class {
  constructor(t4, i4, s5) {
    this.element = t4, this.type = 6, this._$AN = void 0, this._$AM = i4, this.options = s5;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t4) {
    S2(this, t4);
  }
};
var B = i2.litHtmlPolyfillSupport;
null == B || B(N, R), (null !== (t2 = i2.litHtmlVersions) && void 0 !== t2 ? t2 : i2.litHtmlVersions = []).push("2.8.0");
var D = (t4, i4, s5) => {
  var e6, o6;
  const n7 = null !== (e6 = null == s5 ? void 0 : s5.renderBefore) && void 0 !== e6 ? e6 : i4;
  let l5 = n7._$litPart$;
  if (void 0 === l5) {
    const t5 = null !== (o6 = null == s5 ? void 0 : s5.renderBefore) && void 0 !== o6 ? o6 : null;
    n7._$litPart$ = l5 = new R(i4.insertBefore(u2(), t5), t5, void 0, null != s5 ? s5 : {});
  }
  return l5._$AI(t4), l5;
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
    var t4, e6;
    const i4 = super.createRenderRoot();
    return null !== (t4 = (e6 = this.renderOptions).renderBefore) && void 0 !== t4 || (e6.renderBefore = i4.firstChild), i4;
  }
  update(t4) {
    const i4 = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t4), this._$Do = D(i4, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    var t4;
    super.connectedCallback(), null === (t4 = this._$Do) || void 0 === t4 || t4.setConnected(true);
  }
  disconnectedCallback() {
    var t4;
    super.disconnectedCallback(), null === (t4 = this._$Do) || void 0 === t4 || t4.setConnected(false);
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

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/custom-element.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/property.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var i3 = (i4, e6) => "method" === e6.kind && e6.descriptor && !("value" in e6.descriptor) ? { ...e6, finisher(n7) {
  n7.createProperty(e6.key, i4);
} } : { kind: "field", key: Symbol(), placement: "own", descriptor: {}, originalKey: e6.key, initializer() {
  "function" == typeof e6.initializer && (this[e6.key] = e6.initializer.call(this));
}, finisher(n7) {
  n7.createProperty(e6.key, i4);
} };
var e4 = (i4, e6, n7) => {
  e6.constructor.createProperty(n7, i4);
};
function n5(n7) {
  return (t4, o6) => void 0 !== o6 ? e4(n7, t4, o6) : i3(n7, t4);
}

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/state.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
function t3(t4) {
  return n5({ ...t4, state: true });
}

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/base.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/event-options.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/query.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/query-all.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/query-async.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/query-assigned-elements.js
/**
 * @license
 * Copyright 2021 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
var n6;
var e5 = null != (null === (n6 = window.HTMLSlotElement) || void 0 === n6 ? void 0 : n6.prototype.assignedElements) ? (o6, n7) => o6.assignedElements(n7) : (o6, n7) => o6.assignedNodes(n7).filter((o7) => o7.nodeType === Node.ELEMENT_NODE);

// node_modules/.pnpm/@lit+reactive-element@1.6.3/node_modules/@lit/reactive-element/decorators/query-assigned-nodes.js
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */

// lovelace/cards/blueprint-generator.ts
var ICON_WAND = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8 19 13"/><path d="M15 9h0"/><path d="M17.8 6.2 19 5"/><path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/></svg>`;
var ICON_COPY = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
var ICON_INSTALL = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
var ICON_SPINNER = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`;
var ICON_ALERT = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
var ICON_CHECK = x`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
var __installed_dec, __copied_dec, __errorMessage_dec, __result_dec, __cardState_dec, __prompt_dec, __config_dec, _hass_dec, _a, _init;
var FlavorplanBlueprintGeneratorCard = class extends (_a = s4, _hass_dec = [n5({ attribute: false })], __config_dec = [t3()], __prompt_dec = [t3()], __cardState_dec = [t3()], __result_dec = [t3()], __errorMessage_dec = [t3()], __copied_dec = [t3()], __installed_dec = [t3()], _a) {
  constructor() {
    super(...arguments);
    __publicField(this, "hass", __runInitializers(_init, 8, this)), __runInitializers(_init, 11, this);
    __publicField(this, "_config", __runInitializers(_init, 12, this, {})), __runInitializers(_init, 15, this);
    __publicField(this, "_prompt", __runInitializers(_init, 16, this, "")), __runInitializers(_init, 19, this);
    __publicField(this, "_cardState", __runInitializers(_init, 20, this, "idle")), __runInitializers(_init, 23, this);
    __publicField(this, "_result", __runInitializers(_init, 24, this, null)), __runInitializers(_init, 27, this);
    __publicField(this, "_errorMessage", __runInitializers(_init, 28, this, "")), __runInitializers(_init, 31, this);
    __publicField(this, "_copied", __runInitializers(_init, 32, this, false)), __runInitializers(_init, 35, this);
    __publicField(this, "_installed", __runInitializers(_init, 36, this, false)), __runInitializers(_init, 39, this);
    __publicField(this, "_unsubscribeEvent", null);
  }
  setConfig(config) {
    this._config = { show_install: true, ...config };
  }
  connectedCallback() {
    super.connectedCallback();
    this._subscribeToEvents();
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsubscribeEvent) {
      this._unsubscribeEvent();
      this._unsubscribeEvent = null;
    }
  }
  async _subscribeToEvents() {
    if (!this.hass) return;
    try {
      this._unsubscribeEvent = await this.hass.connection.subscribeEvents(
        (event) => this._handleBlueprintEvent(event),
        "culiplan_blueprint_generated"
      );
    } catch {
    }
  }
  _handleBlueprintEvent(event) {
    if (this._cardState !== "loading") return;
    this._result = event.data;
    this._cardState = "result";
    this._installed = !!event.data.installed_path;
  }
  _getAvailableEntities() {
    const ae = this._config.available_entities;
    if (!ae) return void 0;
    if (Array.isArray(ae)) return ae;
    return ae.split(",").map((s5) => s5.trim()).filter(Boolean);
  }
  async _handleGenerate() {
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
    const serviceData = { prompt };
    const entities = this._getAvailableEntities();
    if (entities?.length) serviceData["available_entities"] = entities;
    try {
      await this.hass.callService("culiplan", "generate_blueprint", serviceData);
      setTimeout(() => {
        if (this._cardState === "loading") {
          this._errorMessage = "Blueprint generation timed out. Please try again.";
          this._cardState = "error";
        }
      }, 6e4);
    } catch (err) {
      this._errorMessage = err instanceof Error ? err.message : String(err);
      this._cardState = "error";
    }
  }
  async _handleInstall() {
    if (!this._result?.yaml) return;
    this._cardState = "loading";
    try {
      const serviceData = {
        prompt: this._prompt.trim(),
        install: true
      };
      const entities = this._getAvailableEntities();
      if (entities?.length) serviceData["available_entities"] = entities;
      await this.hass.callService("culiplan", "generate_blueprint", serviceData);
    } catch (err) {
      this._errorMessage = err instanceof Error ? err.message : String(err);
      this._cardState = "error";
    }
  }
  async _handleCopy() {
    if (!this._result?.yaml) return;
    try {
      await navigator.clipboard.writeText(this._result.yaml);
      this._copied = true;
      setTimeout(() => {
        this._copied = false;
      }, 2e3);
    } catch {
    }
  }
  _handleReset() {
    this._cardState = "idle";
    this._result = null;
    this._errorMessage = "";
    this._prompt = "";
  }
  static get styles() {
    return i`
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
    return x`
      <ha-card>
        <div class="header">
          ${ICON_WAND}
          <h3>${title}</h3>
        </div>

        ${this._cardState !== "result" ? x`
          <textarea
            .value=${this._prompt}
            @input=${(e6) => {
      this._prompt = e6.target.value;
    }}
            placeholder="Describe the automation you want — e.g. 'Notify me at 7am with today's meal plan'"
            ?disabled=${this._cardState === "loading"}
          ></textarea>
        ` : ""}

        ${this._cardState === "idle" || this._cardState === "error" ? x`
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

        ${this._cardState === "loading" ? x`
          <div class="loading-row">
            ${ICON_SPINNER}
            Generating blueprint…
          </div>
        ` : ""}

        ${this._cardState === "error" ? x`
          <div class="error-row">
            ${ICON_ALERT}
            <span>${this._errorMessage || "Blueprint generation failed. Please try again."}</span>
          </div>
        ` : ""}

        ${this._cardState === "result" && this._result ? x`
          <div class="result-header">
            ${ICON_CHECK}
            <div class="result-meta">
              <div class="result-name">${this._result.name}</div>
              ${this._result.description ? x`<div class="result-desc">${this._result.description}</div>` : ""}
            </div>
          </div>

          ${this._result.warnings?.length ? x`
            <div class="warnings">
              <strong>Warnings</strong>
              <ul>
                ${this._result.warnings.map((w2) => x`<li>${w2}</li>`)}
              </ul>
            </div>
          ` : ""}

          <div class="yaml-preview">${this._result.yaml}</div>

          <div class="actions">
            ${this._installed ? x`
              <span class="installed-badge">
                ${ICON_CHECK}
                Installed
              </span>
            ` : showInstall && this._result.valid ? x`
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
};
_init = __decoratorStart(_a);
__decorateElement(_init, 5, "hass", _hass_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_config", __config_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_prompt", __prompt_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_cardState", __cardState_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_result", __result_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_errorMessage", __errorMessage_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_copied", __copied_dec, FlavorplanBlueprintGeneratorCard);
__decorateElement(_init, 5, "_installed", __installed_dec, FlavorplanBlueprintGeneratorCard);
__decoratorMetadata(_init, FlavorplanBlueprintGeneratorCard);
customElements.define(
  "flavorplan-blueprint-generator",
  FlavorplanBlueprintGeneratorCard
);
