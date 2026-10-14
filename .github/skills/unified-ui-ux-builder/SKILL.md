---
name: ui-ux-builder
description: >-
  Design and scaffold a UI/UX for any app, sample, or suite across the Open
  Edge Platform (OEP) repos (edge-ai-suites, edge-ai-libraries, and similar)
  so it looks and feels like it belongs to the same product family — for any
  domain (video analytics, predictive maintenance, patient monitoring,
  retail, robotics, etc.). Use when a user wants to create a new frontend,
  redesign an existing one, add a page/component/dashboard, or turn a
  backend API and/or a blueprint/mockup image into a working UI. For an
  existing app it auto-detects the UI stack; for a new app it asks the user
  to choose among three curated reference stacks (React+Redux Toolkit+
  Tailwind+Radix/shadcn, React+Redux Toolkit+plain CSS, or vanilla JS).
  Provides shared design tokens, reusable component patterns, common
  layouts, and a ready-to-copy starter template derived from three
  hand-picked reference apps (visual-pipeline-and-platform-evaluation-tool,
  live-video-captioning, education-ai-suite/smart-classroom). Before code is
  scaffolded, it generates a drag-and-drop-editable wireframe (draw.io file,
  optionally imported into FigJam) and requires explicit user approval
  before implementation. Do not use for backend/API implementation,
  infra/Helm/Docker authoring, or documentation validation.
license: Apache-2.0
compatibility: >-
  Depends on the stack detected or chosen: the two React stacks require
  Node.js 20+ and npm (the Tailwind/Radix stack additionally uses the shadcn
  CLI via `npx shadcn@latest add <component>`); the vanilla-JS stack needs
  only a static file server, no Node/build step, and is typically served by
  a Python (FastAPI/Flask) backend. Works from any OEP repository
  (edge-ai-suites, edge-ai-libraries, etc.); not tied to any specific suite,
  app, or business domain. Wireframing needs no account or install: the
  skill authors a `.drawio` (mxGraph XML) file directly, openable in the
  draw.io desktop app, https://app.diagrams.net, or the VS Code "Draw.io
  Integration" extension. If the user prefers Figma/FigJam, the same file
  is imported there via Figma's free "diagrams.net" plugin — the Figma
  REST API itself has no endpoint to create/edit design nodes, so direct
  push isn't possible.
metadata:
  author: open-edge-platform
  version: "3.0.0"
  tags: ui, ux, frontend, react, redux, tailwind, radix, shadcn, vanilla-js, design-system, edge-ai, oep, wireframe, drawio, figma
allowed-tools: bash ask_user
---

# UI/UX Builder

Scaffold or evolve the frontend of **any app, in any domain, in any OEP repo** (edge-ai-suites,
edge-ai-libraries, or a similar Open Edge Platform repository) so it is quick to build and
instantly recognizable as part of the same product family — consistent colors, typography,
layout shells, and components — regardless of which suite, repo, or use case it serves. The
design system and layout/component patterns below are drawn strictly from **three hand-picked
reference apps** (chosen for UI/UX quality, not surveyed from every app in the repo) — see
"Survey of the repo" below — but nothing here is specific to any one app's business domain (video,
healthcare, manufacturing, retail, robotics, etc.) or to the edge-ai-suites repo itself — apply the
same patterns when working in edge-ai-libraries or any other OEP repo.

| Field | Value |
|-------|-------|
| Skill ID | ui-ux-builder |
| Version | 3.0.0 |
| Input | A target app path (in any OEP repo), optional backend code (API routes/schemas) for any domain, optional blueprint/mockup image |
| Output | An approved wireframe, then a running (or extended) frontend: scaffolded project, pages, and components wired to the backend |
| Design tokens | `references/design-tokens.md` (**normative**) |
| Component patterns | `references/component-library.md` |
| Layouts | `references/layout-patterns.md` |
| Wireframing (draw.io/Figma) | `references/wireframing.md` (**required approval gate before Step 7 build**) |
| Stack selection | `references/stack-and-scaffolding.md` |
| Starter template | `assets/templates/react-tailwind-shadcn/` (stack A only; stacks B/C are scaffolded from scratch per `stack-and-scaffolding.md`) |

---

## When to Use

Use this skill when the user wants to, **for any app/domain in any OEP repo**:

