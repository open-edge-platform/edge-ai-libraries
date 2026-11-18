<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Stack Selection & Scaffolding

- Three curated reference stacks only — chosen for UI/UX quality, not surveyed from every app in
  the repo. **Never assume or default to one.**
- Goal: a uniform look/feel across the repo. This skill intentionally supports **only** these
  three stacks — not any other, and never mixes stacks within one app.
- Existing apps are not exempt:
  - Auto-detect the stack first. If it matches one of the three, continue in it — don't ask.
  - If it doesn't match any of the three (e.g. Vue, Gradio, Jinja templates):
    1. Tell the user: detected stack, and that this skill only builds/updates UI on the three
       reference stacks.
    2. Ask for consent to migrate to one of the three (same options as "Choosing a stack" below).
       Never offer "keep the current non-reference stack" as a path forward.
    3. If the user declines migration: explain the skill's scope/intent (uniform repo UI from three
       curated stacks), then say the task is out of scope, and stop — make no UI/UX changes.
- Brand-new app → the agent MUST ask the user to choose a stack (see below) before scaffolding
  anything.

> **Ask, don't assume (beyond stack choice):** once the stack is settled, still confirm anything
> not implied by the backend or an existing convention — e.g. client-side routing/multiple pages
> (stack A only), i18n (stack B, via `i18next`), light-only vs. dark-only vs. toggle, and which
> port/base path it should run on.

| # | Stack | Reference app | Typical fit |
|---|---|---|---|
| **A** | **React + Redux Toolkit + Tailwind v4 + Radix-primitive (shadcn-style) components** | `edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool/ui` | Full-featured, multi-page product UI needing the richest component set fastest (tables, forms, resizable panels, charts, a flow/graph editor). |
| **B** | **React + Redux Toolkit + plain CSS, custom components (no UI kit)** | `edge-ai-suites/education-ai-suite/smart-classroom/ui` | Full control over every component's markup/CSS without a UI-kit dependency, or needs i18n; single-shell, screen-state-driven (no router) apps. |
| **C** | **Vanilla JS (IIFE modules), no build step** | `edge-ai-suites/metro-ai-suite/live-video-analysis/live-video-captioning` | Lightweight app served directly by a Python backend (FastAPI/Flask), no Node build pipeline wanted; operational/video dashboards with SSE/WebRTC live data. |

All three share: a thin API/services layer wrapping HTTP calls, a light/dark theme toggle driven by
CSS custom properties, and SPDX headers on every file.

## Stack resolution order

1. **UI already exists?** → read `package.json`/`requirements.txt` + source tree.
   - Matches one of the three → continue in it, don't ask.
   - Matches none → flag the mismatch, ask for consent to migrate (see above). Decline → explain
     scope/intent, then stop with no UI/UX changes. Never introduce a second stack into one app.
2. **Brand-new app?** → present the three options below via `ask_user`. Wait for the answer before
   scaffolding anything.
3. **User said "not sure, you pick"** (only in this case) → use this guidance, and tell the user
   which stack was picked and why:
   - Full product-grade app (multi-page, richest component set, data tables/forms/charts) →
     stack A.
   - Full control over markup/CSS with no UI-kit dependency, or needs i18n, or a single-shell
     "process → show results" app with no routing → stack B.
   - No Node/JS build pipeline wanted, backend is Python serving static files directly, app is an
     operational/live-data dashboard (video, SSE, WebRTC) → stack C.

## Scaffolding commands per stack

### Stack A — React + Redux Toolkit + Tailwind v4 + Radix (shadcn-style)

```bash
cp -r .github/skills/unified-ui-ux-builder/assets/templates/react-tailwind-shadcn/* <target-ui-dir>/
cd <target-ui-dir> && npm install
npx shadcn@latest add table dialog tabs badge   # add more primitives on demand
npm run dev
```

- `src/index.css`: OKLCH design tokens under `:root`/`@theme inline`, from the reference app's
  `colors-base.css`/`colors-semantic.css` — see `design-tokens.md`.
