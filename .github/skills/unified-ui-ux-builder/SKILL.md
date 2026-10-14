---
name: unified-ui-ux-builder
description: >-
  Design and scaffold a UI/UX for any app, sample, or suite across OEP repos
  (edge-ai-suites, edge-ai-libraries, and similar), any domain, so it matches
  the product family. Use for a new frontend, a redesign, a new
  page/component/dashboard, or turning a backend API and/or mockup image
  into a working UI. Auto-detects the stack for existing apps; for new apps
  offers 3 curated stacks (React+Redux+Tailwind+Radix/shadcn, React+Redux+
  plain CSS, vanilla JS), each with shared design tokens, component
  patterns, layouts, and a starter template from 3 reference apps.
  Requires an approved draw.io wireframe before any code is scaffolded. Not
  for backend/API implementation, infra/Helm/Docker authoring, or docs.
license: Apache-2.0
compatibility: >-
  React stacks need Node.js 20+ and npm (Tailwind/Radix stack also uses
  `npx shadcn@latest add <component>`); vanilla-JS needs only a static file
  server. Works from any OEP repo. Wireframes are plain `.drawio` (mxGraph
  XML) files, openable in draw.io desktop, app.diagrams.net, or the VS Code
  Draw.io extension, and importable into FigJam via its diagrams.net plugin
  (no direct Figma API push).
metadata:
  author: open-edge-platform
  version: "3.0.0"
  tags: ui, ux, frontend, react, redux, tailwind, radix, shadcn, vanilla-js, design-system, edge-ai, oep, wireframe, drawio, figma
allowed-tools: bash ask_user
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UI/UX Builder

- Scaffolds or evolves the frontend of **any app, any domain, any OEP repo** (edge-ai-suites,
  edge-ai-libraries, or similar) so it's quick to build and instantly recognizable as the same
  product family — same colors, typography, layout shells, components.
- Tokens/components/layouts below come **only** from three hand-picked reference apps (see
  "Survey of the repo"), not a general survey of the whole monorepo — but nothing here is specific
  to any one app's business domain or to one repo; apply the same patterns anywhere in OEP.

| Field | Value |
|-------|-------|
| Skill ID | unified-ui-ux-builder |
| Version | 3.0.0 |
| Input | Target app path (any OEP repo), optional backend code (API routes/schemas), optional blueprint/mockup image |
| Output | Approved wireframe → running (or extended) frontend: scaffolded project, pages, components wired to the backend |
| Design tokens | `references/design-tokens.md` (**normative**) |
| Component patterns | `references/component-library.md` |
| Layouts | `references/layout-patterns.html` |
| Wireframing (draw.io/Figma) | `references/wireframing.md` (**required approval gate before Step 7 build**) |
| Stack selection | `references/stack-and-scaffolding.md` |
| Starter template | `assets/templates/react-tailwind-shadcn/` (stack A), `assets/templates/react-redux-plain-css/` (stack B), `assets/templates/vanilla-js/` (stack C) |

---

## When to use - Example triggering phrases

Each scenario below includes an example trigger phrase (bolded) — a sample of how a user might
phrase the request; similar wording with the same intent also applies.

- Create a brand-new UI for a new app/suite from scratch — **"Create a new UI from scratch."**
- Add a page, panel, dashboard, or component to an existing app's UI — **"Add a feature to the
  UI."**
- Generate/update a UI from a blueprint or mockup image — **"Update the UI to match this
  blueprint."**
- Redesign/restyle an existing UI to match the OEP product family — **"Restyle the UI to match
  the rest of the repo."**
- Generate a UI from a backend's API/data model alone, with no blueprint — any business domain
  (the skill maps *data/endpoint shape* to layout, not domain vocabulary).

**Do not use** for backend implementation, Dockerfile/Helm authoring, or onboarding-doc validation
(see `onboarding-validation` and `security-review` skills instead).

See `example-prompts/` for full step-by-step walkthroughs of these scenarios.

---

## Survey of the repo (why these choices)

- **Three** reference apps, hand-picked for UI/UX quality — the *only* source for tokens,
  components, layouts, templates below. Other apps in the repos are **not** used as reference.
- Never assume which of the three to use for a new app (see "Choosing a stack").
- Scope is intentionally limited to these three stacks:
  - Extending an existing app whose stack already matches one of the three → keep using it.
  - Extending an app on a **different** stack → flag the mismatch, ask consent to migrate to one
    of the three (Step 2). Decline → **do not proceed** with the UI/UX work; this skill doesn't
    build/update UI on a non-reference stack, and must say so.
