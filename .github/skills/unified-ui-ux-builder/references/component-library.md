# Component Library

Canonical, recurring components found in the **three reference apps only** (see `SKILL.md`
"Survey of the repo"). Prefer reusing one of these patterns (adapted to the target stack) over
inventing a new component — this is what makes a new app feel like it belongs with the reference
apps.

> **Ask, don't assume:** not every app needs every component below (live-status pill, data table,
> resizable panels, chat surface). Confirm with the user which are actually relevant to their use
> case and backend before wiring them in — do not add a component just because it's used in a
> reference app.

## Header

- **Stack A** (`src/components/Layout.tsx`): fixed 60px bar, sidebar trigger + vertical separator +
  dynamic page title on the left, light/dark theme toggle (sun/moon icon button) on the right.
  `className="flex h-[60px] shrink-0 items-center gap-2 justify-between border-b"`.
- **Stack B** (`components/Header/Header.tsx`, `TopPanel/TopPanel.tsx`): a `TopPanel` (screen
  switcher / global nav) above a conditional `HeaderBar` shown only on the main screen.
- **Stack C** (`<header class="topbar">`): title with inline SVG icon, a `system-capability-cards`
  region showing CPU/GPU/NPU device info, and a `header-actions` button group (chat toggle, theme
  toggle) — see `index.html:10-49`.

Always keep: title/brand on the left, a theme toggle that writes the stack's theming mechanism
(`.dark` class for A/B via `next-themes`, `data-theme` attribute for C), and any live/engine status
as a colored dot + label using the stack's own status colors. Status pill and multi-screen nav are
optional — ask the user whether the app needs them.

## Sidebar / navigation

- **Stack A only** (`src/components/Navigation.tsx`): collapsible icon sidebar (`Sidebar
  collapsible="icon"`) with a `SidebarMenu` of `NavLink`s; active item gets
  `"bg-sidebar-accent border-r-3 border-brand-accent"`. Use this for any stack-A app with more than
  one page/route.
