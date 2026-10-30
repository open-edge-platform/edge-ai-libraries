<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Example: Analyse/audit an existing UI against the unified UI benchmarks (Scenario 3 — Mode B)

> Applies to any existing app/domain, in any OEP repo. Key behaviors: (a) this mode is read-only —
> no code, wireframe, or scaffolding changes happen in it; (b) the user must pick which page(s) to
> audit before anything is checked; (c) findings are severity-ranked (compliant / moderate /
> critical), not a flat list; (d) the report ends with a short, carry-forward "gap summary" meant
> to be pasted back in to drive a future Mode A update.

> Analyse the UI in `predictive-maintenance-suite/machine-health-monitor/ui`
> against the unified UI benchmarks — tell me what's drifted and how bad it is.

Expected agent behavior (`SKILL.md` Mode B, Steps B.1–B.4):

1. **Step B.1 — Path + stack**
   - Confirm target path if ambiguous.
   - Read `package.json`/src tree/theme CSS; auto-detect stack.
   - Matches a reference stack (say Stack A) → confirm it back to the user, continue.
   - Matches none of the three → say so plainly, explain there's no benchmark to check it against,
     and stop (never improvise benchmarks for a non-reference stack).
2. **Step B.2 — Ask which pages**
   - Enumerate real pages/routes found in the app's router/page directory (e.g. `Dashboard`,
     `Alerts`, `Settings`) — don't guess names.
   - `ask_user`: "All pages" or pick specific ones from the list above.
   - User picks, e.g., `Dashboard` and `Settings` only → confirm the selection before proceeding;
     `Alerts` is not touched.
3. **Step B.3 — Audit each selected page**
   - For `Dashboard`: read its component tree/CSS; compare accent colors, spacing/radius tokens,
     card/table/header structure, and page shell against `design-tokens.md`,
     `component-library.md`, and `layout-patterns.html` for Stack A. Check SPDX headers.
   - For `Settings`: same checks.
   - Classify every finding using `references/ui-audit-report-template.md`'s severity bands:
     - ✅ Compliant — e.g. Header matches the canonical Stack A structure.
     - 🟡 Moderate — e.g. one card's border-radius is `6px` instead of the `8px` token, isolated
       to a single settings row; doesn't need immediate attention.
     - 🔴 Critical — e.g. a custom purple primary button instead of the shared Intel-blue accent,
       repeated across both pages; or a hand-rolled sidebar layout that matches none of the three
       layout patterns.
     - 🔴 **Missing must-have** — the header on both pages has no light/dark theme toggle at all
       (every reference stack has one). Flagged as its own row, labeled "Missing must-have," not
       folded into ordinary critical drift.
   - Don't pad the report with invented findings; if a page is fully compliant, say so.
4. **Step B.4 — Produce the report**
   - One results table per page (`Dashboard`, `Settings`), each with a compliant/moderate/critical
     count.
   - An overall summary table combining both pages.
   - A **carry-forward gap summary**, grouped critical-first, one line per distinct gap (e.g. "the
     custom purple accent" is one line even though it appears on both pages, not two lines).
     Missing must-haves go at the very top of the critical list.
   - Example gap summary lines the user can paste back in later:
     *"[Missing must-have] Add a light/dark theme toggle to the header — absent on Dashboard and
     Settings."*
     *"Replace the custom purple primary accent with the shared Stack A accent token across
     Dashboard and Settings."*
5. **After the report (still Step B.4)**
   - Ask whether the user wants to act on any gaps now (routes into Step A.6's wireframe
     approval gate still applies before anything is built) or just keep the report for later.
   - Never start fixing anything in this mode without the user explicitly asking to move to Mode A.
