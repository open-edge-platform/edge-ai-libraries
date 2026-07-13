---
name: generate-release-notes
description: 'Generate formatted release notes for a specific folder/module in a repository by comparing two git branches or tags. Use this skill whenever the user mentions release notes, changelog, what changed between branches, version summary, release prep, or wants to document what is new or fixed in a release, especially when they mention a component folder or subproject path. Compares commits and diffs between a base branch or tag and a release branch or tag for the requested folder only, then produces structured Markdown release notes with New, Improved, and Fixed bold-heading sections, bold bullet titles, and an intro summary sentence, following the Time Series Analytics product style. Always use this skill rather than writing release notes freehand.'
license: Apache-2.0
metadata:
  tags: "release-notes changelog"
---

# Generate Release Notes

## When to Use

- Preparing a new release and need formatted release notes
- Comparing changes between two branches (e.g., `main` vs `release-2026.1.0`)
- Summarizing what is new, improved, or fixed in a version
- Appending a new version section to an existing release notes file

## Inputs Required

Before starting, ask the user for these values if not already provided:

| Input | Example | Notes |
|-------|---------|-------|
| **product name** | `Time Series Analytics` | Required |
| **Base branch** | `main`, `release-2026.0` | Required |
| **Release branch** | `release-2026.1.0` | Required |
| **Version number** | `2026.1` | Optional — auto-derived from the release branch name if not provided (see Step 3) |
| **Release month and year** | `June 2026` | Required |
| **Folder path in repo** | `microservices/time-series-analytics` | Required |

> If the user has not specified the product name, ask them:
> "What is the product name to include in the release notes? (e.g., Time Series Analytics)"

---

## Procedure

### Step 1: Gather Git History

Run these commands against the repo being released and scope to the requested folder path:

```bash
# All commits unique to the release branch (no merge commits)
git log <base-branch-or-tag>..<release-branch-or-tag> --oneline --no-merges -- <folder-path>

# Files changed and their change volumes
git diff <base-branch-or-tag>..<release-branch-or-tag> --stat -- <folder-path>

# Full diff for detailed analysis
git diff <base-branch-or-tag>..<release-branch-or-tag> -- <folder-path>
```

If the change volume is large, scope the diff further to key subdirectories under the selected folder:

```bash
git diff <base-branch-or-tag>..<release-branch-or-tag> -- <folder-path>/<path/to/component>
```

### Step 2: Categorize Changes

Group every change into **one** of the three categories below. When in doubt, prefer **Improved** over **New** unless the feature is entirely absent from the base branch.

| Category | What belongs here |
|----------|-------------------|
| **New** | Brand-new features, APIs, components, scripts, or capabilities that did not exist in the base branch |
| **Improved** | Enhancements, refactors, performance improvements, dependency/image upgrades, documentation updates, security patches, renames |
| **Fixed** | Bug fixes and error corrections — omit this section entirely if there are no bug fixes |

**Handling ambiguous changes:**
- **Downgrades or reversals** (e.g., base image rolled back from 24.04 to 22.04, a feature removed): still list under **Improved** if the change was intentional, and describe *why* (e.g., "updated to align with supported baseline"). If the change removes user-visible functionality, note it plainly.
- **Very small changes** (typo fix, single-line config tweak): group several into one bullet rather than listing each separately.
- **Security dependency bumps**: always call out under **Improved** with a `**Security**:` bullet, naming the package and CVE or vulnerability description if known.

### Step 3: Write the Release Notes

Follow the [release notes format template](./assets/release-notes-template.md) exactly.

**Formatting rules:**

- File heading: `# Release Notes: <product_name>` — use the product name supplied by the user (e.g., `# Release Notes: Time Series Analytics`).
- Version heading: `## Version <X.Y>` — always `##`, never `#` or `###`

  **Versioning strategy:** The version number follows the `YYYY.MINOR` scheme where `YYYY` is the calendar year and `MINOR` is the sequential release number within that year (starting at `0`). Derive it from the release branch name by stripping the `release-` prefix and any trailing patch segment (`.0`):
  - `release-2026.0` → `2026.0`
  - `release-2026.1.0` → `2026.1`
  - `release-2026.2.0` → `2026.2`

  MINOR increments sequentially within a calendar year (e.g., `2026.0`, `2026.1`, `2026.2`, …). If the user has not specified the version number, derive it from the release branch using this rule and confirm with the user before writing.

- Date line immediately below: `**<Month Year>**` (bold, on its own line, NOT embedded in the heading)
- One-sentence introductory paragraph that names the **2–4 most significant highlights** in bold inline, ending with `and various fixes and documentation improvements.` (or similar closing clause)
- Each category as a **bold paragraph heading** — write exactly `**New**`, `**Improved**`, `**Fixed**` — these are NOT markdown `##` or `###` headers, just bold text on its own line
- Each bullet: `- **Feature Name**: Description sentence(s).`
  - The bold title is the short name of the feature/change
  - The colon goes **outside** the bold markers: `**Name**:` not `**Name:**`
  - The description follows a colon, starts lowercase (unless a proper noun), and ends with a period
  - Group related small changes into a single bullet rather than splitting into many bullets
- Separate versions with a `---` horizontal rule
- Do NOT include code blocks, tables, bash commands, or environment variable listings in release notes — keep entries high-level and human-readable

**Intro sentence patterns** (choose the one that fits):

```
This release introduces **X**, **Y**, and **Z**, along with various fixes and documentation improvements.

This release introduces **X** and **Y**, along with **updated Z** and **documentation improvements**.
```

### Step 4: Locate or Create the Release Notes File

For a folder-scoped release, the canonical path is:

```
<folder-path>/docs/user-guide/release-notes.md
```

If the file does not exist, create it. If it already exists, **prepend** the new version section above the previous most-recent version entry (do not replace existing content).

### Step 5: Reference Example

The authoritative format example is the existing release notes file for the selected folder:

```
<folder-path>/docs/user-guide/release-notes.md
```

When uncertain about formatting or section structure, re-read that file.

### Step 6: Review with User

After drafting, ask the user to confirm:

1. Are all significant changes captured?
2. Are the categorizations (New / Improved / Fixed) correct?
3. Is the intro summary accurate?
4. Are there any sensitive internal details that should be removed?

Apply any corrections before writing to disk.