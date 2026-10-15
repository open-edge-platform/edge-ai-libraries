<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Wireframing — the approval gate before any code is written

- Hard gate: a low-fidelity, drag-and-drop-editable wireframe must be **explicitly approved by the
  user** before Step A.7 (Scaffold and build) starts.
- Existing app → wireframe reflects the *current* UI. New app → wireframe represents the *proposed*
  UI.
- Never skip straight to scaffolding because the layout "seems obvious" — diagram feedback is
  cheap; app code is not.

## 1. Ask which tool the user wants

Use `ask_user` — never assume:

- **draw.io / diagrams.net** (recommended):
  - Generates a `.drawio` (mxGraph XML) file directly.
  - No account needed: draw.io desktop app, https://app.diagrams.net (File > Open), or the VS Code
    "Draw.io Integration" extension.
  - Fully drag-and-drop editable immediately after generation.
- **Figma / FigJam**:
  - Same `.drawio` file is generated — it cannot be pushed into a live Figma file directly (the
    Figma REST API has no endpoint to create/edit design nodes).
  - User imports it into a FigJam board themselves via Figma's free "diagrams.net" plugin.
  - Tell the user this limitation **before** they choose — don't silently generate a draw.io file
    after they asked for Figma without explaining why.

## 2. Determine the layout and component list to draw

- Resolve the layout pattern: `layout-patterns.html` → "Choosing a layout for a new resource"
  (driven by backend resource shapes from Step A.2 and/or the blueprint mapping from Step A.4). If
  it's
  not obvious, ask the user — don't guess.
- **Existing app, no blueprint**: read its current component tree (JSX/template structure, routes,
  CSS grid/flex regions actually rendered). Enumerate the real regions/component instances (Header,
  Sidebar, Card, Table, etc.) with approximate nesting/position. The wireframe must match what's
  live today — don't invent or "improve" structure at this stage.
- **Existing app, blueprint provided**: read the current component tree first (as above), then for
  the region(s) the blueprint covers, lay out boxes from the backend resources/fields (Step A.2)
  and the blueprint's region mapping (Step A.4) — same as a new app. Slot these into the existing
  layout/nav structure rather than discarding it; untouched existing regions still reflect what's
  live today, not a redesign.
- **New app**: lay out boxes region-by-region using the chosen layout pattern, the backend
  resources/fields (Step A.2), and the blueprint's region mapping (Step A.4, if provided).
- Map each element to a neutral, labeled box — gray/placeholder-styled, not final brand colors
  (this stage reviews *structure*, not visual polish):

| Component (`component-library.md`) | drawio shape | Label convention |
|---|---|---|
| Header | full-width rectangle, fixed height | `Header: <title/brand>` |
| Sidebar / nav | fixed-width rectangle, full height | `Sidebar: <nav items>` |
| Card / StatCard | rounded rectangle | `Card: <content summary>` |
| Table | rectangle with horizontal rule lines | `Table: <columns>` |
| Button | small rounded rectangle | `Button: <action>` |
| Form / input | rectangle with an underline | `Input: <field name>` |
| Status pill / badge | small ellipse | `Status: <value>` |
| Chart | rectangle, hatch/chart fill pattern | `Chart: <metric>` |
| Video / stream preview | rectangle, play-icon style | `Live: <stream name>` |
| Toast / modal / slide-over | dashed rectangle, floating | `Modal: <purpose>` |

## 3. Generate the `.drawio` file

- Location: `<target-ui-dir>/../wireframes/<app-name>-wireframe.drawio` (ask the user if they'd
  prefer a different path).
- Start from this minimal mxGraph skeleton; add one `mxCell` per enumerated region/component from
  step 2, positioned per the chosen layout pattern's grid:

```xml
<mxfile>
  <diagram name="Wireframe">
    <mxGraphModel>
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="header" value="Header: App Name" parent="1" vertex="1"
                style="rounded=0;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#999999;">
          <mxGeometry x="0" y="0" width="800" height="60" as="geometry" />
        </mxCell>
        <!-- one mxCell per region/component, following the shape table above -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## 4. Review and iterate until approved

- Tell the user exactly where the file is and how to open/edit it (see tool options above). They
  may drag/resize/add/remove boxes directly in the tool, or describe changes in chat for the skill
  to apply to the same XML file.
- Update the **same** file on every round of feedback — never generate a new file per round.
- Do not proceed to Step A.7 until the user gives **explicit** approval (e.g. "approved", "looks
  good, build it"). If the response is ambiguous, ask directly — never assume approval.
- Once approved, the box layout/component list is the authoritative structure for Step A.7 —
  build to
  match it, don't redesign on the fly.
- After the UI is built (Step A.8), ask the user whether the wireframe file should be kept in the
  repo (e.g. under `docs/wireframes/`), moved, or deleted — same handling as blueprint images in
  Step A.4.

## Figma/FigJam specifics

- The Figma REST API (`api.figma.com`) only reads file contents/metadata/variables and posts
  comments — there is **no endpoint to create or edit frames/nodes**. Pushing a wireframe directly
  into a live Figma file isn't possible without a running Figma plugin, which this skill cannot
  install or execute.
- Supported path: generate the `.drawio` file, then the user imports it into a FigJam board
  themselves via Figma's free "diagrams.net" plugin (Import → draw.io diagram).
- Optional: if the user already has their own Figma Personal Access Token and a specific file to
  flag, the skill may POST a short text comment summarizing the proposed structure via the Comments
  API. Never store or log the token — this is a pointer only, not a substitute for the wireframe
  review itself.
