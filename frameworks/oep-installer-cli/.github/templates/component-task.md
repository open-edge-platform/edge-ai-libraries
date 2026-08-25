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

- **Function naming** (see `module/README.md`):
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
   - Always implement `install`, `remove`, `start`, and `stop`.
   - Omit `start`/`stop` **only** when the spec describes a stateless
     system package with no runtime service, for example, a library or SDK that has no
     explicit start/stop operation.   
   - Omit `remove` **only** for trivial system packages where removal
     could cause unintended side-effects (cite `module/curl/debian`).
   - Add `debian_<NN>_license_{{NAME}}` if the spec requires a click-through
     license; the function must print `@@LICENSE-ID`, `@@LICENSE-TITLE`,
     and the full license text (use `ensure_license_fetch` if fetching
     from a URL).

- **Profile function**: `debian_<NN>_profile_{{NAME}}` must `echo` a space-separated list of
   **existing** component names that `{{NAME}}` depends on. Components that use docker must
   include `docker`. For Edge tools, applications and services that use GPU or NPU, include
   `edge_base` as a dependency, which is a virtual package for preparing the system for GPU
   and NPU acceleration. If the component requires to use `make` for configuration, list `make`
   as a dependency. List all required dependencies. If certain dependents are not yet available
   under `modules`, implement them as part of the commit.

   Once a dependency is declared, consider the implementation of the dependent component ready
   to use. See `module/uv/debian` for an example. The `uv` component provides a public function
   `configure_uv` that can be used by other components, who declares `uv` as a dependent.
   
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
     
- **Idempotent `install`**:
   - Call `verify_{{NAME}}` at the top of the `install_{{NAME}}` function; skip if already satisfied and `--reset-{{NAME}}`
     flag is absent.
   - Support the `--reset-{{NAME}}` flag to force reinstallation.
   - If the component has a RAM or disk size requirement, use `ensure_disk_size` and `ensure_ram_size` to
     check the disk and ram size and exit early if failed. 
   - The `install_{{NAME}}` function should install the component, configure/setup it up such that it is ready to use,
     which includes but not limit to downloading any videos or models (if requried), building or pulling docker images.
     
- **`start` robustness**:
   - The start function must robustly launch the component. Use the `ensure_ports_open` to check if required ports are
     occupied and if so, invoke the `stop_{{NAME}}` function. For containerized applications, check if containers are
     already running, invoke the `stop_{{NAME}}` function to stop the containers and then restart the component.

     The list of required ports can usually be obtained by scanning any docker compose files in the component workspace,
     if not explicitly specified in the `{{SPEC_FILE}}`.   

- **`remove` robustness**:
   - Call the `stop_{{NAME}}` function first (with `|| true`) to stop the component. Then clean up workspace/images/volumes.

- **Helpers** – only reuse helpers that **actually exist** under `common/`
   or `license/`. Do **not** invent new helpers. Available helpers:
{{HELPERS_LIST}}

- **Name conventions** (see `module/README.md`):
   - No global variable name collisions. Use `local` variables or
     suffix/prefix with `_{{NAME}}`.
   - Internal helper functions (if any) must be prefixed with the component
     name, e.g. `{{NAME}}_setup_something`.

- **Reference implementations**:
    - Full app (profile + install + start + stop + remove): `module/smart_parking/debian`
    - Minimal package (install only): `module/curl/debian`

---

### Device Selection

Some applications or tools can configure GPU/NPU acceleration in the `install_{{NAME}}` and `start_{{NAME}}` functions. 
Use the `ensure_select_device` function to retrieve the device selection from the installer command line: `--gpu` (default) 
or `--npu`. The returned device (`gpu` or `npu`) can then be used to configure device acceleration the installation or 
the starting process. See `module/smart_parking/debian` for an example.  

---

### @@HIGHLIGHT guidance

`@@HIGHLIGHT` is a protocol to show the user what to do after install or
start.

**When to include it:**
- Include it for **complex applications** — components that have a workspace,
  a service, a UI, an environment to source, sample content, or docs worth
  linking.  These are typically in the **60–98** order range.
- **Do not** add it for simple utilities such as `curl`, `jq`, `gawk`,
  `unzip`, `make`, or `libgl1` — there is nothing meaningful to say.

**For `start`**, the most useful highlight is usually the UI or API URL:

```bash
echo "@@HIGHLIGHT URL: http://$(ensure_ip):$port"
```

**For libraries and SDKs**, the most useful highlight is to show the workspace and some hints of operations:

Example only:
```bash
echo "@@HIGHLIGHT workspace: $workspace"
echo "@@HIGHLIGHT setup env: setup-vars.sh"
echo "@@HIGHLIGHT make help to see full list of build targets"
```

**Placement**: emit `@@HIGHLIGHT` lines **outside** the "already installed,
skipping" branch so they are printed on both fresh and skipped installs:

```bash
debian_NN_install_{{NAME}} () {
  configure_{{NAME}}
  if verify_{{NAME}} && [[ " $* " != *" --reset-{{NAME}} "* ]]; then
    echo "{{NAME}} already installed. Skipping."
  else
    # ... installation steps ...
  fi
  # @@HIGHLIGHT goes here — runs on both fresh and skipped installs
  echo "@@HIGHLIGHT workspace: $workspace"
}
```

**Format**:
- `@@HIGHLIGHT <label>: <value>` — for human-readable text
- `@@HIGHLIGHT <label> @<path-or-command>` — for paths and commands
- Keep each highlight to a single short line.

---

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