- This three-app restriction governs: (a) the shared token/component/layout docs below, (b) the
  menu offered to brand-new apps (Step 3), (c) the migration-consent gate for existing apps on a
  non-reference stack.

| # | Stack | Reference app | Core packages |
|---|---|---|---|
| **A** | **React + Redux Toolkit + Tailwind v4 + Radix-primitive components (shadcn-style)** | `edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool/ui` | `react@19`, `vite`, `@tailwindcss/vite`, `@reduxjs/toolkit`, `react-redux`, `redux-persist`, `react-router`, `@radix-ui/react-*`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `react-hook-form` + `zod`, `@tanstack/react-table`, `recharts`, `sonner`, `next-themes`, `react-resizable-panels`, `@xyflow/react` (only if a graph/flow editor is genuinely needed) |
| **B** | **React + Redux Toolkit + plain CSS, custom components (no UI kit)** | `edge-ai-suites/education-ai-suite/smart-classroom/ui` | `react@19`, `vite`, `@reduxjs/toolkit`, `react-redux`, `axios`, `i18next` + `react-i18next` (only if multi-language is needed), one `.css` file per component under `src/assets/css/`, no CSS modules/styled-components/UI kit |
| **C** | **Vanilla JS (IIFE modules), no build step, served by a Python backend** | `edge-ai-suites/metro-ai-suite/live-video-analysis/live-video-captioning` | plain `<script>` tags (no bundler, no ES modules), hand-written `fetch`/`EventSource` (SSE) client, CSS custom properties with a `[data-theme="light"\|"dark"]` toggle, served via FastAPI (`StaticFiles` mount) or Flask |

- All three share: a thin API/services layer wrapping HTTP calls, a light/dark theme toggle driven
  by CSS custom properties, SPDX headers on every file.
- Each has its **own** primary blue accent (see `design-tokens.md`) — same Intel-blue hue family,
  different hex values. New app → adopt the accent of whichever reference stack it's based on;
  never invent a fourth blue.

Full detail: `references/stack-and-scaffolding.md`.

---

## Instructions

Follow this exact sequence. **Never assume anything the user hasn't told you or that isn't
verifiable by reading the repo** — use `ask_user` at every step below where information is missing
or ambiguous.

### Step 1 — Ask for the app path

- Always ask for the exact target path first — e.g. "Which app/directory should I build or update
  the UI for?" Don't guess a suite or app name; don't auto-detect from naming similarity.
- Exception: if the user's current working directory is already inside that app's folder, confirm
  it back to them instead of asking from scratch.
- Multiple plausible candidates (e.g. similarly named dirs, one populated/one empty) → list them
  and ask the user to pick, rather than guessing.

### Step 2 — Analyze the use case and backend

- **UI already exists at that path:**
  - Read it first: `package.json`/`requirements.txt`, src tree, theme/CSS files. Auto-detect its
    stack, state it back to the user.
  - Matches one of the three reference stacks (A/B/C) → continue in it, don't ask to choose
    (Step 3).
  - Matches none of the three (Vue, Angular, Svelte, different CSS framework/component kit, etc.):
    - Tell the user plainly: detected stack, and that this skill supports **only** the three
      reference stacks, to keep the repo's UI/UX uniform.
    - `ask_user` to migrate to one of the three (same options/trade-offs as Step 3). Never offer
      "keep the current non-reference stack" as a valid path.
    - Decline migration → explain the skill's scope/intent (uniform repo UI from three curated
      stacks; arbitrary stacks would undermine that), say the task is out of scope, and stop — no
      UI/UX changes. Never migrate without explicit consent; never silently work on a non-reference
      stack either way.
- **Understand the use case and API shape — cheapest accurate source first, don't default to
  reading all backend source:**
  1. Use case → read `README.md`/`docs/` "Getting Started"/user guide first for what the app does
     in plain language.
  2. Endpoints/params/schemas → look for an OpenAPI/Swagger spec (`openapi.yaml`/`.json`,
     `/docs`/`/openapi.json` route, `swagger.yaml`) first; it already enumerates everything a route
     grep would, far more cheaply.
  3. Only read backend route/model source directly when no spec/docs exist, or they're
     incomplete/stale for what's needed — note the gap rather than trusting a stale spec silently.
  4. Can't locate backend code, docs, or spec at all → ask the user where it lives; never guess the
     API shape.
