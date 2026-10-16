<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Component Library

Canonical components, organized **by stack**. Read only your target stack's section — don't
cross-reference other stacks.

Rules:
- Reuse a pattern below (adapted to the target stack) instead of inventing a new component.
- Not every app needs every component. Confirm relevance with the user before wiring one in —
  don't add a component just because it's listed here.
- If a stack has no entry/convention for something the app needs, say so explicitly and ask the
  user how to proceed — don't silently invent one.

---

## Stack A — React + Redux Toolkit + Tailwind v4 + Radix (shadcn-style)

Reference: `visual-pipeline-and-platform-evaluation-tool/ui`

### Header
- `src/components/Layout.tsx`, fixed 60px bar.
- Left: sidebar trigger + vertical separator + dynamic page title.
- Right: light/dark theme toggle (sun/moon icon button).
- Class: `flex h-[60px] shrink-0 items-center gap-2 justify-between border-b`.
- Status pill (optional) in the header: colored dot + label, using this stack's status colors.
- Theme toggle writes `.dark` class via `next-themes`.

### Sidebar / Navigation
- `src/components/Navigation.tsx`.
- Collapsible icon sidebar: `Sidebar collapsible="icon"` wrapping a `SidebarMenu` of `NavLink`s.
- Active item: `bg-sidebar-accent border-r-3 border-brand-accent`.
- Use for any app with more than one page/route. Don't add for a single-page app.

### Cards / Panels
- `src/components/ui/card.tsx`.
- Parts: `Card` / `CardHeader` / `CardTitle` / `CardDescription` / `CardAction` / `CardContent` /
  `CardFooter`.
- Base class: `bg-card text-card-foreground flex flex-col gap-6 border py-6`.
- Header uses CSS container queries: `@container/card-header grid ... has-data-[slot=card-action]:grid-cols-[1fr_auto]`.
- Footer detects a top border via `[.border-t]:pt-6`.
- Scaffold: `npx shadcn@latest add card`, then reconcile with this exact structure.

### Buttons
- `src/components/ui/button.tsx`.
- Variants (CVA): `default | destructive | outline | secondary | ghost | link`.
- Sizes: `default | xs | sm | lg | icon | icon-xs | icon-sm | icon-lg`.
- Attributes: `data-slot="button"` + `data-variant` + `data-size`.
- Supports `asChild` via Radix `Slot.Root`.
- Scaffold: `npx shadcn@latest add button`, then reconcile with this variant/size set.

### Forms / Inputs
- Primitives: `input.tsx`, `select.tsx`, `checkbox.tsx`, `radio-group.tsx`, `switch.tsx`,
  `slider.tsx`, `combobox.tsx`, `label.tsx`, `field.tsx` (Radix primitives + CVA).
- Validation: `react-hook-form` + `@hookform/resolvers` + `zod` schemas.
- Pattern reference: `src/features/pipelines/pipelineSchemas.ts`.

### Tables
- `@tanstack/react-table` + `src/components/ui/table.tsx` primitives.
- Use for any sortable/filterable data grid.
- Reference instances: `BenchmarkSuiteRunsTable.tsx`, `ModelsTable.tsx`.

### Status pill / dot / chip
- Status utilities: `status-info` / `status-success` / `status-error` classes (see
  `design-tokens.md`), driving `--status-bg` / `--status-border` / `--status-fg`.

### Tooltips
- Radix `tooltip.tsx` wrapper.

### Toasts / notifications
- `sonner` library (`components/ui/sonner.tsx`), theme-aware via `useTheme`.
- Install globally: `<Toaster position="top-center" richColors />`.
- App-specific helpers wrap `toast.warning(...)` etc. in `src/lib/toast.ts`.

### Charts
- `recharts`.

### Resizable panels
- `src/components/ui/resizable.tsx` wraps `react-resizable-panels`.
- Parts: `ResizablePanelGroup` / `ResizablePanel` / a draggable `Separator` handle
  (`w-[0.0625rem]` divider, enlarged interaction area, grip icon on hover).
- Use for any user-resizable split view (e.g. editor + preview).
- Stacks B/C don't have this capability — use a fixed-ratio split instead, or recommend stack A.

### Data / state architecture
- Redux Toolkit + **RTK Query** (generated from OpenAPI, `src/api/api.generated.ts`) for server
  state.
- Plain slices for local UI state.
- `redux-persist` for the subset that should survive reloads (e.g. `uiConfig`).
- Typed hooks: `src/store/hooks.ts`.

---

## Stack B — React + Redux Toolkit + plain CSS (no UI kit)

Reference: `education-ai-suite/smart-classroom/ui`

