## Task: update `module/{{NAME}}/debian`

The spec file `{{SPEC_FILE}}` was modified in `main`.  The existing
implementation in `module/{{NAME}}/debian` must be **updated in place** to
enforce any new or changed requirements introduced by the spec edit.

> **Note**: A maintainer added the `GENERATE-COMPONENT` label to authorise
> this task.  Do **not** rewrite the implementation from scratch — edit only
> what the spec change requires.

---

### Updated spec

```markdown
{{SPEC_CONTENT}}
```

---

### Current implementation baseline

The existing code that you must modify (not replace):

{{CURRENT_IMPLEMENTATION}}

---

### Implementation requirements

#### Modify in place — do not rewrite

- Edit `module/{{NAME}}/debian` (and `module/{{NAME}}/linux` if it exists)
  rather than recreating the file from scratch.
- Preserve the existing `debian_<NN>_*` order number unchanged.
- Preserve the existing `configure_{{NAME}}` / `verify_{{NAME}}` function
  idioms unless the spec change explicitly requires altering them.
- Preserve any existing helper functions that are not affected by the spec
  change.
- Keep the diff **minimal and reviewable** — do not reformat, reorder, or
  rename code that the spec change does not touch.

#### Enforce every new or changed requirement

Before writing any code, diff the updated spec against the current
implementation above and enumerate, in the PR description, **every requirement
that is new or changed**:

- New apt/pip/other dependencies → add to `debian_<NN>_profile_{{NAME}}`
- Changed version tag, repository URL, or binary path → update in
  `configure_{{NAME}}`
- New TCP/UDP ports → add to `ensure_ports_open` calls
- New or changed `@@HIGHLIGHT` / `@@COMP` / `@@OK` / `@@FAIL` markers
- A newly required `debian_<NN>_license_{{NAME}}` function
- Changed verification criteria → update `verify_{{NAME}}`
- Changed removal or cleanup steps → update `debian_<NN>_remove_{{NAME}}`

For **each** item, either implement it or explicitly justify in the PR
description why the existing code already satisfies it.

#### Call out removals / regressions

If the spec no longer requires something the implementation still does, note it
explicitly in the PR description rather than silently deleting it.  A reviewer
must decide whether to remove it.

#### Version / state migration

If the spec changes a pinned version, tag, or workspace layout, `verify_{{NAME}}`
**must** return non-zero when an older version is already installed so that
`install` upgrades rather than skipping.  This is required by `module/README.md`
("The component of an older version is previously installed").

---

### Implementation reference rules (unchanged from new-component requirements)

- **Function naming** (see `module/README.md`):

   ```
   debian_<NN>_profile_{{NAME}}
   debian_<NN>_install_{{NAME}}
   debian_<NN>_remove_{{NAME}}
   debian_<NN>_start_{{NAME}}
   debian_<NN>_stop_{{NAME}}
   debian_<NN>_license_{{NAME}}   # only if the spec requires a click-through license
   ```

   Use the **same two-digit order number** `<NN>` across all functions
   (preserved from the existing implementation):

   ```
   00-29  kernel modules/drivers or system utilities
   30-59  low-level libraries
   60-89  middle-level libraries, SDK, and services
   90-98  applications, tools
   99     profiles
   ```

- **File location**: `module/{{NAME}}/debian` for Debian-specific functions;
  `module/{{NAME}}/linux` for distribution-agnostic functions.

- **Functions**: always implement `install`, `remove`, `start`, and `stop`.
  Omit `start`/`stop` only when the spec describes a stateless package with no
  runtime service.  Omit `remove` only for trivial system packages (cite
  `module/curl/debian`).

- **`configure_{{NAME}}` idiom**: set local workspace, version, and repository
  variables.  Default workspace: `$(ensure_project_path)/{{NAME}}`.

- **`verify_{{NAME}}` idiom**: return 0 if correctly installed, non-zero
  otherwise.  Check workspace existence, key files, required Docker images.

- **Reuse helpers** actually defined under `common/` or `license/`.  Do **not**
  invent new helpers.  Available helpers:

{{HELPERS_LIST}}

- **Reference implementations**:
  - Full app (profile + install + start + stop + remove): `module/smart_parking/debian`
  - Minimal package (install only): `module/curl/debian`

---

### Validation before opening the PR

Run these static checks and fix all issues before pushing:

```bash
# 1. Bash syntax check
bash -n module/{{NAME}}/debian

# 2. Shellcheck (sourced fragment – disable SC2148 missing-shebang)
shellcheck --shell=bash --exclude=SC2148 module/{{NAME}}/debian

# 3. Verify all public function names match the allowed pattern
grep -E '^[a-zA-Z_][a-zA-Z0-9_]* \(\)' module/{{NAME}}/debian \
  | grep -vE '^(configure|verify)_{{NAME}} \(\)$' \
  | grep -vE '^[a-z]+_[0-9]{2}_(profile|license|install|remove|start|stop)_{{NAME}} \(\)$' \
  && { echo "Function name violation found"; exit 1; } || echo "Function names OK"
```

In the PR description:

1. List every new or changed requirement from the spec diff, and explain how
   each is implemented (or why the existing code already satisfies it).
2. List any spec removals / regressions and recommend whether to delete them.
3. Include the note:
   > "Static checks pass. Awaiting the `validate-platform` label for hardware
   > validation."

Do **not** state that platform validation has passed — you cannot run it.

---

### Platform validation

Platform validation is performed by a maintainer applying the
`validate-platform` label to the PR.  This triggers
`.github/workflows/platform-validate.yml` on a self-hosted runner which runs
the following lifecycle on real hardware:

| Step | What is tested |
|------|----------------|
| install | `openedge-cli install {{NAME}}` must exit 0 |
| install (again) | Idempotency — must exit 0, must not re-run expensive steps |
| install --reset-{{NAME}} | Forced reinstall must exit 0 |
| start + port probe | `openedge-cli start {{NAME}}` must exit 0; declared ports reachable |
| stop + port probe | `openedge-cli stop {{NAME}}` must exit 0; ports released |
| remove + verify | `openedge-cli remove {{NAME}}` must exit 0; `verify_{{NAME}}` must fail |

**Your updated component must therefore remain:**
- Fully **idempotent**: second install detects existing state via `verify_{{NAME}}` and skips gracefully.
- Supporting `--reset-{{NAME}}` for forced reinstallation.
- Having a `stop` that fully releases bound ports.
- Having a `remove` that leaves `verify_{{NAME}}` returning non-zero.

If validation fails, you will receive a PR comment addressed to **@copilot**
with the failing step and last ~50 lines of log.  Fix and push — the workflow
re-runs automatically.

---

> **Note**: generated PRs must be reviewed by a human before merging.