- From whichever source, enumerate real resources/endpoints + fields/types; infer the use case in
  plain terms (e.g. "camera collection + per-camera stream"). Unclear use case/shape → ask, don't
  invent fields/endpoints/behavior.
- Think in generic resource *shapes* (collection, live session/stream, singleton config) — the
  same UI mapping applies regardless of the actual domain (cameras, machines, patients, vehicles).
  Mapping to layouts happens in Step 6.

### Step 3 — Ask the user to choose a stack (new apps only)

- Step 2 already detected an existing stack → skip this step, continue in that stack.
- Brand-new app → MUST ask the user to choose before scaffolding anything (never default/silently
  pick). Use `ask_user` with these three options, each labeled with its trade-off:
  - "React + Redux Toolkit + Tailwind v4 + Radix-primitive components — matches
    `visual-pipeline-and-platform-evaluation-tool/ui`; richest component set (tables, forms,
    charts, resizable panels), best for a full-featured product-grade app"
  - "React + Redux Toolkit + plain CSS, custom components — matches
    `education-ai-suite/smart-classroom/ui`; no UI-kit dependency, full control over every
    component's markup/CSS, or needs i18n"
  - "Vanilla JS (no build step), served by your Python backend — matches
    `live-video-analysis/live-video-captioning`; lightest weight, no Node/npm pipeline, good for
    an operational/video dashboard tightly coupled to a FastAPI/Flask backend"
  - Plus "I'm not sure — recommend one for my use case" — only here may the agent suggest a stack,
    and must say which + why (using Step 2's inferred use case and
    `references/stack-and-scaffolding.md`'s resolution order), never silently.
- Don't proceed to Step 4 until the stack is detected or confirmed. The stack must be known before
  analyzing any blueprint (Step 4), since component mapping depends on it.

### Step 4 — Analyze a blueprint/mockup image, if provided

- Ask if the user has a blueprint/mockup/reference design before assuming they don't. Accept
  either: an attached/pasted image (png/jpg/pdf/Figma export), or a repo/workspace file path
  openable with `view`.
- Path unreachable from this environment (e.g. local `C:/Users/...`) → say so plainly; ask for a
  repo/workspace path or a direct attachment. Never silently skip the blueprint or guess its
  contents.
- No blueprint → ask whether the user wants to describe the layout in text instead (which
  regions/components they want, order/priority) before falling back to reference-only design
  (point 7 below). Only fall back once the user confirms they have neither.

Once supplied:

1. View the image; identify page regions (header/sidebar/content), component types (cards,
   tables, charts, forms, tabs), approximate color accents, content hierarchy.
2. Map each region to the closest pattern in `references/layout-patterns.html` and component in
   `references/component-library.md` — don't invent new primitives. Build using the matching
   stack's template/components (shadcn-style for A, plain custom for B, hand-written CSS for C),
   not raw HTML/CSS mimicking the image pixel-for-pixel.
3. Reproduce structure, content hierarchy, and component choices as closely as the stack allows —
   apply shared tokens (colors, radius, shadows, fonts), not the blueprint's literal pixel colors.
   **User explicitly asks for exact color/font fidelity anyway:** first propose the closest
   matching shared token as the default. Still insisted on → tell them plainly this deviates from
   the shared design tokens and breaks visual consistency with the rest of the product family —
   never apply it silently. Proceed only after their explicit confirmation, and record the
   override in the Step 8 summary.
   - **A prior override already happened this engagement** (here or in Step 7.5): don't treat
     this as another isolated ask — tell the user this is now a *pattern*, not a single exception,
     and that continuing will make this UI no longer recognizable as part of the product family.
     Still their call, but say so plainly before proceeding.
4. **Something can't be faithfully achieved in the current stack** (e.g. drag/resize layout in
   vanilla JS, a complex data grid with no equivalent in plain-CSS, a shape with no match in
   `component-library.md`): don't silently drop/approximate it.
   - Tell the user what can't be done, why, what you built instead.
   - If a different reference stack would support it, name that stack and ask if they'd like to
     switch (may revisit Step 3).