### Header
- `components/TopPanel/TopPanel.tsx` (+ `assets/css/TopPanel.css`) and, on the main screen only,
  `components/Header/HeaderBar.tsx`-equivalent (+ `assets/css/HeaderBar.css`).
- `TopPanel`: always shown, **solid blue bar** — `background-color: var(--color-theme)` (not a
  light/white surface), `height: 64px`, white text/logo (`color: var(--color-light)`). Carries the
  brand/logo, screen switcher / global nav, and the theme toggle. Don't default this to a white
  background — that's the single most common drift seen when building from this stack (see
  `UploadSection.css`'s `.content-search-btn` for how secondary controls look sitting on top of it:
  transparent background, `1.5px solid rgba(255, 255, 255, 0.7)` border, white text, hover fills
  `rgba(255, 255, 255, 0.15)`).
- `HeaderBar`: conditional, shown only on the main screen. White background (`#fff`), not blue —
  this is the one that carries the outlined `.text-button` (see Buttons below).
- Theme toggle writes the stack's own theming mechanism (same light/dark convention as stack A,
  via plain CSS not `next-themes`). Since it sits on `TopPanel`'s blue bar, style it on-accent
  (transparent + light border/text), not with its default light-surface look.

### Sidebar / Navigation
- **None.** No persistent sidebar in this stack.
- Navigation is screen-state driven: local React state `activeScreen` (no router), full-screen
  "screens" replace the body rather than navigating to a new route.
- Don't add a sidebar unless the user explicitly wants multi-page navigation — in that case,
  recommend stack A instead and ask if they'd like to switch.

### Cards / Panels
- No shared `Card` primitive. Each feature has its own container + dedicated `.css` file
  (`LeftPanel.css`, `RightPanel.css`, etc.).
- Closest shared pattern: `Accordion` (`components/common/Accordion.tsx` + `Accordion.css`).
  - Flat background `#f8f8f8`, no shadow.
  - Full-width `1px solid #e6e7e8` separator.
  - Blue (`#0071c5`) toggle icon.
  - 16px section title / 14px body.
  - Use for collapsible grouped content.
- Everything else: plain `<section>` + dedicated CSS file.

### Buttons
Three looks coexist in the real app — pick the one matching the action's role, don't invent a
fourth:
- **Plain/neutral** (default, e.g. a basic action button): `font-size: 12px; font-weight: 500;
  color: var(--color-dark); background: var(--color-light); border-radius: 4px; border: none;
  padding: 6px 16px;`. The real reference app has no dark theme, so its source literally hardcodes
  `background: #FFF` — **don't copy that literally**: this skill's own dark-theme addition (see
  "No documented dark-theme palette" below) inverts `--color-dark`/`--color-light` together, so a
  hardcoded `#FFF` paired with `var(--color-dark)` text becomes invisible (light-on-white) once
  dark mode is toggled. Always pair theme-dependent text (`--color-dark`) with the matching
  theme-dependent surface (`--color-light`), never a literal hex, for any button/surface in this
  stack. Confirmed as a real regression in a migrated app's Copy button.
- **Solid primary** (the main call-to-action, e.g. `.cs-browse-btn`): `background: #0071c5;
  color: #fff; border: none; border-radius: 4px; padding: 6px 18px; font-size: 12px;`, hover
  darkens to `#005fa3`.
- **Outlined secondary** (`.text-button`, lives in `HeaderBar.css`): `color: #0071c5; background:
  none; border: 2px solid #82b6df; border-radius: 4px; padding: 8px 16px; font-size: 14px;
  font-weight: 500;`.
- No variant system/prop — differentiate via a modifier class per feature, matching whichever of
  the three looks above fits the action's importance.

### Forms / Inputs
- Controlled React state + native `<input>`/`<select>`. No form library.
- Global input styling:
  - `--control-padding: 8px 12px;`
  - `--control-radius: 4px;`
  - `--control-border-color: #ccc;`
  - `--control-focus-ring: 0 0 0 2px rgba(0, 123, 255, 0.25);`
- **File upload / dropzone** (`.cs-dropzone`, `UploadSection.css`): `border: 2px dashed #b0bec5;
  border-radius: 8px; background: #f5f8fa;`. On hover/focus: `border-color: #0071c5; background:
  #eaf3fb;`. While a file is actively being dragged over it (`.cs-dropzone--active`):
  `border-color: #0071c5; background: #daeeff;`. Icon and any inline "Browse" button inside it use
  the accent (`#0071c5`), matching the solid-primary button look above.

