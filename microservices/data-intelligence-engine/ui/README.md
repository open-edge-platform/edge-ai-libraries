# Data Intelligence Engine Console

Independent Vue 3 + TypeScript + Vite project. The user-facing chatbot and
settings remain in [app/ui](../../app/ui); Console has no dependency on that
frontend or its development server.

## Develop

Use Node.js 22.18+ and start the engine on port 16022. From this directory:

```shell
npm ci
npm run dev
```

Open `http://localhost:7778/console/`. Vite proxies `/v1/*` and `/health` to
`http://localhost:16022`. Set `DI_ENGINE_PROXY_TARGET` to override the complete
engine URL, or `DI_PROXY_HOST` to change the host while keeping port 16022.
These settings can also be placed in an untracked `.env.local` file.

Console uses the engine's own `/v1/*` APIs directly in production; it does not
need the app service's `/engine-api/` proxy. Chat completion URLs configured
in the playground must be reachable from the browser and allow its origin.

## Structure

- `src/layout/`: `main.vue` composes the header, library scope and routed content
  outlet; `Sidebar.vue` owns the sidebar menu, collapse state and engine status display.
- `src/router/`: history-mode routes relative to the `/console/` base.
- `src/views/`: route directories (`libraries`, `assets`, `pools`,
  `sources`, `databases`, `ModelManagement`, `canvas`, `retrieve`, `chat`, `error`).
- `src/components/`: cross-page UI primitives only (`SvgIcon`, `PartialLoading`,
  `FormTooltip`, `ConsoleTable`, `StatusTag`). Business components belong in
  their owning `src/views/<page>/components/` directory, even when another page
  reuses them through an explicit import.
- `src/api/`, `src/i18n/`, `src/store/`, `src/types/`, `src/utils/`: frontend support.

Child component filenames use PascalCase, including shared components, page
components and layout children (`Header.vue`, `Sidebar.vue`). TypeScript files
inside page and component directories also use PascalCase (`ColumnsList.ts`,
`SourceOptions.ts`). Page entry `index.vue`, layout entry `main.vue` and
infrastructure filenames outside these directories keep their existing names.

## Build and validate

```shell
npm run build
npm run type-check
```

Build output stays in `ui/dist/`. The engine serves it at
`http://localhost:16022/console/`, with fallback for deep links such as
`/console/libraries`. Only build output is exposed, never sources or dependencies.
If it is missing, Console returns HTTP 503 with build instructions; the API
remains available.

The engine Dockerfile builds Console in a Node stage automatically. For Python
wheel packaging, build Console first, then build/install the engine from its
root. The Python build hook copies the compiled UI into the wheel's
`console_ui_dist/` resources next to the backend's `console_ui.py` module,
so an installed wheel does not need Node.js.
Missing frontend output fails wheel creation explicitly.