5. **Separately, check whether the backend actually has the data the blueprint implies** (not just
   whether the stack can render it) — e.g. mockup shows images/frames but nothing serves them, or
   a per-run export with no run identifier in the schema. This is a backend-data gap, distinct from
   a stack-rendering gap, and must be flagged separately:
   - Say exactly what's missing, whether it's fixable with the current backend+stack or needs a
     backend change — if truly not fixable, say so and suggest an alternative.
   - Fixable but needs backend work → ask the user to choose: **(a)** stub it in the UI only
     (wire to the intended API shape, mark the stub clearly in code comments/docstrings and in the
     rendered UI, e.g. a "PLACEHOLDER" badge), leaving backend work as a follow-up; **(b)**
     implement the backend change now; or **(c)** treat it as a separate follow-up and skip for
     now. Never pick one of these on the user's behalf.
6. Backend (Step 2) + blueprint both present → blueprint drives layout/visual structure, backend
   drives data/behavior. Conflict (e.g. mockup field the backend doesn't have) → ask the user.
7. No blueprint and no text-described layout → skip this step; build directly from
   `references/layout-patterns.html` (resource-shape → layout mapping),
   `references/component-library.md` (matching stack's components),
   `references/design-tokens.md` (colors/spacing/radius), and the chosen stack's starter template
   under `assets/templates/` (base file structure/App Shell to extend) — driven by Step 2's
   resource shapes alone (Step 6) — never invent a layout, styling, or structure outside these
   references.
8. User uploaded blueprint image(s) into the repo for this session → once UI work is complete, ask
   whether to delete, keep, or move them. Never decide this without asking.

### Step 5 — Load the shared design system

Read in full before generating any code:
- `references/design-tokens.md` — color palette (each stack's own accent + shared status colors),
  typography, spacing/radius/shadow tokens, light/dark variants.
- `references/component-library.md` — canonical components, organized by stack, with the
  reference-app source and exact structure/classes to reuse.
- `references/layout-patterns.html` — recurring page shells from the three reference apps: **App
  Shell** (sidebar + header), **Dashboard Grid**, **Split Panel**.

### Step 6 — Create a wireframe and get explicit approval before any code

**Hard gate: do not start Step 7 until the user has explicitly approved a wireframe.** Read
`references/wireframing.md` in full and follow it:

1. Ask whether the user wants **draw.io/diagrams.net** (recommended, no account needed) or
   **Figma/FigJam** — explain up front that Figma's REST API can't create/edit design nodes
   directly, so the Figma path means importing the generated `.drawio` file into FigJam via
   Figma's "diagrams.net" plugin, not a direct push.
2. Resolve the layout pattern (`layout-patterns.html` → "Choosing a layout for a new resource",
   driven by Step 2's backend shapes and/or Step 4's blueprint mapping); enumerate the concrete
   regions/components to place:
   - Existing app → read its current component tree/routes/CSS regions; reflect what's actually
     live today, not an idealized redesign. If a blueprint was provided in Step 4, perform blueprint region mapping for the regions it covers, also apply Step 2's resources/fields slotted
     into the existing structure — untouched regions still reflect what's live today.
   - New app → lay out boxes from the chosen layout pattern + Step 2's resources/fields + Step 4's
     blueprint region mapping (if provided).
3. Generate the `.drawio` file (neutral/gray placeholder boxes, one labeled box per
   component/region — see `wireframing.md`'s shape-mapping table). Tell the user where it is and
   how to open/edit it; iterate on the same file through as many feedback rounds as needed.
4. Only once the user gives explicit approval ("approved", "looks good, build it", etc.) may you
   proceed to Step 7, using the approved box layout/component list as the authoritative structure
   — Step 7 must build to match it, not redesign it.

### Step 7 — Scaffold and build the UI

Copy the matching template for whichever stack was detected/chosen in Step 3:

```bash
# Stack A: React + Redux Toolkit + Tailwind v4 + Radix-primitive (shadcn-style) components
cp -r .github/skills/unified-ui-ux-builder/assets/templates/react-tailwind-shadcn/* <target-ui-dir>/
cd <target-ui-dir> && npm install
# add further shadcn-style primitives on demand, e.g.:
npx shadcn@latest add table dialog tabs badge

# Stack B: React + Redux Toolkit + plain CSS (TypeScript)
cp -r .github/skills/unified-ui-ux-builder/assets/templates/react-redux-plain-css/* <target-ui-dir>/
cd <target-ui-dir> && npm install

# Stack C: vanilla JS, no build step
cp -r .github/skills/unified-ui-ux-builder/assets/templates/vanilla-js/* <target-ui-dir>/
```

All three templates are minimal starters, not full copies of the reference apps — extend them,
don't feel bound to their exact file count.

Then, using Step 2's use case, Step 4's layout (if a blueprint was given), and the **approved
wireframe from Step 6**:

1. Rename the app (`package.json` name, `index.html` title, Header brand text, and the template's
   `README.md` title/description).
2. Build regions/components exactly as placed in the approved Step 6 wireframe (list/collection →
   **Dashboard Grid**, stat cards + table; single live resource → **Split Panel**; everything else
   → **App Shell** page with a form/detail view). Don't silently change the approved structure —
   if something turns out impractical mid-build, stop and go back to the user/Step 6.
3. Generate a thin `services/api.*` (or `api/request.ts`) client with one function per real
   endpoint from Step 2. Never fabricate endpoints or fields.
4. Use the shared Intel-blue primary accent (`design-tokens.md` "Suite accent colors") — never
   invent a different primary brand color. Only add a secondary, purely semantic accent (e.g.
   status/category color) if genuinely needed beyond success/warn/error — ask the user first.
   Extending an app with its own non-referenced tokens → don't silently keep or replace; follow
   `design-tokens.md`'s "Ask, don't assume" (callout vs. default, propose an alternative if it's
   substantially off best practice, user decides).
5. **Any new requirement beyond the approved wireframe** (a component type, interaction, or
   style not in `component-library.md`/`layout-patterns.html`/`design-tokens.md`): check whether
   the chosen stack's reference app supports it first.
   - Supported → build it with the existing pattern/tokens.
   - Not supported by any reference stack → say plainly this falls outside the skill's
     unification scope (same look/behavior across the product family), suggest the closest
     supported alternative, and proceed only if the user explicitly accepts the deviation —
     record it in the Step 8 summary.
   - **A prior override already happened this engagement** (here or in Step 4.3): flag this as a
     pattern, not a one-off — tell the user continuing will make this UI no longer recognizable
     as part of the product family before proceeding.
6. Add SPDX headers (`SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
   `SPDX-License-Identifier: Apache-2.0`) to every new source file.
7. **Restructuring an existing template/page** (not scaffolding new) — first grep the existing
   JS/tests for every element ID, class, selector they depend on (`getElementById`,
   `querySelector`, test assertions on structure). After rewriting markup, verify each still
   appears exactly once — no existing script silently breaks from a missing/duplicated ID/class.
8. Once built, follow `wireframing.md`'s cleanup step: ask whether the wireframe file should be
   kept, moved, or deleted — same handling as blueprint images in Step 4.

### Step 8 — Validate

- `npm run build` (or `npm run lint` if build requires unavailable infra) must pass before
  finishing.
- Existing test suite present (pytest, vitest, jest, etc.) → run it **before** changes to capture
  a baseline, then again after. Confirm no new regressions vs. that baseline (pre-existing
  failures unrelated to this work may remain — note them as pre-existing, don't silently ignore).
  Add tests for any new routes/components where the existing suite has a pattern for it.
- Confirm no hard-coded secrets; any new `.env` usage follows `.env.example` conventions.
- If the app runs via an existing `docker/docker-compose.yml`, ask the user whether to rebuild/
  recreate that container so the change is visible — never rebuild silently, and never author new
  Docker/Helm config (out of scope; see "When to use").
- Spot-check the new UI matches shared design tokens (no ad hoc colors outside the palette unless
  called out/confirmed with the user per `design-tokens.md`); SPDX headers present on new files.
- Summarize for the user: detected/chosen stack, approved wireframe + final location
  (kept/moved/deleted), resources wired, any backend-data gaps flagged and how resolved
  (stubbed/implemented/deferred), test results vs. baseline, open questions asked along the way,
  and any non-referenced token values or out-of-scope requirements kept/approved (what, why, and
  the closest supported alternative that was proposed first). Note any earlier migration from a
  non-reference stack.
  - **Two or more overrides accepted this engagement** → list them together as one combined block
    (not scattered through the rest of the summary) so the user sees the cumulative drift from the
    shared design system in one place, and can reconsider even after approving each individually.
- After the summary, explicitly ask whether this covers everything or more UI/UX work is needed
  (another screen, a tweak, a different blueprint). Keep asking after each follow-up round until
  the user confirms they're done — never assume a single pass ends the engagement.
