# Layout Patterns

Page shells drawn **only** from the three reference apps (see `SKILL.md` "Survey of the repo").
Pick the closest match instead of designing a new page structure from scratch.

> **Ask, don't assume:** the table at the bottom maps common resource shapes to a layout, but real
> backends often expose more than one shape (e.g. a collection *and* a live stream). If it's not
> obvious which should be the primary landing view, ask the user rather than guessing — the wrong
> choice here is expensive to redo later.

## 1. App Shell — sidebar + header + routed content (Stack A)

Source: `visual-pipeline-and-platform-evaluation-tool/ui/src/components/Layout.tsx` + `Navigation.tsx`.

```
+--------+----------------------------------------------------+
| Side   | Header: sidebar-trigger | separator | page title    | theme toggle
| bar    +----------------------------------------------------+
| (icon, |  Main content (React Router <Outlet/>, scrollable)  |
|  nav)  |                                                      |
+--------+----------------------------------------------------+
  Toaster (top-center) + a persistent "background jobs" widget overlay the whole shell.
```

- Sidebar is collapsible to icon-only; active nav item gets a `border-r-3` brand-colored accent.
- Header is a fixed 60px bar.
- Main content area is `flex h-full overflow-auto` — each route owns its own internal scrolling.
- Use for any stack-A app with more than one page/section; don't add a sidebar to a single-page app.

## 2. Dashboard Grid — content + side info panel (Stack A "Home" page)

Source: `visual-pipeline-and-platform-evaluation-tool/ui/src/pages/Home.tsx`.

```
+-----------------------------------------------------+------------------+
| flex-1 overflow-auto, p-4, space-y-8:                 | w-86 border-l,  |
|   section 1 (e.g. summary cards)                      | p-4, bg-sidebar |
|   section 2 (e.g. list/table)                         | (secondary info |
|   ...                                                 | / quick stats)  |
+-----------------------------------------------------+------------------+
```

- Left/main region: `flex-1 overflow-auto`, `p-4` page padding, `space-y-8` vertical section
  rhythm.
- Right region: fixed-width (`w-86`) `border-l`, sidebar-tinted background — use for secondary,
  glanceable info (quick stats, recent items), not primary content.
- This is the default shape for a stack-A "overview/operations" landing page.

## 3. Dashboard with left panel + live right panel (Stack B)

Source: `education-ai-suite/smart-classroom/ui/src/components/common/Body.tsx`.

```
+-----------------------------------------------------+
| TopPanel (screen switcher) + conditional HeaderBar    |
+------------------+------------------------------------+
| .left-panel       | .right-panel-slot (flex: 1)         |
| (content/controls)| (analytics/results, collapsible     |
|                    |  via a center "▶/◀" arrow divider)  |
+------------------+------------------------------------+
| Footer                                                |
+-----------------------------------------------------+
  ReportPanel / HistoryPanel slide over the whole workspace from the side when opened.
```

- No URL routing — screens are controlled by a local `activeScreen` state union
  (`'main' | 'content-search' | 'grading' | ...`); tool/full-screen states replace the body
  entirely rather than navigating to a new route.
- Right panel is collapsible via a draggable divider with an arrow affordance
  (`usePanelDividerX` hook); collapses to `flex: 0`.
- Responsive breakpoint: `@media (max-width: 900px)` stacks `.main-content` to a single column.
- Reports/history are slide-over panels (`z-index` reserved: header `50`, toast `1100`, video
  `1000`, modal `9999`), not separate pages.
- Use this shape for any stack-B app centered on "process something, then show results alongside
  it" (upload → transcript/summary/mindmap tabs, in the reference app).

## 4. Split Panel — config/control card + live preview (Stack C)

Source: `live-video-captioning/app/ui/index.html` + `styles.css` (`.panels` grid).

```
+-----------------------------------------------------+
| <header class="topbar">: title | device/capability    |
| cards | chat toggle | theme toggle                    |
+------------------+------------------------------------+
| <article class="card">: left   | <article class="card  |
| config form (controls) +       | live-layout">: runs/   |
| nested system-stats-card       | video/caption panels,  |
|                                | empty-state hint        |
+------------------+------------------------------------+
```

- CSS grid: `grid-template-columns: minmax(300px, 27%) minmax(0, 1fr);` — left column is a fixed
  ~27% minimum-300px config/stats panel, right column takes the remaining space and is the primary
  visual focus (video + captions).
- Right side renders dynamically generated run cards (one per active session/stream); shows an
  `.empty-alert` hint when nothing is running yet.
- An optional slide-over chat panel (RAG assistant) docks from the right, toggled by a header
  button, built as `<section class="chat-panel">` with a backdrop + dialog + iframe, not a modal
  library.
- Use for any stack-C app centered on a live feed, recording, or session (video, audio, sensor
  stream) with configuration controls alongside it.

## Responsive rules (apply across all three)

- Stack A: sidebar collapses to icon-only rather than hiding; main content keeps independent
  scrolling at all widths.
- Stack B: two-panel workspace collapses to a single stacked column below `900px`.
- Stack C: the `.panels` grid's left column has a `minmax(300px, 27%)` floor — below that, consider
  stacking (not documented upstream as a breakpoint, so ask the user if this matters for their
  target devices before inventing one).

## Choosing a layout for a new resource

| Backend resource shape | Stack A | Stack B | Stack C |
|---|---|---|---|
| Collection/list with CRUD (cameras, rules, documents) | App Shell page + Dashboard Grid | Left panel list/table inside the left-panel slot | Config card (left) listing/selecting items |
| Single long-lived session/stream (video, audio, sensor) | Dashboard Grid's main region, or a dedicated route | Right-panel live view (video/transcript) | Split Panel (right side = live run) |
| Multi-page app with distinct sections | App Shell (sidebar nav) | Screen-state switch (`activeScreen`), no router | Not applicable — stack C is single-page; recommend stack A if the app needs to grow multi-page |
| Small single-purpose operational dashboard | Dashboard Grid | — | Split Panel |
