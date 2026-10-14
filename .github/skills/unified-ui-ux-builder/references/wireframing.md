# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Wireframing — the approval gate before any code is written

A low-fidelity, drag-and-drop-editable wireframe must be produced and **explicitly approved by the
user** before Step 7 (Scaffold and build) starts — for both an existing app (the wireframe must
reflect its *current* UI) and a brand-new app (the wireframe represents the *proposed* UI). Design
feedback is cheap to iterate on in a diagram; app code is not — never skip straight to scaffolding
because the layout "seems obvious."

## 1. Ask which tool the user wants

Use `ask_user` — never assume:

- **draw.io / diagrams.net** (recommended) — the skill generates a `.drawio` (mxGraph XML) file
  directly; opens with no account in the draw.io desktop app, at https://app.diagrams.net (File >
  Open), or in-editor via the VS Code "Draw.io Integration" extension. Fully drag-and-drop editable
  by the user immediately after generation.
- **Figma / FigJam** — see "Figma/FigJam specifics" below before offering this: the skill still
  produces the same `.drawio` file, but cannot push it into a live Figma file directly (the Figma
  REST API has no endpoint to create/edit design nodes). The user imports it into a FigJam board
  themselves using Figma's free "diagrams.net" plugin.

Tell the user plainly about the Figma limitation *before* they choose, so they aren't surprised —
do not silently generate a draw.io file if they asked for Figma without explaining why that's the
path.

## 2. Determine the layout and component list to draw

1. Resolve the layout pattern using `layout-patterns.md` → "Choosing a layout for a new resource"
   (driven by the backend resource shapes from Step 2 and/or the blueprint mapping from Step 3). If
   it's not obvious which layout fits, ask the user rather than guessing.
2. **Existing app**: read its current component tree (JSX/template structure, routes, CSS grid/flex
   regions actually rendered) and enumerate the real regions/component instances (Header, Sidebar,
   Card, Table, etc.) with their approximate nesting and position. The wireframe must be a true
   reflection of what's live today — do not invent or "improve" structure the user hasn't asked for
   yet at this stage.
3. **New app**: lay out boxes region-by-region using the chosen layout pattern, the resources/
   fields identified from the backend (Step 2), and the blueprint's region mapping (Step 3, if
   provided).
4. Map each element to a neutral, labeled box — keep wireframes gray/placeholder-styled, not final
   brand colors, since this stage reviews *structure*, not visual polish:

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

Save it near the target UI, e.g. `<target-ui-dir>/../wireframes/<app-name>-wireframe.drawio` (ask
the user if they'd prefer a different location), starting from this minimal mxGraph skeleton and
adding one `mxCell` per enumerated region/component from step 2, positioned per the chosen layout
pattern's grid:

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

1. Tell the user exactly where the file is and how to open/edit it (see tool options above). They
   may drag/resize/add/remove boxes directly in the tool, or just describe changes in chat for the
   skill to apply to the same XML file.
2. Update the **same** file on every round of feedback — never generate a new file per round.
3. Do not proceed to Step 7 (Scaffold and build) until the user gives **explicit** approval (e.g.
   "approved", "looks good, build it"). If a response is ambiguous, ask directly rather than
   assuming approval.
4. Once approved, the approved box layout/component list becomes the authoritative structure for
   Step 7 — Step 7 must build to match it, not redesign it on the fly.
5. After the UI is built (Step 8 summary), ask the user whether the wireframe file should be kept
   in the repo (e.g. under `docs/wireframes/`), moved, or deleted — same handling as blueprint
   images in Step 3.

## Figma/FigJam specifics

- The Figma REST API (`api.figma.com`) only supports reading file contents/metadata/variables and
  posting comments — there is **no endpoint to create or edit frames/nodes** in a file. Pushing a
  wireframe directly into a live Figma file isn't possible without a running Figma plugin, which
  this skill cannot install or execute.
- Supported path: generate the `.drawio` file as above, then the user imports it into a FigJam
  board themselves via Figma's free "diagrams.net" plugin (Import → draw.io diagram) to continue
  collaborating on Figma's native canvas.
- Optional lightweight extra: if the user already has their own Figma Personal Access Token and a
  specific file they want flagged, the skill may POST a short text comment summarizing the
  proposed structure via the Comments API — never store or log the token, and this is only a
  pointer, not a substitute for the wireframe review itself.
