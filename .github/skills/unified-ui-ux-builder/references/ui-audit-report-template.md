<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UI Audit Report Template

Used by `SKILL.md` **Mode B — Analyse/Audit** to report how far an existing page/component has
drifted from the shared design system (`design-tokens.md`, `component-library.md`,
`layout-patterns.html`). Read-only: this report never changes code.

## Severity bands

| Band | Meaning | Example |
|---|---|---|
| ✅ **Compliant** | Matches the reference token/component/pattern, or an already-approved, recorded override. | Uses the stack's shared Intel-blue accent and the canonical Header structure. |
| 🟡 **Moderate drift** | Noticeably off the reference but not urgent — cosmetic, low-visibility, or a single isolated spot. Doesn't need immediate attention. | A card uses a slightly different border-radius value than the token; one-off spacing on a rarely-seen settings row. |
| 🔴 **Critical drift** | Far from the reference — wrong accent family, a hand-rolled component where a canonical one exists, a layout shell that doesn't match any of the three patterns, missing SPDX header, or a pattern repeated across many places. | A custom purple primary button instead of the shared accent; a bespoke sidebar+header shell instead of the App Shell pattern. |
| 🔴 **Missing must-have** | A special case of critical: one of `SKILL.md`'s "Must-have baseline elements" (theme toggle, SPDX headers, thin API/services layer, canonical page shell, status colors) is **absent entirely**, not just styled differently. Always flagged, always critical, always called out separately from ordinary drift. | No light/dark theme toggle anywhere in the page/header; no SPDX header on any file. |

Bands are about **distance from the reference and user impact**, not just "is it different" — an
isolated one-off difference is moderate; a difference that recurs across the page/app, or breaks
recognizability as part of the product family, is critical. A missing must-have is always critical
regardless of how isolated it looks, because every reference stack has it.

## Report structure

For each page/component audited, produce:

```markdown
### Page: <name/route>

| # | Area | Benchmark reference | Found | Status | Note |
|---|------|---------------------|-------|--------|------|
| 1 | Primary accent color | design-tokens.md § Stack A Suite accent | `#6d28d9` (custom purple) | 🔴 Critical | No shared-accent token in use; replace with `--accent-primary`. |
| 2 | Card border-radius | design-tokens.md § radius scale | `6px` vs token `8px` | 🟡 Moderate | Cosmetic, low-visibility card on the settings page only. |
| 3 | Header structure | component-library.md § Header (Stack A) | Matches canonical structure | ✅ Compliant | — |
| 4 | Page shell | layout-patterns.html § App Shell | Custom flex layout, no sidebar | 🔴 Critical | Doesn't match any of the 3 reference layout patterns. |
| 5 | Theme toggle | SKILL.md § Must-have baseline elements | Not found anywhere in header/page | 🔴 Critical | **Missing must-have** — every reference stack has a light/dark toggle. |
| 6 | SPDX headers | licensing requirement | Present on all files | ✅ Compliant | — |
```

Rows cover at minimum: accent/status colors, typography, spacing/radius/shadow tokens, component
structure (header, nav, cards, tables, forms, buttons), layout shell pattern, SPDX headers. Add
rows for anything else that's checkable against the three reference docs — don't pad the table
with rows that have nothing to compare against.

## Per-page summary

After each page's table, one line: `**<N> compliant, <N> moderate, <N> critical**`.

## Overall summary (all pages audited)

```markdown
## Overall summary

| Page | Total components | ✅ Compliant | 🟡 Moderate | 🔴 Critical | % Compliant |
|------|------------------:|-------------:|------------:|------------:|------------:|
| Dashboard | 9 | 6 | 2 | 1 | 67% |
| Settings  | 7 | 4 | 3 | 0 | 57% |
| **Total** | **16** | **10** | **5** | **1** | **63%** |
```

`Total components` = rows audited on that page; `% Compliant` = Compliant ÷ Total components,
rounded. This lets pages
of different sizes be compared fairly instead of relying on raw counts alone.

## Carry-forward gap summary

A short, copy-pasteable block the user can hand back next time to say "update the UI based on
these gaps." Group by severity, most critical first, one line per distinct gap (not per
occurrence) — a recurring issue across many components is one line, not N lines:

```markdown
## Gap summary (carry forward to next update)

**Critical:**
- **[Missing must-have]** Add a light/dark theme toggle to the header — every reference stack has
  one and it's currently absent on Dashboard and Settings.
- Replace custom purple primary (`#6d28d9`) with the shared Stack A accent token across
  Dashboard and Settings.
- Rebuild the page shell to match the App Shell pattern (sidebar + 60px header) instead of the
  current custom flex layout.

**Moderate:**
- Align card border-radius to the `8px` token on the Settings page.
- Settings form uses native `<select>` instead of the canonical Radix Select component.
```

Only list what was actually found — never pad this section to seem thorough, and never include
✅ compliant items here.
