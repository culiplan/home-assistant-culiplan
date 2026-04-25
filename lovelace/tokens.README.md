# Culiplan Design Tokens — Mapping Reference

`tokens.css` is the single design-token source-of-truth for all Lovelace cards
in the Culiplan HACS integration. It extracts values from two authoritative
sources in the Culiplan monorepo and reconciles them into CSS custom properties
that live on `:root` (not Shadow DOM) so Home Assistant users can override them
via `card-mod`.

---

## Source files

| Source | Path in monorepo | Authority |
|--------|-----------------|-----------|
| Mobile theme | `packages/mobile/src/styles/theme.ts` | Primary brand source — brand colours, spacing scale, type ramp, border radius |
| Web/Tablet Tailwind config | `packages/front/tailwind.config.ts` | Shadows, gradients, HSL variable references |

---

## 1. Brand & Semantic Colours

| CSS variable | Mobile source | Hex value | Notes |
|---|---|---|---|
| `--culiplan-primary` | `colors.primary` | `#f26744` | Culiplan Orange — main brand colour |
| `--culiplan-primary-light` | `colors.primaryLight` | `#f58566` | Hover/light state |
| `--culiplan-primary-dark` | `colors.primaryDark` | `#d94d2a` | Press/active state |
| `--culiplan-secondary` | `colors.secondary` | `#16A34A` | Culiplan Green — success/secondary |
| `--culiplan-secondary-light` | `colors.secondaryLight` | `#22C55E` | Hover/light state |
| `--culiplan-secondary-dark` | `colors.secondaryDark` | `#15803D` | Press/active state |
| `--culiplan-error` | `colors.error` | `#EF4444` | Error / destructive |
| `--culiplan-error-dark` | `colors.errorDark` | `#DC2626` | |
| `--culiplan-warning` | `colors.warning` | `#EAB308` | Warning state |
| `--culiplan-warning-dark` | `colors.warningDark` | `#CA8A04` | |
| `--culiplan-info` | `colors.info` | `#3B82F6` | Informational |
| `--culiplan-info-dark` | `colors.infoDark` | `#2563EB` | |
| `--culiplan-success` | `colors.success` | `#22C55E` | Mirrors secondary-light |
| `--culiplan-success-dark` | `colors.successDark` | `#16A34A` | |
| `--culiplan-overlay` | `colors.overlay` | `rgba(0,0,0,0.5)` | Modal backdrop |
| `--culiplan-overlay-light` | `colors.overlayLight` | `rgba(0,0,0,0.3)` | Subtle overlay |

---

## 2. Surface Palette — Light Mode

| CSS variable | Mobile source | Value | Notes |
|---|---|---|---|
| `--culiplan-bg` | `lightColors.background` | `#FAF8F5` | Warm cream page background |
| `--culiplan-bg-subtle` | `lightColors.backgroundSubtle` | `#FFFBF7` | Off-white subtle bg |
| `--culiplan-surface` | `lightColors.card` | `#FFFFFF` | Card/panel surface |
| `--culiplan-surface-hover` | `lightColors.cardHover` | `#F9FAFB` | Card hover state |
| `--culiplan-text-primary` | `lightColors.foreground` | `#1C1917` | Dark brown primary text |
| `--culiplan-text-secondary` | `lightColors.foregroundSecondary` | `#6B7280` | gray500 secondary text |
| `--culiplan-text-muted` | `lightColors.foregroundMuted` | `#9CA3AF` | gray400 muted text |
| `--culiplan-border` | `lightColors.border` | `#E5E7EB` | gray200 borders |
| `--culiplan-border-subtle` | `lightColors.borderSubtle` | `#F3F4F6` | gray100 subtle borders |
| `--culiplan-muted` | `lightColors.muted` | `#F3F4F6` | Muted surface |
| `--culiplan-muted-foreground` | `lightColors.mutedForeground` | `#6B7280` | Text on muted surface |

---

