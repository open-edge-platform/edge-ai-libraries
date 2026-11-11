<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# App UI (React + Redux Toolkit + Tailwind v4 + Radix/shadcn)

Scaffolded by the `unified-ui-ux-builder` skill from the `react-tailwind-shadcn` template (Stack A),
matching `visual-pipeline-and-platform-evaluation-tool/ui`. Replace this file's content once the
app has a real name/description.

## Quick start

```bash
npm install
cp .env.example .env   # set VITE_API_BASE to the backend URL for local dev
npm run dev            # starts Vite on a local port, proxies /api to VITE_API_BASE
```

```bash
npm run build           # production build to dist/
npm run lint            # eslint
```

Add further shadcn-style primitives on demand:

```bash
npx shadcn@latest add table dialog tabs badge
```

## Structure

- `src/services/api.js` — thin fetch wrapper; add one function per real backend endpoint here,
  never call `fetch` directly from components.
- `src/index.css` — shared design tokens (colors, radius) under `:root`/`.dark`. Don't hand-pick
  one-off colors; see the skill's `references/design-tokens.md`.
- `src/components/ui/` — shadcn-style primitives (button, card, etc.), added via
  `npx shadcn@latest add <component>`.
- `src/lib/utils.js` — `cn()` class-merging helper.

## Conventions

- Every new source file needs an SPDX header:
  `SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
  `SPDX-License-Identifier: Apache-2.0`.
- Never commit `.env` — only `.env.example` is tracked.
