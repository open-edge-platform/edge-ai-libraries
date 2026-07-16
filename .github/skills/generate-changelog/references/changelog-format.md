# Changelog Format Reference

This document defines the exact structure and style for `CHANGELOG.md` entries
in the edge-ai-libraries repository. Follow it precisely when generating or updating
the changelog.

---

## File structure

```
# Changelog

All notable changes to this project are documented in this file.

## [<version>] - <Month Year>

### Added
- <Description of new feature or capability.> ([#NN])

### Changed
- <Description of change to existing behavior.> ([#NN])

### Removed
- <Description of removed feature or functionality.> ([#NN])

### Fixed
- <Description of bug fix.> ([#NN])

### Security
- <Description of security fix or dependency bump.> ([#NN])

### Documentation
- <Description of docs-only change.> ([#NN])

---
[#NN]: <repo_url>/pull/NN
[abcdef]: <repo_url>/commit/abcdef1234567890

---

## [<previous_version>] - <Month Year>
...
```

---

## Rules

### Version header
```
## [2026.1.0] - June 2026
```
- Version is enclosed in square brackets.
- Date is written as `Month YYYY` (full month name, four-digit year).
- Separated from previous section by a horizontal rule `---`.

### Section headers
Use `###` for each category. Include only sections that have at least one entry.
Order: **Added → Changed → Removed → Fixed → Security → Documentation**

### Bullet entries
- Begin with `- ` (dash and space).
- Written in **past tense**, **sentence case** (capitalize first word only, unless
  a proper noun).
- End with a period `.`
- Append PR/commit reference in parentheses: `([#NN])` or `([abcdef])`
- One bullet per logical change. If a commit covers multiple unrelated changes,
  split into separate bullets.

### Reference links
After the last bullet of the version block, add a horizontal rule `---` followed by
reference-style links for every PR/commit cited:

```markdown
---
[#29]: <repo_url>/pull/29
[0a74a61]: <repo_url>/commit/0a74a613d92f08f321a60d8eedcebec2a6cb22b4
```

Use the **full commit hash** (40 characters) in the URL even though the anchor
text uses the short hash (7 characters).

---

## Full annotated example

```markdown
# Changelog

All notable changes to this project are documented in this file.

## [2026.1.0] - June 2026

### Added
- Added batch processing variants for anomaly detection sample apps. ([#2586])
- Added classification training and inference scripts for weld defect detection. ([#2354])

### Changed
- Renamed sample app "Weld Anomaly Detection" to "Weld Defect Detection" across all configs, docs, and scripts. ([#2504])
- Updated UDF package upload format from zip to tar archives. ([#2441])

### Removed
- Removed LinearRegression model from Wind Turbine Anomaly Detection. ([#2509])

### Fixed
- Fixed Helm automation deployment issues. ([#2424])
- Fixed failing functional test cases. ([#2450])

### Security
- Bumped `cryptography` from 46.0.5 to 47.0.0. ([#2352])
- Updated Docker Compose service image versions to address security vulnerabilities. ([#2579])

### Documentation
- Updated get-started guide by moving multi-stream ingestion to a dedicated how-to guide. ([#2884])
- Fixed broken reference in Weld Defect Detection documentation. ([#2581])

---
[#2352]: <repo_url>/pull/2352
[#2354]: <repo_url>/pull/2354
[#2424]: <repo_url>/pull/2424
[#2441]: <repo_url>/pull/2441
[#2450]: <repo_url>/pull/2450
[#2504]: <repo_url>/pull/2504
[#2509]: <repo_url>/pull/2509
[#2579]: <repo_url>/pull/2579
[#2581]: <repo_url>/pull/2581
[#2584]: <repo_url>/pull/2584
[#2884]: <repo_url>/pull/2884

---

## [2026.0] - March 2026

...
```

---

## Style notes

- Keep descriptions concise (one sentence preferred, two at most).
- Do not include the commit hash in the description text — it lives in the
  reference link only.
- Do not include the branch or author name unless it adds meaningful context.
- Avoid implementation jargon that external contributors wouldn't understand.
- Prefer active phrases: "Added X", "Fixed Y", "Removed Z".
