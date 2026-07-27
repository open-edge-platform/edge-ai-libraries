---
name: generate-changelog
description: >
  Generates or updates CHANGELOG.md by analyzing git commit history between two branches,
  tags, or revisions in ANY git repository or folder. Use this skill whenever the user
  asks to create, update, generate changelog, draft release notes from git history, or
  compare branches/tags (e.g., "generate changelog comparing release-2026.0.0 and release-2026.1.0",
  "update CHANGELOG.md for the time-series-analytics folder", "what changed between v1.0.0
  and main", "create release notes for this project"). The skill auto-detects folder paths,
  infers version numbers from branch/tag names, detects existing CHANGELOG format, and
  produces well-categorized entries (Added, Changed, Removed, Fixed, Security, Documentation)
  matching the repository's established style. Works with ANY folder structure or repository.
license: Apache-2.0
metadata:
  tags: "changelog release-notes"
---


# Changelog Generator

Generates or updates `CHANGELOG.md` by extracting and categorizing commits between
two git branches or tags. Follows the [Keep a Changelog](https://keepachangelog.com/) style
used by the current repository.

## Inputs

Collect from the user (or infer from context):

| Parameter | Description | Example |
|-----------|-------------|---------|
| `folder_path` | Path to the repository root or to a folder inside the repository; a subfolder automatically scopes commit extraction to that path | `/path/to/repo`, `microservices/time-series-analytics`, `./my-project` |
| `base_ref` | Starting branch, tag, or commit | `release-2026.0.0`, `v1.0.0`, `main`, commit SHA |
| `target_ref` | Ending branch, tag, or commit | `release-2026.1.0`, `v2.0.0`, `develop` |
| `version_label` | Version string for CHANGELOG entry | `2026.1.0`, `v1.2.0` |
| `release_date` | Release month and year (optional) | `June 2026`, `January 2024` |
| `changelog_path` | Output path for CHANGELOG.md | `<folder_path>/CHANGELOG.md` (default) |

### Path Semantics

- If `folder_path` points to the repository root, changelog generation covers the entire repository unless a narrower scope is supplied.
- If `folder_path` points to a subfolder inside the repository, that subfolder becomes the default commit scope automatically.
- If the user wants to write `CHANGELOG.md` in one location but scope commits to another path, call `extract_commits.sh` with the repository root as the first argument and the scope path as the optional fourth argument.

### Folder Path Resolution

If `folder_path` is not fully specified:

1. **Search by name:** If user says "time-series-analytics" but relative path isn't found, search the workspace recursively for a matching folder name.
   ```bash
   find <workspace_root> -type d -name "*time-series-analytics*" 2>/dev/null | head -1
   ```

2. **Resolve relative paths:** If a relative path is given, resolve it from current working directory:
   ```bash
   cd <workspace_root> && realpath <relative_path>
   ```

3. **Validate:** Confirm the folder is a git repository:
   ```bash
   git -C <folder_path> rev-parse --is-inside-work-tree
   ```

4. **Determine commit scope:**
   - If `<folder_path>` is the repository root, the default scope is the full repository.
   - If `<folder_path>` is a repository subfolder, use that subfolder as the default scope.
   - If needed, keep both values: `repo_root` for git operations and `scope_path` for path-limited history queries.

### Version Label Inference

If `version_label` is not provided, attempt to infer from `target_ref`:

1. **From branch name:** Extract version from naming patterns:
   - `release-2026.1.0` → `2026.1`
   - `release-2026.1.0` → `2026.1.0`
   - `v1.2.0` → `1.2.0`
   - `v2.0.0-rc1` → `2.0.0-rc1`

2. **From git tag:** If `target_ref` is a tag like `v2.1.0`, strip the `v` prefix.

3. **Fallback:** If inference fails, ask the user:
   > "I couldn't infer a version from `<target_ref>`. What version label should I use? (e.g., 2026.1.0, v1.2.0)"

If `release_date` is not provided, use the commit date of the target commit.

### GitHub/Remote URL Detection

```bash
git -C <folder_path> remote get-url origin
```

Strip `.git` suffix. Supports GitHub, GitLab, Gitea, and other hosting platforms.


## Workflow

### Step 1 – Resolve folder path and validate

1. If `folder_path` is incomplete or ambiguous, use the folder path resolution logic from the Inputs section.
2. Validate the path is inside a git repository:
   ```bash
   git -C <folder_path> rev-parse --is-inside-work-tree
   ```
   If this fails, inform the user the path is not a git repository or repository subfolder.

3. Resolve the repository root and the effective commit scope:
   ```bash
   repo_root=$(git -C <folder_path> rev-parse --show-toplevel)
   ```
   Treat `<folder_path>` as the scope when it is a subfolder. If `<folder_path>` equals `repo_root`, use the full repository unless the user supplied a narrower scope.

4. Verify both `base_ref` and `target_ref` exist:
   ```bash
   git -C "$repo_root" rev-parse <base_ref> >/dev/null 2>&1
   git -C "$repo_root" rev-parse <target_ref> >/dev/null 2>&1
   ```
   If either fails, list available branches and tags:
   ```bash
   git -C "$repo_root" branch -a && git -C "$repo_root" tag
   ```

### Step 2 – Infer version and release date

1. If `version_label` is missing, apply the version inference logic from the Inputs section.
2. If `release_date` is missing, extract the commit date of `target_ref`:
   ```bash
   git -C "$repo_root" log -1 --format=%cs <target_ref>
   ```
   Format as "Month Year" (e.g., "June 2026").

### Step 3 – Detect existing CHANGELOG format

Before categorizing commits, read the existing `CHANGELOG.md` (if present):

1. Check if `<folder_path>/CHANGELOG.md` exists.
2. If it exists, analyze its structure:
   - **Look for section headers:** Scan for patterns like `## [Version]`, `### Added`, `### Fixed`, etc.
   - **Infer category order:** Note which sections appear and in what order.
   - **Detect categorization style:** Is it Keep a Changelog style? Custom sections? Hybrid?
   - **Example inference:**
     ```
     # Changelog
     ## [2.0.0]
     ### Added
     ### Changed
     ### Fixed
     ```
     → Infer: Use `Added`, `Changed`, `Fixed` (no Security, Documentation, Removed)

3. If no CHANGELOG.md exists or it has no clear structure, use the **default keyword-based categorization** (described in Step 4).

### Step 4 – Extract and categorize commits

1. Get the commit list between base and target refs:
   ```bash
    bash .github/skills/generate-changelog/scripts/extract_commits.sh \
       <folder_path> <base_ref> <target_ref> [scope_path]
   ```

    Usage notes:
    - Use `<folder_path>` only for full-repository changelogs when it points to the repo root.
    - Use a repository subfolder as `<folder_path>` for folder-specific changelogs.
    - Use `[scope_path]` only when `<folder_path>` is the repo root but commit extraction should be narrowed to a different path.

2. For each commit, classify into a section based on the **detected format** from Step 3.

3. **If using default keyword-based categorization**, apply these rules in order (first match wins):

   | Section | Keywords / patterns (case-insensitive) |
   |---------|----------------------------------------|
   | **Security** | `security`, `cve`, `vulnerability`, `bump`, `trivy`, `patch`, `upgrade` (dependency) |
   | **Fixed** | `fix`, `fixed`, `repair`, `resolve`, `hotfix`, `revert` |
   | **Added** | `add`, `added`, `new`, `introduce`, `enable`, `support`, `feature`, `implement` |
   | **Removed** | `remove`, `removed`, `delete`, `deleted`, `drop`, `deprecat` |
   | **Documentation** | `doc`, `docs`, `documentation`, `readme`, `changelog`, `typo`, `spelling` |
   | **Changed** | everything else |

   > **Tip:** If a commit is ambiguous, prefer the section that better serves the reader. Merge commits and automated bot commits (e.g., Dependabot) should go in **Security** or **Changed** as appropriate.

4. Also collect PR numbers referenced in commit messages (pattern `(#\d+)` or `#\d+`).

### Step 5 – Format the entry

> **Format reference:** See [`references/changelog-format.md`](references/changelog-format.md) for the exact CHANGELOG structure and style template used by this repository.

Format the new version block using the **detected CHANGELOG style** from Step 3:

**If Keep a Changelog or similar style:**
```markdown
## [<version>] - <release_date>

### Added
- Feature one ([#123])
- Feature two ([abc1234])

### Changed
- Behavior updated ([#124])

### Fixed
- Bug resolved ([#125])

### Security
- Vulnerability patched ([#126])

[#123]: <repo_url>/pull/123
[#124]: <repo_url>/pull/124
[#125]: <repo_url>/pull/125
[#126]: <repo_url>/pull/126
[abc1234]: <repo_url>/commit/abc1234
```

**If custom sections detected:** Match the detected sections and order.

**Formatting rules:**
- Write each bullet in past tense, sentence case.
- Append PR/commit reference at the end: `([#NN])` for PRs, `([hash])` for commits.
- Omit sections with no entries.
- Include reference links at the bottom of the block.

### Step 6 – Write or update CHANGELOG.md

1. **If CHANGELOG.md does not exist:** Create it with a header + new version block:
   ```markdown
   # Changelog

   All notable changes to this project will be documented in this file.

   ## [<version>] - <release_date>
   ...
   ```

2. **If CHANGELOG.md exists:** Insert the new version block immediately after the introductory paragraph (or after `# Changelog` header) and *before* any existing `## [...]` sections. Preserve all existing content exactly.

3. **If version already exists in CHANGELOG.md:** Ask the user whether to replace or skip:
   > "Version `<version>` already exists in CHANGELOG.md. Replace it, append a new entry, or skip?"

4. Write to `<folder_path>/CHANGELOG.md` (or custom `changelog_path` if provided).

### Step 7 – Confirm output

Print a summary:
```
Changelog generated: <folder_path>/CHANGELOG.md
Version: <version> (<release_date>)
Commits processed: <count>
  Added: N | Changed: N | Fixed: N | Security: N | Documentation: N | Removed: N

Comparison: <base_ref>...<target_ref>
Repository: <repo_url>
```

## Edge cases

- **Folder path not found:** If searching for a folder name returns multiple matches or no matches, list results and ask the user to clarify which one to use.

- **Repo root vs scoped folder:** If the user asks for a folder-specific changelog but gives the repository root, either resolve a narrower folder path or call `extract_commits.sh <repo_root> <base_ref> <target_ref> <scope_path>` explicitly.

- **Detached HEAD or missing refs:** If `base_ref` or `target_ref` don't exist, list available branches and tags:
  ```bash
   git -C "$repo_root" branch -a && git -C "$repo_root" tag
  ```
  Ask the user to provide valid refs.

- **No commits found:** If `git log <base_ref>..<target_ref>` returns nothing, the refs may be identical or in the wrong order. Suggest:
  - Running `git fetch --all` to ensure all remote branches are available
  - Reversing the ref order if needed
  - Confirming the refs point to different commits

- **Shallow clone:** If the repository is a shallow clone, commit history may be incomplete. Suggest running:
  ```bash
   git -C "$repo_root" fetch --unshallow
  ```

- **Duplicate version in CHANGELOG.md:** If the version already exists, ask the user:
  > "Version `<version>` is already in CHANGELOG.md. Should I replace it, append a new entry, or skip?"

- **Empty or malformed existing CHANGELOG.md:** If the existing CHANGELOG.md has no clear structure, treat it as a new file and use the default keyword-based categorization. Warn the user that the new entry may not match the existing format.

- **No GitHub/remote URL:** If `git remote get-url origin` fails or returns a non-standard URL (e.g., SSH, local path), skip reference links or ask the user for the repository URL.

## Script reference

The helper script supports both repository-wide and folder-scoped extraction:

```bash
bash .github/skills/generate-changelog/scripts/extract_commits.sh <repo_or_folder_path> <base_ref> <target_ref> [scope_path]
```

- `<repo_or_folder_path>` may be the repository root or a subfolder inside the repository.
- When `<repo_or_folder_path>` is a subfolder, that subfolder is used as the commit scope automatically.
- `[scope_path]` is optional and is only needed when the first argument is the repository root but a narrower commit scope is desired.
