## Task: update `module/{{NAME}}/debian`

The spec file `{{SPEC_FILE}}` was modified in `main`.  The existing
implementation in `module/{{NAME}}/debian` must be **updated in place** to
enforce any new or changed requirements introduced by the spec edit.

> **Note**: A maintainer added the `GENERATE-COMPONENT` label to authorise
> this task.  Do **not** rewrite the implementation from scratch — edit only
> what the spec change requires.

> **Before writing any code**, read `module/README.md` and `profile/README.md`
> in full.  They are the normative reference for function naming, order ranges,
> the `@@HIGHLIGHT` protocol, the `install`/`remove`/`start`/`stop`/`profile`/
> `license` contracts, and helper reuse.  The requirements below do **not**
> restate those rules — they only cover what is not already in those files.

> **Scope fence**: modify only files under `module/{{NAME}}/` (and the
> profile files named in the spec, if any).
> Do **not** touch `common/`, `license/`, `openedge-cli`, `.github/`, or any
> other component's directory.  If a needed helper does not exist in `common/`
> or `license/`, implement the logic locally within the component and note the
> gap in the PR description for a maintainer to decide.

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

#### Naming

   The six interface functions **must** follow the exact pattern:

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

   `configure_{{NAME}}` and `verify_{{NAME}}` are **conventions, not
   requirements**.  Additional helper functions are allowed; the real
   constraint is **global uniqueness across all installer scripts** (CI
   enforces this).  Suffixing helpers with `_{{NAME}}` is the recommended
   way to ensure uniqueness.

- **File location**: `module/{{NAME}}/debian` for Debian-specific functions;
  `module/{{NAME}}/linux` for distribution-agnostic functions.

- **Functions**: always implement `install`, `remove`, `start`, and `stop`.
  Omit `start`/`stop` only when the spec describes a stateless package with no
  runtime service.  Omit `remove` only for trivial system packages (cite
  `module/curl/debian`).

- **Profile membership**: the spec states whether this component should be added to one or more profiles.
   - If the spec names one or more profiles, **update those `profile/*/debian`
     files directly** in this PR — append the component name to the return
     value of the corresponding `debian_99_profile_<suite>` function.
   - If the spec is silent or says "none", do **not** touch `profile/` and
     note this in the PR description.

- **`set -e` consequence**: all component scripts execute in a `set -e`
   subshell (see `act_helpper` in `common/linux/cli`).  Any command that may
   legitimately fail must be guarded with `|| true`, as done in
   `module/smart_parking/debian`'s `remove` function.

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

Run the shared validation script and fix every reported issue before pushing:

```bash
.github/scripts/validate-modules.sh module/{{NAME}}
```

This is the same script CI runs (`.github/workflows/validate-modules.yml`), so
a local pass means CI will pass.

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