- Create a brand-new UI for a new app/suite from scratch.
- Add a page, panel, dashboard, or component to an existing app's UI.
- Redesign/restyle an existing UI to match the rest of the OEP product family.
- Generate a UI from a backend's API/data model, a blueprint/mockup image, or both — whatever the
  underlying business domain is (the skill maps *data/endpoint shape* to layout, not domain
  vocabulary).

Do not use this skill for backend implementation, Dockerfile/Helm authoring, or
onboarding-doc validation (see the `onboarding-validation` and `security-review` skills for those).

---

## Survey of the repo (why these choices)

**Three** reference apps were hand-picked across the OEP repos for their UI/UX quality — these are
the *only* apps this skill draws its design tokens, components, layouts, and templates from. Other
apps in edge-ai-suites/edge-ai-libraries may look different; they are **not** used as a reference
here. This skill never assumes which of the three to use for a new app — see "Choosing a stack"
below. The goal is a uniform-looking repo, so this skill is intentionally scoped to **only** these
three stacks: when **extending an existing app**, if its established stack already matches one of
the three, keep using it. If it does **not** match any of the three, flag the mismatch to the user
and ask for consent to migrate to one of the three reference stacks (see Step 2). If the user
declines migration, **do not proceed** with the UI/UX work — this skill does not support building
or updating UI on a non-reference stack, and must say so rather than working on it anyway. The
three-app restriction governs (a) the shared design-token/component/layout documentation below,
(b) the menu offered to brand-new apps in Step 4, and (c) this migration-consent gate for existing
apps on a non-reference stack.

| # | Stack | Reference app | Core packages |
|---|---|---|---|
| **A** | **React + Redux Toolkit + Tailwind v4 + Radix-primitive components (shadcn-style)** | `edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool/ui` | `react@19`, `vite`, `@tailwindcss/vite`, `@reduxjs/toolkit`, `react-redux`, `redux-persist`, `react-router`, `@radix-ui/react-*`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `react-hook-form` + `zod`, `@tanstack/react-table`, `recharts`, `sonner`, `next-themes`, `react-resizable-panels`, `@xyflow/react` (only if a graph/flow editor is genuinely needed) |
| **B** | **React + Redux Toolkit + plain CSS, custom components (no UI kit)** | `edge-ai-suites/education-ai-suite/smart-classroom/ui` | `react@19`, `vite`, `@reduxjs/toolkit`, `react-redux`, `axios`, `i18next` + `react-i18next` (only if multi-language is needed), one `.css` file per component under `src/assets/css/`, no CSS modules/styled-components/UI kit |
| **C** | **Vanilla JS (IIFE modules), no build step, served by a Python backend** | `edge-ai-suites/metro-ai-suite/live-video-analysis/live-video-captioning` | plain `<script>` tags (no bundler, no ES modules), hand-written `fetch`/`EventSource` (SSE) client, CSS custom properties with a `[data-theme="light"\|"dark"]` toggle, served via FastAPI (`StaticFiles` mount) or Flask |

All three share: a thin API/services layer wrapping HTTP calls, a light/dark theme toggle driven by
CSS custom properties, and SPDX headers on every file. Each has its **own** primary blue accent
(see `design-tokens.md`) — they are all in the same Intel-blue hue family but not identical hex
values; a new app should adopt the accent of whichever reference stack it's based on, not invent a
fourth blue.

Full detail: `references/stack-and-scaffolding.md`.

---

## Instructions

Follow this exact sequence. **Never assume anything the user hasn't told you or that isn't
verifiable by reading the repo** — use `ask_user` (or equivalent clarifying questions) at every
step below where information is missing or ambiguous.

### Step 1 — Ask for the app path

Always ask the user for the exact target path before doing anything else — e.g. "Which
app/directory should I build or update the UI for? (give the path, or describe where the new app
should live, e.g. `<suite>/<app-name>/ui`)." Do not guess a suite or app name, and do not try to
auto-detect the path from repo structure or naming similarity. The only exception is when the
user's current working directory is already inside that app's own folder (e.g. they're clearly
working from `<suite>/<app-name>/` already) — in that case confirm it back to them instead of
asking from scratch. If more than one plausible candidate exists (e.g. similarly named
directories, one populated and one an empty placeholder), list the candidates and ask the user to
pick the right one rather than guessing which is intended.

### Step 2 — Analyze the use case and backend

Once the path is known:

