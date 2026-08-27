## Task: implement `module/{{NAME}}/debian`

A new spec file `{{SPEC_FILE}}` was pushed to `main`. Implement the
corresponding installer component following the rules below, then open a
pull request adding `module/{{NAME}}/debian`.

> **Before writing any code**, read `module/README.md` and `profile/README.md`
> in full.  They are the normative reference for function naming, order ranges,
> the `@@HIGHLIGHT` protocol, the `install`/`remove`/`start`/`stop`/`profile`/
> `license` contracts, and helper reuse.  The requirements below do **not**
> restate those rules — they only cover what is not already in those files.

> **Scope fence**: modify only files under `module/{{NAME}}/`.  Do **not**
> touch `common/`, `license/`, `openedge-cli`, `profile/`, `.github/`, or any
> other component's directory.  If a needed helper does not exist in `common/`
> or `license/`, implement the logic locally within the component and note the
> gap in the PR description for a maintainer to decide.

---

### Spec

```markdown
{{SPEC_CONTENT}}
```

---

### Implementation requirements

- **Function naming** (see `module/README.md`):

   The six interface functions **must** follow the exact pattern:
   ```
   debian_<NN>_profile_{{NAME}}
   debian_<NN>_install_{{NAME}}
   debian_<NN>_remove_{{NAME}}
   debian_<NN>_start_{{NAME}}
   debian_<NN>_stop_{{NAME}}
   debian_<NN>_license_{{NAME}}   # only if the spec requires a click-through license
   ```
   `configure_{{NAME}}` and `verify_{{NAME}}` are **conventions, not
   requirements** — they are not enforced by the naming check.  Additional
   helper functions are allowed; the real constraint is **global uniqueness
   across all installer scripts** (CI enforces this).  Suffixing helpers with
   `_{{NAME}}` is the recommended way to ensure uniqueness.

- **File location**: `module/{{NAME}}/debian` for debian specific functions and
   `module/{{NAME}}/linux` for distribution agnostic functions. The interface functions mentioned
   above must be defined in `module/{{NAME}}/debian`.        

- **Functions to implement**:
   - Always implement `install`, `remove`, `start`, and `stop`. Follow `profile/README.md` and `module/README.md` for implementation requirements. 
   - Omit `start`/`stop` **only** when the spec describes a stateless system package with no runtime service, for example, a library or SDK that has no explicit start/stop operation.   
   - Omit `remove` **only** for trivial system packages where removal could cause unintended side-effects (cite `module/curl/debian`).
   - Add `debian_<NN>_license_{{NAME}}` if the spec requires a click-through license; the function must print `@@LICENSE-ID`, `@@LICENSE-TITLE`, and the full license text (use `ensure_license_fetch` if fetching from a URL).
   - Reuse common functions actually defined under common/ or license/. Do not invent new helpers. Available helpers: {{HELPERS_LIST}}

- **Profile membership**: the spec's `## Profile membership` section states
   whether this component should be added to one or more profiles.  Do **not**
   edit `profile/*/debian` yourself.  Instead, include in the PR description
   the exact suggested edit — the `profile/<suite>/debian` function name and
   the component name to append to its return list — so a maintainer can apply
   it.  If the spec is silent or says "none", note that and take no action.

- **`set -e` consequence**: all component scripts execute in a `set -e`
   subshell (see `act_helpper` in `common/linux/cli`).  Any command that may
   legitimately fail must be guarded with `|| true`, as done in
   `module/smart_parking/debian`'s `remove` function.

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
# 1. Bash syntax check — covers both debian and linux files if present
for f in module/{{NAME}}/*; do [ -f "$f" ] || continue; bash -n "$f"; done

# 2. Shellcheck (sourced fragment – disable SC2148 missing-shebang)
for f in module/{{NAME}}/*; do
  [ -f "$f" ] || continue
  shellcheck --shell=bash --exclude=SC2148 "$f"
done

# 3. Check that every function defined in this component is globally unique
# (no other installer script in module/, profile/, common/, or license/ defines
# the same name).  CI enforces this via validate-modules.yml.
for f in module/{{NAME}}/*; do
  [ -f "$f" ] || continue
  while IFS= read -r func; do
    matches="$(grep -rlE "^${func} *\(\)" module/ profile/ common/ license/ \
      2>/dev/null | grep -v "^module/{{NAME}}/" || true)"
    if [[ -n "$matches" ]]; then
      echo "Function name collision: '${func}' in ${f} is also defined in: ${matches}"
      exit 1
    fi
  done < <(grep -oE '^[a-zA-Z_][a-zA-Z0-9_]+' "$f" \
    < <(grep -E '^[a-zA-Z_][a-zA-Z0-9_]* *\(\)' "$f" || true))
done
echo "Function names are globally unique."
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