## 3. Surface Palette — Dark Mode

Activated via `@media (prefers-color-scheme: dark)` and `:host-context([data-theme="dark"])`.

| CSS variable | Mobile source | Dark value | Notes |
|---|---|---|---|
| `--culiplan-bg` | `darkColors.background` | `#1A1F2E` | Blue-gray dark background |
| `--culiplan-bg-subtle` | `darkColors.backgroundSubtle` | `#1E2433` | |
| `--culiplan-surface` | `darkColors.card` | `#212838` | Dark card surface |
| `--culiplan-surface-hover` | `darkColors.cardHover` | `#283041` | |
| `--culiplan-text-primary` | `darkColors.foreground` | `#F8FAFC` | Near-white text |
| `--culiplan-text-secondary` | `darkColors.foregroundSecondary` | `#94A3B8` | Lighter gray |
| `--culiplan-text-muted` | `darkColors.foregroundMuted` | `#64748B` | Muted gray |
| `--culiplan-border` | `darkColors.border` | `#334155` | Dark border |
| `--culiplan-border-subtle` | `darkColors.borderSubtle` | `#2D3A4D` | |

---

## 4. Spacing Scale

Source: `packages/mobile/src/styles/theme.ts` → `spacing` export (4 px base, Tailwind-compatible).

| CSS variable | px value | Tailwind equivalent |
|---|---|---|
| `--culiplan-space-1` | 4px | `space-1` |
| `--culiplan-space-2` | 8px | `space-2` |
| `--culiplan-space-3` | 12px | `space-3` |
| `--culiplan-space-4` | 16px | `space-4` |
| `--culiplan-space-5` | 20px | `space-5` |
| `--culiplan-space-6` | 24px | `space-6` |
| `--culiplan-space-8` | 32px | `space-8` |
| `--culiplan-space-10` | 40px | `space-10` |
| `--culiplan-space-12` | 48px | `space-12` |
| `--culiplan-space-16` | 64px | `space-16` |
| `--culiplan-space-xs` | 8px | named alias |
| `--culiplan-space-sm` | 12px | named alias |
| `--culiplan-space-md` | 16px | named alias |
| `--culiplan-space-lg` | 24px | named alias |
| `--culiplan-space-xl` | 32px | named alias |
| `--culiplan-space-2xl` | 48px | named alias |

---

## 5. Typography Ramp

Source: `packages/mobile/src/styles/theme.ts` → `fontSize`, `fontWeight`, `lineHeight` exports.

### Font sizes

| CSS variable | px value | Mobile key |
|---|---|---|
| `--culiplan-text-xs` | 12px | `fontSize.xs` |
| `--culiplan-text-sm` | 14px | `fontSize.sm` |
| `--culiplan-text-base` | 16px | `fontSize.base` |
| `--culiplan-text-lg` | 18px | `fontSize.lg` |
| `--culiplan-text-xl` | 20px | `fontSize.xl` |
| `--culiplan-text-2xl` | 24px | `fontSize['2xl']` |
| `--culiplan-text-3xl` | 30px | `fontSize['3xl']` |
| `--culiplan-text-4xl` | 36px | `fontSize['4xl']` |
| `--culiplan-text-5xl` | 48px | `fontSize['5xl']` |

### Font weights

| CSS variable | value | Mobile key |
|---|---|---|
| `--culiplan-font-normal` | 400 | `fontWeight.normal` |
| `--culiplan-font-medium` | 500 | `fontWeight.medium` |
| `--culiplan-font-semibold` | 600 | `fontWeight.semibold` |
| `--culiplan-font-bold` | 700 | `fontWeight.bold` |

### Line heights

| CSS variable | multiplier | Mobile key |
|---|---|---|
| `--culiplan-leading-tight` | 1.25 | `lineHeight.tight` |
| `--culiplan-leading-normal` | 1.5 | `lineHeight.normal` |
| `--culiplan-leading-relaxed` | 1.625 | `lineHeight.relaxed` |
| `--culiplan-leading-loose` | 2 | `lineHeight.loose` |