1. **If a UI already exists** at that path, read it first: `package.json`/`requirements.txt`, the
   src tree, and theme/CSS files. Auto-detect its stack from this — state the detected stack back
   to the user.
   - **If the detected stack matches one of the three reference stacks** (A/B/C in "Survey of the
     repo"), continue in it — do not ask them to choose a stack in this case (see Step 4).
   - **If the detected stack does NOT match any of the three** (e.g. an app built with Vue, Angular,
     Svelte, a different CSS framework, or a different component kit), do not silently keep using
     it. Tell the user plainly: what stack was detected, and that this skill is intentionally
     designed to support **only** the three reference stacks (A/B/C) — not any other stack — in
     order to keep the repo's UI/UX uniform. Then use `ask_user` to offer migrating this app's UI to
     one of the three reference stacks (present the same three options/trade-offs as Step 4).
     **Do not offer "keep the current non-reference stack" as a valid path forward.** If the user
     still declines migration, do not just stop silently — first clearly convey the skill's scope
     and intent: this skill exists to give every app in the repo the same curated, high-quality
     look/feel built from three hand-picked reference stacks, and supporting arbitrary stacks would
     undermine that goal, so it deliberately does not build or update UI on a non-reference stack.
     Only after explaining this, tell them this task is therefore out of scope for the skill unless
     they agree to migrate, and stop without making any UI/UX changes to the app. Never migrate a
     stack without their explicit consent, and never silently work on a non-reference stack either
     way.
2. **Find and read the backend code** for this app (routes, OpenAPI/schema, models, or equivalent).
   If you can't locate it, ask the user where it lives — do not proceed on guesses about the API
   shape.
3. From the backend, enumerate the real resources/endpoints and their fields/types, and infer the
   use case in plain terms (e.g. "this looks like a live video-analytics app with a camera
   collection and a per-camera stream"). If the use case or a resource's shape is still unclear,
   ask the user rather than guessing — do not invent fields, endpoints, or domain behavior that
   isn't in the code.
4. Think in terms of generic resource *shapes* (collection, live session/stream, singleton
   config) — the same UI mapping applies whether the collection is cameras, machines, patients,
   vehicles, or anything else (the actual mapping to layouts happens in Step 6).

### Step 3 — Analyze a blueprint/mockup image, if provided

Ask the user if they have a blueprint/mockup/reference design before assuming they don't. If they
do, ask them to supply it either by:

- attaching/pasting the image directly in the chat/IDE (png/jpg/pdf/Figma export), or
- giving a file path in the repo/workspace that can be opened with the `view` tool.

If the user gives a path that turns out to be unreachable from the current environment (e.g. a
local machine path like `C:/Users/...` that the session can't read), tell them plainly that the
path isn't reachable and ask them to either point to a path inside the repo/workspace or upload/
attach the image directly (e.g. by adding it to the repo so it can be opened with `view`). Do not
silently skip the blueprint or guess its contents.

Once supplied:

1. View the image and identify: page regions (header/sidebar/content), component types (cards,
   tables, charts, forms, tabs), approximate color accents, and content hierarchy.
2. Map each region to the closest existing pattern in `references/layout-patterns.md` and
   component in `references/component-library.md` instead of inventing new primitives, then build
   using the matching stack's starter template/components so the recreation stays idiomatic to
   that stack (e.g. shadcn-style primitives for stack A, plain custom components for stack B, hand-
   written CSS classes for stack C) rather than hand-rolling raw HTML/CSS that mimics the image
   pixel-for-pixel.
3. Reproduce the blueprint as closely as the chosen/detected stack reasonably allows — match its
   structure, content hierarchy, and component choices — but apply the repo's shared tokens
   (colors, radius, shadows, fonts) rather than the blueprint's literal pixel colors, unless the
   user asks for exact color fidelity.
4. **If something in the blueprint cannot be faithfully achieved in the current stack** (e.g. a
   drag-and-drop/resizable-panel layout that plain vanilla JS can't support well, a complex data
   grid with no equivalent in a no-UI-kit plain-CSS app, a component shape with no match in
   `component-library.md`), do not silently drop or approximate it without saying so. Explicitly
   tell the user which part can't be done as shown, why, and what you built instead — and if a
   different one of the three reference stacks would support it properly, name that stack and ask
   whether they'd like to switch (this may mean revisiting Step 4).
5. **Separately, check whether the backend actually has the data the blueprint implies** (not just
   whether the chosen *stack* can render it) — e.g. the mockup shows images/frames but no service
   persists or serves them, or a per-run export but the schema has no run identifier to scope it.
   This is a backend-data gap, distinct from a stack-rendering gap in point 4, and must be flagged
   separately:
   - Tell the user exactly what's missing, whether it's fixable at all with the current backend
     and UI stack, or only with a backend change — and if it truly cannot be done at all, say so
     and suggest an alternative (a different data source, a reduced scope, a different display).
   - If it's fixable but needs backend work, tell the user that and ask them to choose one of:
     **(a)** stub it in the UI only — wire the UI to the intended API shape now, with the stubbed
     endpoint/data clearly marked as a placeholder (both in code comments/docstrings and visibly in
     the rendered UI, e.g. a "PLACEHOLDER" badge/tooltip), leaving the real backend work for a
     separate follow-up task; **(b)** implement the real backend change now as part of this task;
     or **(c)** treat the whole thing as a separate follow-up task and skip it for now. Do not pick
     one of these on the user's behalf.
6. If both a backend (Step 2) and a blueprint are present, the blueprint drives layout/visual
   structure and the backend drives data/behavior wiring. If they conflict (e.g. the mockup shows
   a field the backend doesn't have), ask the user how to resolve it.
7. If no blueprint is provided, skip this step and design the layout from the backend's resource
   shapes alone (Step 6).
8. If the user uploaded blueprint image(s) into the repo for this session, once the UI work is
   complete ask them whether those uploaded image(s) should be deleted, kept where they are, or
   moved somewhere else — don't delete or leave them without asking.

### Step 4 — Ask the user to choose a stack (new apps only)

- **If Step 2 already detected an existing stack, skip this step** — continue in that stack.
- **If this is a brand-new app**, the skill MUST ask the user to choose a stack before scaffolding
  anything — never default or silently pick one. Use `ask_user` with the three options below, each
  labeled with its trade-off:

  - "React + Redux Toolkit + Tailwind v4 + Radix-primitive components — matches
    `visual-pipeline-and-platform-evaluation-tool/ui`; richest component set (tables, forms,
    charts, resizable panels), best for a full-featured product-grade app"
  - "React + Redux Toolkit + plain CSS, custom components — matches
    `education-ai-suite/smart-classroom/ui`; no UI-kit dependency, good when you want full control
    over every component's markup/CSS or need i18n"
  - "Vanilla JS (no build step), served by your Python backend — matches
    `live-video-analysis/live-video-captioning`; lightest weight, no Node/npm pipeline, good for an
    operational/video dashboard tightly coupled to a FastAPI/Flask backend"

  Also offer an "I'm not sure — recommend one for my use case" option; only in that case may the
  agent suggest a stack, and it must say which one and why (using the inferred use case from Step
  2 and `references/stack-and-scaffolding.md`'s resolution order) rather than silently applying it.
- Do not proceed to Step 5 until the stack is either detected or confirmed by the user.

### Step 5 — Load the shared design system

Read, in full, before generating any code:

- `references/design-tokens.md` — color palette (each reference stack's own Intel-blue-family
  accent + shared status colors), typography, spacing/radius/shadow tokens, light/dark variants.
- `references/component-library.md` — canonical components (Header, Sidebar, StatCard, Card,
  Button, Table, Modal, Badge/status pill, Toast) with where each pattern is used in the three
  reference apps and a copy-ready snippet.
- `references/layout-patterns.md` — the recurring page shells drawn from the three reference apps:
  **App Shell** (sidebar + header), **Dashboard Grid**, and **Split Panel**.

### Step 6 — Create a wireframe and get explicit approval before any code

**This is a hard gate: do not start Step 7 until the user has explicitly approved a wireframe.**
Read `references/wireframing.md` in full and follow it:

1. Ask the user whether they want the wireframe as a **draw.io/diagrams.net** file (recommended,
   no account needed) or via **Figma/FigJam** — explain up front that Figma's REST API cannot
   create/edit design nodes directly, so the Figma path means importing the generated `.drawio`
   file into FigJam via Figma's "diagrams.net" plugin, not a direct push.
2. Resolve the layout pattern (reusing `layout-patterns.md` → "Choosing a layout for a new
   resource", driven by Step 2's backend resource shapes and/or Step 3's blueprint mapping) and
   enumerate the concrete regions/components to place:
   - **Existing app**: read its current component tree/routes/CSS regions and reflect what's
     actually live today — the wireframe must match the real app, not an idealized redesign.
   - **New app**: lay out boxes from the chosen layout pattern + the backend resources/fields from
     Step 2 and the blueprint region mapping from Step 3 (if provided).
3. Generate the `.drawio` file (neutral/gray placeholder boxes, one labeled box per
   component/region — see the shape-mapping table in `wireframing.md`), tell the user where it is
   and how to open/edit it, and iterate on that same file through as many rounds of feedback as
   needed.
4. Only once the user gives explicit approval ("approved", "looks good, build it", etc.) may you
   proceed to Step 7, using the approved box layout/component list as the authoritative structure
   — Step 7 must build to match it, not redesign it.

### Step 7 — Scaffold and build the UI

Copy the matching template directory for whichever stack was detected or chosen in Step 4:

```bash
# Stack A: React + Redux Toolkit + Tailwind v4 + Radix-primitive (shadcn-style) components
cp -r .github/skills/ui-ux-builder/assets/templates/react-tailwind-shadcn/* <target-ui-dir>/
cd <target-ui-dir> && npm install
# add further shadcn-style primitives on demand, e.g.:
npx shadcn@latest add table dialog tabs badge
```

For stack B (React + Redux Toolkit + plain CSS) or stack C (vanilla JS, no build step), there is no
copy-paste template — follow the scaffolding commands and conventions in
`references/stack-and-scaffolding.md` §B/§C instead.

Then, using the use case from Step 2, the layout from Step 3 (if a blueprint was given), and the
**approved wireframe from Step 6**:

1. Rename the app (`package.json` name, `index.html` title, Header brand text) to the target app.
2. Build the regions/components exactly as placed in the approved Step 6 wireframe (list/
   collection → **Dashboard Grid**, stat cards + table; single live resource → **Split Panel**;
   everything else → **App Shell** page with a form/detail view) — do not silently change the
   approved structure; if something in it turns out to be impractical once you start building,
   stop and go back to the user/Step 6 rather than quietly deviating.
3. Generate a thin `services/api.*` (or `api/request.ts`) client with one function per real
   endpoint found in Step 2 — never fabricate endpoints or fields.
4. Use the shared Intel-blue primary accent (see design-tokens.md "Suite accent colors" table) —
   do not invent a different primary brand color. Only add a secondary, purely semantic accent on
   top (e.g. a status/category color) if the use case genuinely needs one beyond success/warn/error;
   ask the user before introducing one rather than assuming. Keep the same neutral/background/status
   tokens so the app still *feels* consistent.
5. Add SPDX headers (`SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
   `SPDX-License-Identifier: Apache-2.0`) to every new source file.
6. **When restructuring an existing template/page rather than scaffolding a new one**, first grep
   the existing JS/tests for every element ID, class, and selector they depend on (e.g.
   `getElementById`, `querySelector`, test assertions on structure). After rewriting the markup,
   verify each one still appears — exactly once — so no existing script silently breaks from a
   missing or duplicated ID/class.
7. Once the UI is built, follow `wireframing.md`'s cleanup step: ask the user whether the
   wireframe file should be kept in the repo, moved, or deleted — same handling as blueprint images
   in Step 3.

### Step 8 — Validate

- `npm run build` (or `npm run lint` if build requires unavailable infra) must pass before finishing.
- If the app has an existing test suite (pytest, vitest, jest, etc.), run it **before** making
  changes to capture a baseline, then again after — confirm no new failures/regressions versus
  that baseline (pre-existing failures unrelated to this work may remain, but note them as
  pre-existing rather than silently ignoring them). Add tests for any new routes/components you
  introduced where the existing suite has a pattern for it.
- Confirm no hard-coded secrets, and that any new `.env` usage follows `.env.example` conventions.
- Spot-check that the new UI matches the shared design tokens (no ad hoc colors outside the palette)
  and that SPDX headers are present on new files.
- Summarize for the user: detected/chosen stack, the approved wireframe and its final location
  (kept/moved/deleted per their choice), resources wired, any backend-data gaps flagged and how
  they were resolved (stubbed/implemented/deferred), test results versus baseline, and any open
  questions you asked along the way. If migration from a non-reference stack happened earlier in
  this task, note that in the summary too.
- After presenting that summary, explicitly ask the user whether this covers everything or whether
  they need further UI/UX assistance (another screen, a tweak, a different blueprint, etc.). Keep
  asking this after each follow-up round until the user confirms they're done — never assume a
  single pass is the end of the engagement.

