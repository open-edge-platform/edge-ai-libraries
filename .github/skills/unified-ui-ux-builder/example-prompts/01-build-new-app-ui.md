# Example: Build a new app's UI from scratch

> Build the UI for a new app called "Fleet Health Monitor" under
> `metro-ai-suite/fleet-health-monitor/ui`. The backend exposes REST endpoints
> `/api/vehicles`, `/api/alerts`, and `/api/telemetry/{vehicle_id}`
> (see `metro-ai-suite/fleet-health-monitor/backend/routes.py`). It should look
> and feel consistent with the rest of the repo.

Expected agent behavior:

1. Detect that no UI exists yet at the target path, so the agent MUST ask the
   user to choose a stack via `ask_user` — presenting the three options from
   `references/stack-and-scaffolding.md` (React+Redux Toolkit+Tailwind+
   Radix/shadcn, React+Redux Toolkit+plain CSS, vanilla JS) plus an "you pick
   for me" option. It must not silently assume one of the three stacks.
2. Read the backend routes, and map `/vehicles` + `/alerts` to a **Dashboard
   Grid** layout (stat cards for fleet counts/alert counts + a vehicles
   table), and `/telemetry/{vehicle_id}` to a **Split Panel** detail view
   (vehicle picker on the left, live telemetry charts on the right).
3. Before writing any code, ask whether the user wants a draw.io file or
   FigJam (via import) for the wireframe, generate a `.drawio` file laying
   out the Dashboard Grid + Split Panel regions from step 2, and iterate with
   the user until they explicitly approve it.
4. Only after approval, copy `assets/templates/react-tailwind-shadcn` into
   the target directory, rename the app, and keep the shared tokens in
   `src/index.css`, building the approved wireframe's pages exactly.
5. Generate `src/services/api.js` functions for each endpoint and wire the
   generated pages to them.
6. Run `npm install && npm run build` to confirm it compiles before finishing.