### Tables
- No shared table primitive — feature-specific markup (e.g. `FileManager`, `Timeline`).
- Build a plain `<table>` with the stack's existing CSS conventions if a new feature needs one.

### Status pill / dot / chip
- `.status-dot.success|.warning|.error` — small colored circle + label text.
- Reference: `Services.css`.

### Tooltips
- No tooltip pattern established in this stack. Ask the user before adding a dependency or
  hand-rolling one.

### Toasts / notifications
- No toast library. Errors surface as inline banners (`.pipeline-error-banner`,
  `#pipelineServerError`) or status text/dots.
- Don't introduce a toast dependency without asking the user first.

### Charts
- `react-chartjs-2`.

### Video / stream preview
- `video.js` + `@videojs/http-streaming` for streaming.
- `react-player` for simpler playback.

### Data / state architecture
- Redux Toolkit with hand-written slices (`createSlice`, no RTK Query), one per domain concept
  (`transcriptSlice`, `summarySlice`, etc.).
- `axios` for HTTP.
- Typed hooks: `src/redux/hooks.ts`.
- i18n (optional): `i18next` + `react-i18next`, `src/i18n/{en,zh}.json`. Add only if the new app
  genuinely needs multi-language — ask the user.

---

## Stack C — Vanilla JS, no build step

Reference: `live-video-analysis/live-video-captioning`

### Header
- `<header class="topbar">`.
- Title with inline SVG icon.
- `system-capability-cards` region: CPU/GPU/NPU device info.
- `header-actions` button group: chat toggle, theme toggle.
- Reference: `index.html:10-49`.
- Theme toggle writes `data-theme` attribute (not a `.dark` class).

### Sidebar / Navigation
- **None.** Stack C is single-page.
- If the app needs multi-page navigation, recommend stack A instead and ask if they'd like to
  switch.

### Cards / Panels
- `.card` — `background: var(--panel); border: 3px solid var(--border); border-radius: 10px;
  padding: 8px; box-shadow: var(--shadow);`.
- Markup: `<article class="card">`.
- Cards nest for specialized sections, e.g. `.system-stats-card` nested inside a form card with
  `background: var(--panel-strong)`.

### Buttons
- `.btn` base: `border: 0; border-radius: 6px; padding: 8px 14px;`
- `.btn-primary`: `background: var(--accent); color: #fff;`
- `.btn-danger`: `background: #dc3545;`
- `.btn-secondary.btn-sm`: compact secondary actions.
- `.icon-button`: icon-only actions, inline SVG (no icon library).

### Forms / Inputs
- Structure: `<label class="field"><span class="label">…</span><select class="input">…`.
- Related controls grouped in a `.field-row`.
- Conditional sections: toggled via `style="display:none"` + JS
  (e.g. `#detectionSection`, `#alertRulesSection`).

### Tables
- No `<table>` convention. Lists render as cards/chips/rows, or a Chart.js canvas.
- If a feature genuinely needs tabular data, a plain semantic `<table>` is fine, but there's no
  established styling to match — ask the user.

### Status pill / dot / chip
- `.dot` base: `background: var(--muted)`.
- `.dot.active`: green glow. `.dot.error`: red glow.
- `.chips` / `.chip`: metadata tags — `border-radius: 999px; padding: 4px 8px;
  background: var(--panel-strong);`.
- Created dynamically in JS via a `createChip()` helper (`run-card.js`).

### Tooltips
- Pure-CSS pseudo-element tooltip: `.tooltip-btn::after { content: attr(data-tooltip); ...
  opacity: 0; visibility: hidden; }`, shown on hover/focus.
- No JS tooltip library — reuse this pattern instead of adding a dependency.

### Toasts / notifications
- No toast library. Errors surface as inline banners or status text/dots.
- Don't introduce a toast dependency without asking the user first.

### Charts
- Vendored `Chart.js` (no CDN, no React wrapper), via a hand-written `ChartManager`
  (`js/utils/charts.js`).
- Re-themes on light/dark toggle; keeps a rolling window (`maxPoints = 60`) of samples.
- Reuse this wrapper's functions (`createConsolidatedChart`, `pushStatFrame`,
  `updateChartColors`) instead of adding a charting dependency.

### Video / stream preview
- Native `<video>` / WebRTC (WHEP) elements, built dynamically per run.
- Chips for latency/TTFT/TPOT/throughput + an error overlay.
- Reference: `RunCardComponent` in `run-card.js`.

### Data / state architecture
- No store. Plain JS variables/`Map`s as state; the DOM is the source of rendered truth.
- `localStorage` for persisted settings/theme.
- Live data via `EventSource` (SSE) for metrics/captions — not polling.
