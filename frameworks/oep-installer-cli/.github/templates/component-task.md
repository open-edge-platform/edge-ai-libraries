## Task: implement `module/{{NAME}}/debian`

A new spec file `{{SPEC_FILE}}` was pushed to `main`. Implement the
corresponding installer component following the rules below, then open a
pull request adding `module/{{NAME}}/debian`.

---

### Spec

```markdown
{{SPEC_CONTENT}}
```

---

### Implementation requirements

- **Function naming** (See `module/README.md`):

   ```
   debian_<NN>_profile_{{NAME}}
   debian_<NN>_install_{{NAME}}
   debian_<NN>_remove_{{NAME}}
   debian_<NN>_start_{{NAME}}
   debian_<NN>_stop_{{NAME}}
   debian_<NN>_license_{{NAME}}   # only if the spec requires a click-through license

   ```

   Use the **same two-digit order number** `<NN>` across all functions in
   this component, chosen from the documented ranges:
   ```
   00-29  kernel modules/drivers or system utilities
   30-59  low-level libraries
   60-89  middle-level libraries, SDK, and services including microservices
   90-98  applications, tools, 
   99     profiles (virtual groups of components)
   ```

- **File location**: `module/{{NAME}}/debian` for debian specific functions and
   `module/{{NAME}}/linux` for distribution agnostic functions. The interface functions mentioned
   above must be defined in `module/{{NAME}}/debian`.        

- **Functions to implement**:
   - Always implement `install`, `remove`, `start`, and `stop`. Follow `profile/README.md` and `module/README.md` for implementation requirements. 
   - Omit `start`/`stop` **only** when the spec describes a stateless system package with no runtime service, for example, a library or SDK that has no explicit start/stop operation.   
   - Omit `remove` **only** for trivial system packages where removal could cause unintended side-effects (cite `module/curl/debian`).
   - Add `debian_<NN>_license_{{NAME}}` if the spec requires a click-through license; the function must print `@@LICENSE-ID`, `@@LICENSE-TITLE`, and the full license text (use `ensure_license_fetch` if fetching from a URL).
   - Reuse common functions actually defined under common/ or license/. Do not invent new helpers. Available helpers: {{HELPERS_LIST}}

- **`configure_{{NAME}}` idiom**:
   - If a local workspace is required to store the component source files or configurations, define
     a `configure_{{NAME}}` function that sets local workspace, version, and repository variables.
     Use the default workspace location `$(ensure_project_path)/{{NAME}}`.

- **`verify_{{NAME}}` idiom**:
   - Define a `verify_{{NAME}}` function that returns 0 if the component is already correctly
     installed, non-zero otherwise.
   - The `verify_{{NAME}}` function should verify if the component is completely installed, by
     checking the workspace existence, important files such as downloaded videos and models and
     required docker images.

- **Reference implementations**:
    - Full app (profile + install + start + stop + remove): `module/smart_parking/debian`
    - Minimal package (install only): `module/curl/debian`

### Validation before opening the PR

Your responsibility before opening the PR is to pass all **static checks**.
Platform validation on real hardware is performed separately by maintainers
(see *Platform validation* below) — do not claim that platform validation has
passed.

Run these checks and fix all issues before pushing:

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

In the PR description, include a note such as:
> "Static checks pass. Awaiting the `validate-platform` label for hardware
> validation."

Do **not** state that platform validation passed — you cannot run it.

---

### Platform validation

Platform validation is performed by a maintainer applying the
`VALIDATE-PLATFORM` label to the PR.  This triggers
`.github/workflows/platform-validate.yml` on a self-hosted runner inside the
corporate lab, which runs the following lifecycle on real hardware:

| Step | What is tested |
|------|---------------|
| install | `openedge-cli install {{NAME}}` must exit 0 |
| install (again) | Idempotency — must exit 0, must not re-run expensive steps |
| install --reset-{{NAME}} | Forced reinstall must exit 0 |
| start + port probe | `openedge-cli start {{NAME}}` must exit 0; declared ports must be reachable |
| stop + port probe | `openedge-cli stop {{NAME}}` must exit 0; ports must be released |
| remove + verify | `openedge-cli remove {{NAME}}` must exit 0; `verify_{{NAME}}` must then fail |

**Your component must therefore:**
- Be fully **idempotent**: the second install must detect the existing state
  via `verify_{{NAME}}` and skip gracefully.
- Support `--reset-{{NAME}}` for forced reinstallation.
- Have a `stop` that fully releases any bound ports.
- Have a `remove` that leaves `verify_{{NAME}}` returning non-zero and
  cleans up the workspace.

If validation fails, you will receive a PR comment addressed to **@copilot**
with the failing step name and the last ~50 lines of the log.  Fix the issue
and push to this branch — the workflow will re-run automatically.

---

> **Note**: generated PRs must be reviewed by a human before merging.
