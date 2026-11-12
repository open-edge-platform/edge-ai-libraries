<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# App UI (React + Redux Toolkit + plain CSS)

Scaffolded by the `unified-ui-ux-builder` skill from the `react-redux-plain-css` template (Stack B),
matching `education-ai-suite/smart-classroom/ui`. Replace this file's content once the app has a
real name/description.

## Quick start

```bash
npm install
cp .env.example .env   # set VITE_API_BASE to the backend URL for local dev
npm run dev            # starts Vite on a local port, proxies /api to VITE_API_BASE
```

```bash
npm run build           # tsc -b && vite build, production build to dist/
npm run lint            # eslint
```

Optional, only if the app needs multi-language:

```bash
npm install i18next react-i18next
```

## Structure

- `src/services/api.ts` — thin axios wrapper; add one function per real backend endpoint here,
  never call `axios`/`fetch` directly from components.
- `src/redux/slices/` — one hand-written slice per domain concept (`createSlice`, no RTK Query).
- `src/index.css` — shared design tokens (`--font-display`, `--color-theme`, `--control-*`). Don't
  hand-pick one-off colors; see the skill's `references/design-tokens.md`.
- `src/components/common/` — shared components (e.g. `Accordion`), each with its own `.css` file.
  No CSS-in-JS, no Tailwind, no UI-kit dependency — plain CSS per component, matching the
  reference app.

## Conventions

- Every new source file needs an SPDX header:
  `SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
  `SPDX-License-Identifier: Apache-2.0`.
- Never commit `.env` — only `.env.example` is tracked.
- No path alias — relative imports throughout, matching the reference app.
