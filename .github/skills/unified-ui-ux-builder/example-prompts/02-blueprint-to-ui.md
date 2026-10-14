# Example: Generate a UI from a blueprint image + backend code

> Like example 1, this is illustrative only — the same steps apply to a blueprint for any domain
> (predictive maintenance, retail, robotics, etc.) and to apps in edge-ai-suites, edge-ai-libraries,
> or any other OEP repo. Step 2 (auto-detect an existing stack) is the key generalizable behavior
> here: the agent never reintroduces a different stack just because the mockup looks "modern."

> Here's a mockup of the dashboard we want (attached image). The backend is in
> `health-and-life-sciences-ai-suite/vitals-tracker/services/`. Build the
> frontend to match the mockup and wire it to this backend.

Expected agent behavior (follows `SKILL.md` Steps 1–8 in order):

1. **Step 1 — path.** The backend path was given (`.../vitals-tracker/services/`), but the agent
   still confirms the actual UI target directory with the user if it's not obvious (e.g.
   `vitals-tracker/ui` doesn't exist yet) rather than assuming where the frontend should live.
2. **Step 2 — use case + backend.** Reads the backend code, enumerates real endpoints/fields (e.g.
   a patient/vitals collection, a live-reading stream), and states its understanding of the use
   case back to the user. It does not invent vitals fields that aren't in the backend — if a field
   is ambiguous it asks. If a UI already exists in this app, it auto-detects the stack here (no
   prompt needed).
3. **Step 3 — blueprint analysis.** Views the attached image; identifies regions (header with logo
   + patient selector, left vitals list, right live chart area, bottom alert banner) and component
   types (cards, line charts, status badges), then maps them onto `references/layout-patterns.md`
   — this matches the **Split Panel** pattern (left control/list panel, right live content) — and
   onto component patterns in `references/component-library.md`, planning to recreate it as closely
   as the React + Redux + plain-CSS stack allows. Suppose the mockup shows a draggable, resizable
   multi-chart grid — the agent explicitly tells the user: "the drag/resize grid in the mockup
   isn't something this stack has a ready pattern for; I'll build a fixed-layout equivalent with
   the same charts instead, or if you want true drag/resize, a React+Tailwind+shadcn rebuild (with
   a grid library) would support it — let me know if you'd like to switch stacks for that." It does
   not silently drop or fake the feature.
4. **Step 4 — stack.** Since `health-and-life-sciences-ai-suite` apps already use the React +
   Redux Toolkit + plain CSS stack, Step 2's auto-detection already resolved this — the agent
   continues in that stack and does **not** ask the user to choose, and does not introduce
   shadcn/Tailwind into this suite just because the mockup looks "modern." (If the user instead
   opts to switch stacks per the Step 3 callout, this is revisited here.)
5. **Step 5 — design system.** Loads `references/design-tokens.md` (status colors for vitals
   alerts, Intel-blue accent) and applies those instead of the mockup's literal pixel colors,
   unless the user explicitly asked for exact color fidelity.
6. **Step 6 — wireframe approval.** Before writing any code, asks whether the user wants the
   wireframe as a draw.io file or via FigJam (explaining the FigJam import caveat), then generates
   a `.drawio` file laying out the Split Panel regions/components identified in Step 3 (left vitals
   list, right live chart area, bottom alert banner). Iterates on that file with the user until they
   explicitly approve it — only then moves to Step 7.
7. **Step 7 — build.** Builds the pages/components exactly per the approved wireframe's Split Panel
   layout, wires them to the backend via a `services/api.ts` client with one function per real
   endpoint, adds SPDX headers.
8. **Step 8 — validate.** Runs `npm run build`, then summarizes the stack used (auto-detected),
   the approved wireframe and what happened to its file, the layout pattern applied, the resources
   wired, and any open questions.
