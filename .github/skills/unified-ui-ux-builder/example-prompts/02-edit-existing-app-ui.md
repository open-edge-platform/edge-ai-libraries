<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example: Add a feature to an existing app's UI (Scenario 2 — edit/modify existing app)

> Applies to any existing app/domain, in any OEP repo. Key behaviors: (a) auto-detect and extend
> the existing stack in place — never redesign or switch stacks unasked; (b) a blueprint image and
> plain-text instructions are equally valid ways to request an edit.

> Add an alerts panel showing active equipment alerts to the dashboard in
> `predictive-maintenance-suite/machine-health-monitor/ui`. The backend already
> exposes `/api/alerts` (see
> `predictive-maintenance-suite/machine-health-monitor/backend/routes.py`).

Expected agent behavior (`SKILL.md` Steps A.1–A.8):

1. **Path** — confirm target path if ambiguous.
2. **Analyze existing UI first**
   - Read `package.json`/src tree/theme CSS; auto-detect stack.
   - Matches a reference stack → confirm back to the user which one (Stack A/B/C) before
     continuing — don't ask the user to choose, just state the match.
   - Read current component tree/routes to locate the live dashboard page.
   - Check OpenAPI spec/docs first for `/api/alerts`; read route source only if missing.
   - Enumerate real fields; never invent a severity/field the backend doesn't return.
3. **Stack** — already resolved in Step A.2 → skip, no `ask_user` prompt.
4. **Blueprint** — ask if one exists for the new panel.
   - None → `ask_user` if the user wants to describe the panel in text; neither given → design from the
     backend shape + existing page layout, using `layout-patterns.html` + `component-library.md` + `design-tokens.md` for the new region — not an invented layout/styling.
   - **Image provided** → map only the covered region(s) to the *already-detected* stack's
     patterns; keep untouched regions exactly as they are today; flag anything the stack can't
     faithfully build, and any backend-data gap, separately — never silently approximate or
     switch stacks.
   - **Must-have check** — while reading the existing header/page (Step A.2) and the blueprint, this
     app turns out to have no light/dark theme toggle — a must-have every reference stack has. Flag
     it to the user explicitly (separate from the new alerts-panel work), `ask_user` whether to add
     it in this same pass or skip it for now; skipping it → note as an open gap in the Step A.8
     summary, don't drop it silently.
5. **Design system** — reuse the existing app's exact accent/status-pill/card patterns; no new
   colors or components for this feature.
6. **Wireframe (hard gate)**
   - Add one new labeled box for the alerts panel into the current `.drawio`/live layout.
   - Every other existing region stays as-is — not redesigned.
   - Ask draw.io vs. Figma/FigJam; iterate on the same file.
   - **No code until the user explicitly approves it.**
7. **Build** — only after approval:
   - Build only the new alerts panel component, matching the approved wireframe.
   - Add one function to the **existing** `src/services/api.js` — no second API client.
   - Reuse the existing shared status-pill component.
   - Grep existing JS/tests for IDs/classes/selectors before touching markup; verify none break.
   - SPDX header on new files only; existing files keep theirs.
8. **Validate**
   - Run the existing test suite before and after the change; confirm no new regressions.
   - `npm run build` must pass.
   - If the app runs via `docker/docker-compose.yml`, ask whether to rebuild/recreate that
     container — never rebuild silently.
   - Summarize: stack (unchanged), wireframe location, resource wired, test results vs. baseline.
   - Ask if more UI/UX work is needed.