---

## 6. Border Radius

Source: `packages/mobile/src/styles/theme.ts` → `borderRadius` export.

| CSS variable | px value | Mobile key |
|---|---|---|
| `--culiplan-radius-none` | 0px | `borderRadius.none` |
| `--culiplan-radius-sm` | 2px | `borderRadius.sm` |
| `--culiplan-radius` | 4px | `borderRadius.default` |
| `--culiplan-radius-md` | 6px | `borderRadius.md` |
| `--culiplan-radius-lg` | 8px | `borderRadius.lg` |
| `--culiplan-radius-xl` | 12px | `borderRadius.xl` |
| `--culiplan-radius-2xl` | 16px | `borderRadius['2xl']` |
| `--culiplan-radius-3xl` | 24px | `borderRadius['3xl']` |
| `--culiplan-radius-full` | 9999px | `borderRadius.full` |

---

## 7. Shadows

Source: `packages/front/tailwind.config.ts` → `boxShadow` extensions, reconciled with mobile
card-level drop-shadow values.

| CSS variable | Description | Tailwind key |
|---|---|---|
| `--culiplan-shadow-soft` | Subtle 1px shadow | `shadow-soft` |
| `--culiplan-shadow-medium` | Medium 4px shadow | `shadow-medium` |
| `--culiplan-shadow-strong` | Strong 10px shadow | `shadow-strong` |
| `--culiplan-shadow-card` | Orange-tinted brand shadow | custom |

---

## 8. Gradients

Source: `packages/front/tailwind.config.ts` → `backgroundImage` extensions.

| CSS variable | Direction | Tailwind key |
|---|---|---|
| `--culiplan-gradient-hero` | 135deg orange ramp | `gradient-hero` |
| `--culiplan-gradient-subtle` | 180deg warm-cream ramp | `gradient-subtle` |
| `--culiplan-gradient-card` | 145deg white card | `gradient-card` |
| `--culiplan-gradient-green` | 135deg green ramp | custom |

---

## 9. Motion

Source: HA conventions + mobile animation usage patterns.

| CSS variable | value | Usage |
|---|---|---|
| `--culiplan-motion-fast` | 150ms | Hover state transitions |
| `--culiplan-motion-normal` | 250ms | Panel/card transitions |
| `--culiplan-motion-slow` | 350ms | Page-level transitions |
| `--culiplan-motion-ease-out` | `cubic-bezier(0,0,0.2,1)` | Standard enter |
| `--culiplan-motion-ease-in-out` | `cubic-bezier(0.4,0,0.2,1)` | Standard exit |
| `--culiplan-motion-spring` | `cubic-bezier(0.34,1.56,0.64,1)` | Bouncy emphasis |

---

## Overriding via card-mod

Install [card-mod](https://github.com/thomasloven/lovelace-card-mod) and add a
`card_mod` section to any card that uses Culiplan tokens:

```yaml
card_mod:
  style: |
    :root {
      --culiplan-primary: #e05a30;       /* darker orange */
      --culiplan-secondary: #0d7a36;     /* deeper green */
      --culiplan-radius-xl: 20px;        /* rounder cards */
    }
```

Variables on `:root` cascade into all Culiplan Shadow DOM elements automatically.

---

## Divergence notes

| Issue | Resolution |
|---|---|
| `tailwind.config.ts` references HSL variables (`hsl(var(--primary))`) without fixed values | Resolved to mobile hex values; tailwind HSL indirection is a build-time construct, not compatible with HA runtime CSS |
| Mobile `borderRadius.sm = 2` but tailwind `borderRadius.sm = calc(var(--radius) - 4px)` (relative) | Used mobile absolute values as ground truth |
| Tailwind shadows are named `shadow-soft/medium/strong` but values are unset in the config (mapped at build time) | Defined reasonable values matching HA card shadow conventions |