- `.env.example`: copy to `.env` and set `VITE_API_BASE` to the real backend URL for local dev
  (read by `vite.config.js`'s proxy). Never commit `.env` itself — the template's `.gitignore`
  already excludes it while keeping `.env.example` tracked.
- `src/lib/utils.js`: `cn()` helper combining `clsx` + `tailwind-merge`.
- Path alias `@/*` → `./src/*` in both `vite.config.js` and `jsconfig.json`.
- Redux Toolkit + RTK Query: follow the reference app's `src/store/index.ts` (slices +
  `redux-persist` for the subset that should survive reloads) and `src/api/` (generated RTK Query
  client). No copy-paste template for these yet — hand-wire per `component-library.md`'s "Data /
  state architecture" section.

### Stack B — React + Redux Toolkit + plain CSS

```bash
cp -r .github/skills/unified-ui-ux-builder/assets/templates/react-redux-plain-css/* <target-ui-dir>/
cd <target-ui-dir> && npm install
# optional, only if the app needs multi-language:
npm install i18next react-i18next
npm run dev
```

- Template already includes: TypeScript (`react-ts`), `src/index.css` with the exact root tokens
  (`--font-display`, `--font-text`, `--color-theme: #0071c5`, `--control-*` — see
  `design-tokens.md` stack B section), a sample `redux/slices/uiSlice.ts` + `store.ts` + typed
  `hooks.ts`, a thin axios `services/api.ts`, and sample `TopPanel`/`Header`/`Accordion`/`Body`
  components each with their own `.css` file — extend these, don't start from a blank app.
- `.env.example`: copy to `.env` and set `VITE_API_BASE` to the real backend URL for local dev
  (read by `vite.config.ts`'s proxy). Never commit `.env` itself — the template's `.gitignore`
  already excludes it while keeping `.env.example` tracked.
- One slice per domain concept under `src/redux/slices/*.ts` (`createSlice`, no RTK Query). One
  `.css` file per component, imported directly in the component (no CSS-in-JS, no Tailwind).
- No path alias — relative imports throughout, matching the reference app.

### Stack C — Vanilla JS static app

```bash
cp -r .github/skills/unified-ui-ux-builder/assets/templates/vanilla-js/* <target-ui-dir>/
# serve via the existing Python backend's static file route:
#   FastAPI: app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
#   Flask:   app.static_folder = "ui"; or render_template(...) for server-rendered pages
```

- No `.env.example` here: there's no Vite/build step to inject env vars into the browser. The
  vanilla-JS client calls the API via a relative path (`/api/...`), same-origin as the Python
  backend that serves it — nothing to configure per environment.
- Template already includes: `index.html` loading `js/*.js` as plain `<script>` tags in dependency
  order (utils -> services -> components -> app.js), `css/styles.css` with `:root` tokens (dark
  default) + `[data-theme="light"]` override, a `ThemeManager` IIFE (`js/utils/theme.js`), a thin
  fetch-based `ApiService` (`js/services/api.js`), a reconnect-with-backoff `StreamService` for SSE
  (`js/services/stream.js`), and a small `StatusDot` component — extend these, don't start from a
  blank `index.html`.
- Keep each `.js` file a self-contained IIFE module
  (`const Foo = (function () { ... return {...}; })();`) exposing only what other scripts need —
  the reference app's exact convention; avoids a bundler or `type="module"` import graph.
- Live data: prefer a single multiplexed `EventSource` (SSE) connection per concern (captions,
  metrics) over polling, with a reconnect-with-backoff loop (see `js/services/stream.js`, based on
  the reference app's `metadata-stream.js`'s `reconnectTimer`/5000ms pattern) — reuse this exact
  pattern.

## Apps on a stack outside the three references

- This skill does not support building or updating UI on any stack other than the three above.
- If an existing UI is on an unsupported stack (Vue, Gradio, Jinja templates, etc.): flag the
  mismatch, offer migration to one of the three (see above).
- Decline migration → explain the skill's scope/intent (uniform repo UI from three curated,
  high-quality reference stacks), say the task is out of scope, and stop — make no UI/UX changes.
