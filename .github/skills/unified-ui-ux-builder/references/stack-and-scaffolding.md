# Stack Selection & Scaffolding

This skill offers **three** curated reference stacks for brand-new apps — chosen for UI/UX quality,
not surveyed from every app in the repo. **Never assume or default to one.** The goal is a uniform
look/feel across the repo, so this skill is intentionally scoped to support **only** these three
stacks — not any other. Existing apps are not exempt: for an app that already has a UI, auto-detect
its stack first. If it already matches one of the three, continue in it without asking. If it does
**not** match any of the three (e.g. an app on Vue, Gradio, or Jinja templates), tell the user the
detected stack is outside the repo's three supported reference stacks and that this skill does not
build or update UI on any other stack — then ask for consent to migrate it to one of the three
(same options as Step 4) before doing any UI work. **If the user declines migration, do not just
stop silently.** First explain the skill's scope and intent — it exists to keep every app in the
repo visually consistent by building strictly from three curated, high-quality reference stacks,
and supporting arbitrary stacks would defeat that purpose — then tell them this task is out of
scope for the skill unless they agree to migrate, and stop without making any UI/UX changes to that
app. There is no "keep the non-reference stack and continue" path. For a brand-new app, the agent
MUST ask the user to choose (see `SKILL.md` Step 4) before scaffolding anything. Do not mix stacks
within one app.

> **Ask, don't assume (beyond stack choice):** once the stack is settled, still confirm anything
> not implied by the backend or an existing convention — e.g. whether the app needs client-side
> routing/multiple pages (stack A only), whether i18n is required (stack B supports it via
> `i18next`), light-only vs. dark-only vs. toggle, and which port/base path it should run on.

| # | Stack | Reference app | Typical fit |
|---|---|---|---|
| **A** | **React + Redux Toolkit + Tailwind v4 + Radix-primitive (shadcn-style) components** | `edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool/ui` | Full-featured, multi-page product UI that needs the richest component set fastest (tables, forms, resizable panels, charts, a flow/graph editor). |
| **B** | **React + Redux Toolkit + plain CSS, custom components (no UI kit)** | `edge-ai-suites/education-ai-suite/smart-classroom/ui` | Extending an app that wants full control over every component's markup/CSS without a UI-kit dependency, or needs i18n; single-shell, screen-state-driven (no router) apps. |
| **C** | **Vanilla JS (IIFE modules), no build step** | `edge-ai-suites/metro-ai-suite/live-video-analysis/live-video-captioning` | Lightweight app served directly by a Python backend (FastAPI/Flask) with no Node build pipeline wanted; operational/video dashboards with SSE/WebRTC live data. |

All three share: a thin API/services layer wrapping HTTP calls, a light/dark theme toggle driven by
CSS custom properties, and SPDX headers on every file.

## Stack resolution order

1. **Does a UI already exist for this app?** → read its `package.json`/`requirements.txt` and
   source tree first. If it matches one of the three reference stacks, continue in it without
   asking. If it doesn't match any of the three, flag the mismatch and ask the user for consent to
   migrate to one of the three before proceeding (see above). If they decline, explain the skill's
   scope/intent (uniform repo UI built from three curated stacks) before stopping — do not do any
   UI/UX work on that app. Never introduce a second stack into one app.
2. **Is this a brand-new app?** → present the three options above to the user with `ask_user` (or
   equivalent) and wait for their choice. Do not scaffold until they answer.
3. **User asked the agent to recommend one** (explicit "not sure, you pick" answer only) → use the
   guidance below, and tell the user which one was picked and why:
   - Full product-grade app (multi-page, richest component set, data tables/forms/charts) →
     stack A.
   - Wants full control over markup/CSS with no UI-kit dependency, or needs multi-language (i18n),
     or is a single-shell "process → show results" app with no routing → stack B.
   - No Node/JS build pipeline wanted, backend is Python serving static files directly, app is an
     operational/live-data dashboard (video, SSE, WebRTC) → stack C.

## Scaffolding commands per stack

### Stack A — React + Redux Toolkit + Tailwind v4 + Radix (shadcn-style)

```bash
cp -r .github/skills/ui-ux-builder/assets/templates/react-tailwind-shadcn/* <target-ui-dir>/
cd <target-ui-dir> && npm install
npx shadcn@latest add table dialog tabs badge   # add more primitives on demand
npm run dev
```

Key files: `src/index.css` (OKLCH design tokens under `:root`/`@theme inline`, taken from the
reference app's `colors-base.css`/`colors-semantic.css` — see `design-tokens.md`), `src/lib/utils.js`
(`cn()` helper combining `clsx` + `tailwind-merge`), path alias `@/*` → `./src/*` in both
`vite.config.js` and `jsconfig.json`. For Redux Toolkit + RTK Query, follow the reference app's
`src/store/index.ts` (slices + `redux-persist` for the subset that should survive reloads) and
`src/api/` (generated RTK Query client) structure — there's no copy-paste template for these yet;
hand-wire them per `component-library.md`'s "Data/state architecture" section.

### Stack B — React + Redux Toolkit + plain CSS

```bash
npm create vite@latest <app-name> -- --template react-ts
cd <app-name>
npm install @reduxjs/toolkit react-redux axios
# optional, only if the app needs multi-language:
npm install i18next react-i18next
# one slice per domain concept under src/redux/slices/*.ts (createSlice, no RTK Query),
# store.ts combining them, typed hooks in src/redux/hooks.ts
# one .css file per component under src/assets/css/*.css, imported directly in the component
```

Reuse the reference app's root tokens (`--font-display`, `--font-text`, `--color-theme: #0071c5`,
`--control-*`) in a top-level `src/index.css` — see `design-tokens.md` stack B section for the
exact values.

### Stack C — Vanilla JS static app

```bash
mkdir -p <target-ui-dir>/{js/components,js/services,js/utils,css}
# index.html links css/styles.css and loads js/*.js as plain <script> tags in dependency order
# (vendor -> utils -> services -> components -> app.js) — no bundler, no ES modules
# css/styles.css defines :root tokens (dark default) + [data-theme="light"] override
# (see design-tokens.md stack C section for exact values)
# serve via the existing Python backend's static file route:
#   FastAPI: app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
#   Flask:   app.static_folder = "ui"; or render_template(...) for server-rendered pages
```

Keep each `.js` file a self-contained IIFE module
(`const Foo = (function () { ... return {...}; })();`) exposing only what other scripts need — this
is the reference app's exact convention and avoids needing a bundler or `type="module"` import
graph. For live data, prefer a single multiplexed `EventSource` (SSE) connection per concern
(captions, metrics) over polling, with a reconnect-with-backoff loop (see
`js/services/metadata-stream.js`'s `reconnectTimer`/5000ms pattern) — reuse this exact pattern
rather than inventing a new reconnection strategy.

## Apps on a stack outside the three references

This skill does not support building or updating UI on any stack other than the three references
above. If Step 2 detects an existing UI on a stack not covered above (Vue, Gradio, Jinja templates,
etc.), flag the mismatch and offer migration to one of the three reference stacks as described
above. If the user declines migration, do not stop abruptly — first convey the skill's scope and
intent: it exists to keep the repo's UI/UX uniform by building strictly on three curated,
high-quality reference stacks, so working on an arbitrary stack would undermine that goal. Only
after explaining this, tell them this task is out of scope for the skill until they agree to
migrate, and stop without making any UI/UX changes to that app.
