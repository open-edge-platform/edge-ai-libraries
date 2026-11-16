<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example: Build a new app's UI from scratch (Scenario 1 — new app)

> Build the UI for a new app called "Fleet Health Monitor" under
> `metro-ai-suite/fleet-health-monitor/ui`. The backend exposes REST endpoints
> `/api/vehicles`, `/api/alerts`, and `/api/telemetry/{vehicle_id}`
> (see `metro-ai-suite/fleet-health-monitor/backend/routes.py`). It should look
> and feel consistent with the rest of the repo.

Expected agent behavior (`SKILL.md` Steps A.1–A.8):

1. **Path** — confirm target path; no `ui/` exists yet → new app, not an edit.
2. **Use case + backend**
   - Check OpenAPI spec/docs first; read route source only if missing.
   - Enumerate real endpoints/fields (`/vehicles`, `/alerts`, `/telemetry/{vehicle_id}`).
   - State inferred use case back to the user; never invent fields.
3. **Stack** — brand-new app → `ask_user` with the 3 stack options + "recommend one"; never
   assume. Must be resolved before blueprint analysis (Step A.4), since component mapping depends
   on it.
4. **Blueprint** — ask if one exists; none → ask if the user wants to describe the layout in
   text; neither given → build from `layout-patterns.html` + `component-library.md` +
   `design-tokens.md` + the chosen stack's `assets/templates/` starter, using the backend's
   resource shapes alone, not an invented layout/styling/structure.
5. **Design system** — load `design-tokens.md` / `component-library.md` / `layout-patterns.html`
   for the chosen stack.
6. **Wireframe (hard gate)**
   - `/vehicles` + `/alerts` → Dashboard Grid (stat cards + table).
   - `/telemetry/{vehicle_id}` → Split Panel (picker + live charts).
   - Ask draw.io vs. Figma/FigJam; generate `.drawio`; iterate on the same file.
   - **No code until the user explicitly approves it.**
7. **Build** — only after approval:
   - Copy the chosen template; rename app (`package.json`, `index.html`, Header, `README.md`).
   - Keep shared tokens in `src/index.css`.
   - Build exactly to the approved wireframe.
   - Add one `src/services/api.js` function per real endpoint.
   - SPDX header on every new file.
8. **Validate**
   - `npm install && npm run build` must pass.
   - Summarize: stack, wireframe location, resources wired.
   - Ask if more UI/UX work is needed.
