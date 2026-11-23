<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# App UI (Vanilla JS, no build step)

Scaffolded by the `unified-ui-ux-builder` skill from the `vanilla-js` template (Stack C), matching
`live-video-analysis/live-video-captioning`. Replace this file's content once the app has a real
name/description.

## Quick start

No Node/npm pipeline — serve this folder directly from the existing Python backend:

```python
# FastAPI
app.mount("/", StaticFiles(directory="ui", html=True), name="ui")

# Flask
app.static_folder = "ui"
```

The client calls the API via a relative path (`/api/...`), same-origin as the backend — no
`.env`/build-time configuration needed.

## Structure

- `js/services/api.js` — thin `fetch`-based API client; add one function per real backend
  endpoint here, never call `fetch` directly from components.
- `js/services/stream.js` — `EventSource` (SSE) client with reconnect-with-backoff; prefer this
  over polling for live data.
- `js/utils/theme.js` — `ThemeManager` IIFE; toggles `[data-theme="light"|"dark"]` and persists to
  `localStorage`.
- `js/components/` — small IIFE-module components (e.g. `status-dot.js`).
- `css/styles.css` — shared design tokens as CSS custom properties under `:root` (dark default) /
  `[data-theme="light"]`. Don't hand-pick one-off colors; see the skill's
  `references/design-tokens.md`.
- `index.html` — loads `js/*.js` as plain `<script>` tags in dependency order (utils → services →
  components → app.js). No bundler, no ES module imports — keep this convention when adding files.

## Conventions

- Every new source file needs an SPDX header:
  `SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
  `SPDX-License-Identifier: Apache-2.0`.
- Keep each `.js` file a self-contained IIFE exposing only what other scripts need.