- **Stacks B/C** don't use a persistent sidebar — stack B switches full-screen "screens" via local
  React state (`activeScreen`, no router); stack C is single-page. Don't add a sidebar to a B/C app
  unless the user explicitly wants multi-page navigation (in which case, consider recommending
  stack A instead and asking the user if they'd like to switch).

## Cards / panels

- **Stack A** (`src/components/ui/card.tsx`): `Card` / `CardHeader` / `CardTitle` /
  `CardDescription` / `CardAction` / `CardContent` / `CardFooter`. Base: `"bg-card text-card-foreground
  flex flex-col gap-6 border py-6"`; header uses CSS container queries
  (`@container/card-header grid ... has-data-[slot=card-action]:grid-cols-[1fr_auto]`); footer
  detects a top border via `[.border-t]:pt-6`. Scaffold with `npx shadcn@latest add card` then
  reconcile with this exact structure.
- **Stack B**: no shared `Card` primitive — each feature has its own container + dedicated `.css`
  file (`LeftPanel.css`, `RightPanel.css`, etc). The closest shared pattern is `Accordion`
  (`components/common/Accordion.tsx` + `Accordion.css`): flat background `#f8f8f8`, no shadow,
  full-width `1px solid #e6e7e8` separator, blue (`#0071c5`) toggle icon, 16px section title /14px
  body. Use an accordion for collapsible grouped content in this stack; use a plain `<section>` +
  dedicated CSS file for everything else.
- **Stack C**: `.card` — `background: var(--panel); border: 3px solid var(--border); border-radius:
  10px; padding: 8px; box-shadow: var(--shadow);` (`<article class="card">`). Cards nest for
  specialized sections (e.g. a `.system-stats-card` nested inside a form card with
  `background: var(--panel-strong)`).

## Buttons

- **Stack A** (`src/components/ui/button.tsx`): CVA variants `default | destructive | outline |
  secondary | ghost | link`; sizes `default | xs | sm | lg | icon | icon-xs | icon-sm | icon-lg`;
  `data-slot="button"` + `data-variant` + `data-size` attributes; supports `asChild` via Radix
  `Slot.Root`. Scaffold with `npx shadcn@latest add button` then reconcile with this variant/size
  set.
- **Stack B**: plain `<button>`/`.text-button` — `font-size: 12px; font-weight: 500; color:
  var(--color-dark); background: #FFF; border-radius: 4px; border: none; padding: 6px 16px;`. No
  variant system; differentiate primary/secondary/danger with a modifier class per-feature.
- **Stack C**: `.btn` base (`border: 0; border-radius: 6px; padding: 8px 14px;`) + `.btn-primary`
  (`background: var(--accent); color: #fff;`), `.btn-danger` (`background: #dc3545;`),
  `.btn-secondary.btn-sm` for compact secondary actions, `.icon-button` for icon-only actions (uses
  inline SVG, no icon library).

## Forms / inputs

- **Stack A**: shadcn-style `input.tsx`, `select.tsx`, `checkbox.tsx`, `radio-group.tsx`,
  `switch.tsx`, `slider.tsx`, `combobox.tsx`, `label.tsx`, `field.tsx` (Radix primitives + CVA).
  Validation: `react-hook-form` + `@hookform/resolvers` + `zod` schemas (see
  `src/features/pipelines/pipelineSchemas.ts` for the pattern).
- **Stack B**: controlled React state + native `<input>`/`<select>`, no form library. Global input
  styling: `--control-padding: 8px 12px; --control-radius: 4px; --control-border-color: #ccc;
  --control-focus-ring: 0 0 0 2px rgba(0, 123, 255, 0.25);`.
- **Stack C**: `<label class="field"><span class="label">…</span><select class="input">…`
  structure; related controls grouped in a `.field-row`; conditional sections toggled via
  `style="display:none"` + JS (`#detectionSection`, `#alertRulesSection` pattern).

## Tables

- **Stack A**: `@tanstack/react-table` + `src/components/ui/table.tsx` primitives — use for any
  sortable/filterable data grid (see `BenchmarkSuiteRunsTable.tsx`, `ModelsTable.tsx`).
- **Stack B**: no shared table primitive — feature-specific markup (e.g. `FileManager`,
  `Timeline`). Build a plain `<table>` with the stack's existing CSS conventions if a new feature
  needs one.
- **Stack C**: no `<table>` convention at all — lists are rendered as cards/chips/rows (see
  `Chips` below) or a Chart.js canvas. If a new stack-C feature genuinely needs tabular data, a
  plain semantic `<table>` is fine but there's no established styling to match — ask the user.

## Status pill / dot / chip

- **Stack A**: status utilities (`status-info`/`status-success`/`status-error`, see
  `design-tokens.md`) applied as a class, driving `--status-bg`/`--status-border`/`--status-fg`.
- **Stack B**: `.status-dot.success|.warning|.error` — small colored circle + label text (see
  `Services.css`).
- **Stack C**: `.dot` (base, `background: var(--muted)`) + `.dot.active` (green glow) / `.dot.error`
  (red glow); `.chips`/`.chip` for metadata tags — `border-radius: 999px; padding: 4px 8px;
  background: var(--panel-strong);` — created dynamically in JS via a `createChip()` helper
  (`run-card.js`).

## Tooltips

- **Stack A**: Radix `tooltip.tsx` wrapper.
- **Stack C**: pure-CSS pseudo-element tooltip — `.tooltip-btn::after { content:
  attr(data-tooltip); ... opacity: 0; visibility: hidden; }`, shown on hover/focus. No JS tooltip
  library. Reuse this for stack C instead of pulling in a tooltip dependency.

## Toasts / notifications

- **Stack A**: `sonner` (`components/ui/sonner.tsx`, theme-aware via `useTheme`), installed
  globally as `<Toaster position="top-center" richColors />`; app-specific helpers wrap
  `toast.warning(...)` etc. in `src/lib/toast.ts`.
- **Stack B/C**: no toast library — errors surface as inline banners (`.pipeline-error-banner`,
  `#pipelineServerError`) or status text/dots, not floating toasts. Don't introduce a toast
  dependency into these stacks without asking the user first.

## Charts

- **Stack A**: `recharts`.
- **Stack B**: `react-chartjs-2`.
- **Stack C**: vendored `Chart.js` (no CDN, no React wrapper) via a hand-written `ChartManager`
  (`js/utils/charts.js`) that re-themes on light/dark toggle and keeps a rolling window
  (`maxPoints = 60`) of samples — reuse this wrapper pattern (`createConsolidatedChart`,
  `pushStatFrame`, `updateChartColors`) rather than adding a charting dependency to a no-build app.

## Data/state architecture (not just visual, but affects how components are wired)

- **Stack A**: Redux Toolkit + **RTK Query** (generated from OpenAPI, `src/api/api.generated.ts`)
  for server state, plain slices for local UI state, `redux-persist` for the subset that should
  survive reloads (e.g. `uiConfig`), typed hooks (`src/store/hooks.ts`).
- **Stack B**: Redux Toolkit with hand-written slices (`createSlice`, no RTK Query) per domain
  concept (`transcriptSlice`, `summarySlice`, etc.), `axios` for HTTP, typed hooks
  (`src/redux/hooks.ts`).
- **Stack C**: no store — plain JS variables/`Map`s as state, the DOM as the source of rendered
  truth, `localStorage` for persisted settings/theme. Live data arrives via `EventSource` (SSE) for
  metrics/captions, not polling.

## Resizable panels (stack A only)

`src/components/ui/resizable.tsx` wraps `react-resizable-panels` — `ResizablePanelGroup` /
`ResizablePanel` / a draggable `Separator` handle (`w-[0.0625rem]` divider with an enlarged
interaction area and a visible grip icon on hover). Use for any stack-A app that needs a
user-resizable split view (e.g. editor + preview); stacks B/C don't have this capability — use a
fixed-ratio split (see `layout-patterns.md`) instead, or flag it as infeasible and suggest stack A.

## Video / stream preview

- **Stack B**: `video.js` + `@videojs/http-streaming`, `react-player` for simpler playback.
- **Stack C**: native `<video>`/WebRTC (WHEP) elements built dynamically per run, with chips for
  latency/TTFT/TPOT/throughput and an error overlay — see `RunCardComponent` in `run-card.js`.

If a stack has no established convention for something the new app needs, say so explicitly and
ask the user how to proceed rather than silently inventing a pattern.
