#!/usr/bin/env bash
# Usage: create-component-issue.sh <specs_list_file>
# Reads a newline-separated list of spec file paths, derives a component name
# for each, builds a detailed task-body file, and creates a GitHub issue
# assigned to copilot-swe-agent.
#
# Environment variables:
#   FORCE_REGENERATE   Set to "true" to bypass Guards 2 and 3 (module-exists
#                      and open-issue checks).  Default: unset / false.
#   MAX_TASKS_PER_RUN  Maximum number of new issues to create in one run.
#                      Default: 3.  If the number of eligible specs exceeds
#                      this cap, the job fails loudly and no issues are created.
#
# Requires: gh (GitHub CLI) authenticated via GH_TOKEN env var, jq.
set -euo pipefail

SPECS_LIST="${1:?Usage: $0 <specs_list_file>}"
FORCE_REGENERATE="${FORCE_REGENERATE:-false}"
MAX_TASKS_PER_RUN="${MAX_TASKS_PER_RUN:-3}"

# Validate MAX_TASKS_PER_RUN is a positive integer.
if ! [[ "$MAX_TASKS_PER_RUN" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::MAX_TASKS_PER_RUN must be a positive integer, got: '${MAX_TASKS_PER_RUN}'"
  exit 1
fi

# Build list of available helpers once (embedded into every issue body)
HELPERS_LIST="$(find common/ license/ -type f ! -name cli ! -name panelled_logs ! -name license_gate 2>/dev/null | sort | sed 's|^|  - |')"

# ---------------------------------------------------------------------------
# Pass 1 – collect eligible specs (apply Guards 2 and 3)
# ---------------------------------------------------------------------------
eligible_specs=()
eligible_names=()

while IFS= read -r spec_file; do
  [ -f "$spec_file" ] || continue

  # Derive component name: strip directory + .md suffix, lowercase, dashes → underscores
  raw_name="$(basename "$spec_file" .md)"
  name="${raw_name,,}"
  name="${name//-/_}"

  # Guard 2 – skip if module/<name>/ already exists
  if [[ "$FORCE_REGENERATE" != "true" ]] && [[ -d "module/${name}/" ]]; then
    echo "::notice::Skipping ${spec_file}: module/${name}/ already exists. Delete the module directory or set FORCE_REGENERATE=true to regenerate."
    continue
  fi

  # Guard 3 – skip if an open issue with the same title already exists
  if [[ "$FORCE_REGENERATE" != "true" ]]; then
    issue_title="Implement installer component: ${name}"
    # gh issue list search is fuzzy; filter JSON for an exact title match with jq.
    existing_number="$(gh issue list \
      --state open \
      --search "${issue_title}" \
      --json number,title \
      | jq -r --arg title "${issue_title}" \
          '.[] | select(.title == $title) | .number' \
      | head -n 1)"
    if [[ -n "$existing_number" ]]; then
      echo "::notice::Skipping ${spec_file}: open issue #${existing_number} already exists for '${issue_title}'. Set FORCE_REGENERATE=true to create a new one."
      continue
    fi
  fi

  eligible_specs+=("$spec_file")
  eligible_names+=("$name")
done < "$SPECS_LIST"

# Guard 4 – cap tasks per run (pre-flight, all-or-nothing)
task_count="${#eligible_specs[@]}"
if (( task_count > MAX_TASKS_PER_RUN )); then
  echo "::error::${task_count} specs are eligible but MAX_TASKS_PER_RUN is ${MAX_TASKS_PER_RUN}. No issues were created."
  echo "::error::Eligible specs: ${eligible_specs[*]}"
  echo "::error::To proceed deliberately, either:"
  echo "::error::  - Re-run with a higher MAX_TASKS_PER_RUN (workflow_dispatch input 'max_tasks')"
  echo "::error::  - Dispatch each spec individually via workflow_dispatch with 'spec_file'"
  exit 1
fi

if (( task_count == 0 )); then
  echo "No eligible specs after filtering – nothing to do."
  exit 0
fi

# ---------------------------------------------------------------------------
# Pass 2 – create issues for eligible specs
# ---------------------------------------------------------------------------
for i in "${!eligible_specs[@]}"; do
  spec_file="${eligible_specs[$i]}"
  name="${eligible_names[$i]}"

  BODY_FILE="$(mktemp --suffix=.md)"

  cat > "$BODY_FILE" <<ENDOFBODY
## Task: implement \`module/${name}/debian\`

A new spec file \`${spec_file}\` was pushed to \`main\`. Implement the
corresponding installer component following the rules below, then open a
pull request adding \`module/${name}/debian\`.

---

### Spec

\`\`\`markdown
$(cat "$spec_file")
\`\`\`

---

### Implementation requirements

1. **Function naming** (see \`module/README.md\`):
   \`\`\`
   debian_<NN>_profile_${name}
   debian_<NN>_install_${name}
   debian_<NN>_remove_${name}
   debian_<NN>_start_${name}
   debian_<NN>_stop_${name}
   debian_<NN>_license_${name}   # only if the spec requires a click-through license
   \`\`\`
   Use the **same two-digit order number** \`<NN>\` across all functions in
   this component, chosen from the documented ranges:
   \`\`\`
   00-29  kernel modules/drivers
   30-59  low-level libraries
   60-89  middle-level libraries/microservices
   90-98  applications
   99     profiles
   \`\`\`

2. **File location**: \`module/${name}/debian\`. Linux distribution-agnostic functions 
   can be also defined in \`module/${name}/linux\`, except those interface functions 
   mentioned in step 1.      

3. **Functions to implement**:
   - Always implement \`install\`, \`remove\`, \`start\`, and \`stop\`.
   - Omit \`start\`/\`stop\` **only** when the spec describes a stateless
     system package with no runtime service, for example, a library or SDK that has no
     explicit start/stop operation.   
   - Omit \`remove\` **only** for trivial system packages where removal
     could cause unintended side-effects (cite \`module/curl/debian\`).
   - Add \`debian_<NN>_license_${name}\` if the spec requires a click-through
     license; the function must print \`@@LICENSE-ID\`, \`@@LICENSE-TITLE\`,
     and the full license text (use \`ensure_license_fetch\` if fetching
     from a URL).

4. **Profile function**: \`debian_<NN>_profile_${name}\` must \`echo\` a
   space-separated list of **existing** component names that \`${name}\`
   depends on. Components that use docker must include `\docker`\ as a
   dependency. For Edge tools, applications and services that use GPU or NPU,
   include \`edge_base\` as a dependency, which is a virtual package for 
   preparing the system for Edge applications. If the component requires
   to use \`make\` for configuration, list \`make\` as a dependency. List
   all required dependencies. If some of them are not yet available under \`modules\`, 
   implement them as part of the commit.    

5. **\`configure_${name}\` / \`verify_${name}\` idiom**:
   - Define a \`configure_${name}\` function that sets local workspace,
     version, and repository variables (no global state).
   - If a local workspace is required, for example, use the default workspace location
     `$(ensure_project_path)/${name}`.  
   - Define a \`verify_${name}\` function that returns 0 if the component
     is already correctly installed, non-zero otherwise.

6. **Idempotent install**:
   - Call \`verify_${name}\` at the top of \`install\`; skip if already
     satisfied and \`--reset-${name}\` flag is absent.
   - Support the \`--reset-${name}\` flag to force reinstallation.
   - The \`install\` function should install the component, configure/setup it up such
     that it is ready to use, which also includes pulling docker images if the component
     is a dockerized application.   

7. **\`start\` robustness**: If a component appears to be running (for example, with
   occupied ports), the \`start\` function uses \`ensure_ports_open\` to check if the 
   ports are occupied and if so, stop the component first. 

   The list of required ports can usually be obtained by scanning any docker compose files 
   in the component repository, if not explicitly specified.   

8. **\`remove\` robustness**: call \`stop\` first (with \`|| true\`) to stop the component,
   then clean up workspace/images/volumes.

9. **Helpers** – only reuse helpers that **actually exist** under \`common/\`
   or \`license/\`. Do **not** invent new helpers. Available helpers:
${HELPERS_LIST}

10. **Name conventions** (see \`module/README.md\`):
   - No global variable name collisions. Use \`local\` variables or
     suffix/prefix with \`_${name}\`.
   - Internal helper functions (if any) must be prefixed with the component
     name, e.g. \`${name}_setup_something\`.

11. **Reference implementations**:
    - Full app (profile + install + start + stop + remove):
      \`module/loitering_detection/debian\`
    - Minimal package (install only): \`module/curl/debian\`

---

### @@HIGHLIGHT guidance

\`@@HIGHLIGHT\` is a protocol to show the user what to do after install or
start.

**When to include it:**
- Include it for **complex applications** — components that have a workspace,
  a service, a UI, an environment to source, sample content, or docs worth
  linking.  These are typically in the **60–98** order range.
- **Do not** add it for simple utilities such as \`curl\`, \`jq\`, \`gawk\`,
  \`unzip\`, \`make\`, or \`libgl1\` — there is nothing meaningful to say.

**For \`start\`**, the most useful highlight is usually the UI or API URL:
\`\`\`bash
echo "@@HIGHLIGHT URL: http://\$(ensure_ip):\$port"
\`\`\`

**Placement**: emit \`@@HIGHLIGHT\` lines **outside** the "already installed,
skipping" branch so they are printed on both fresh and skipped installs:
\`\`\`bash
debian_NN_install_${name} () {
  configure_${name}
  if verify_${name} && [[ " \$* " != *" --reset-${name} "* ]]; then
    echo "${name} already installed. Skipping."
  else
    # ... installation steps ...
  fi
  # @@HIGHLIGHT goes here — runs on both fresh and skipped installs
  echo "@@HIGHLIGHT workspace: \$workspace"
}
\`\`\`

**Format**:
- \`@@HIGHLIGHT <label>: <value>\` — for human-readable text
- \`@@HIGHLIGHT <label> @<path-or-command>\` — for paths and commands
- Keep each highlight to a single short line.

---

### Validation before opening the PR

Your responsibility before opening the PR is to pass all **static checks**.
Platform validation on real hardware is performed separately by maintainers
(see *Platform validation* below) — do not claim that platform validation has
passed.

Run these checks and fix all issues before pushing:

\`\`\`bash
# 1. Bash syntax check
bash -n module/${name}/debian

# 2. Shellcheck (sourced fragment – disable SC2148 missing-shebang)
shellcheck --shell=bash --exclude=SC2148 module/${name}/debian

# 3. Verify all public function names match the allowed pattern
grep -E '^[a-zA-Z_][a-zA-Z0-9_]* \(\)' module/${name}/debian \
  | grep -vE '^(configure|verify)_${name} \(\)$' \
  | grep -vE '^[a-z]+_[0-9]{2}_(profile|license|install|remove|start|stop)_${name} \(\)$' \
  && { echo "Function name violation found"; exit 1; } || echo "Function names OK"
\`\`\`

In the PR description, include a note such as:
> "Static checks pass. Awaiting the \`validate-platform\` label for hardware
> validation."

Do **not** state that platform validation passed — you cannot run it.

---

### Platform validation

Platform validation is performed by a maintainer applying the
\`validate-platform\` label to the PR.  This triggers
\`.github/workflows/platform-validate.yml\` on a self-hosted runner inside the
corporate lab, which runs the following lifecycle on real hardware:

| Step | What is tested |
|------|---------------|
| install | \`openedge-cli install ${name}\` must exit 0 |
| install (again) | Idempotency — must exit 0, must not re-run expensive steps |
| install --reset-${name} | Forced reinstall must exit 0 |
| start + port probe | \`openedge-cli start ${name}\` must exit 0; declared ports must be reachable |
| stop + port probe | \`openedge-cli stop ${name}\` must exit 0; ports must be released |
| remove + verify | \`openedge-cli remove ${name}\` must exit 0; \`verify_${name}\` must then fail |

**Your component must therefore:**
- Be fully **idempotent**: the second install must detect the existing state
  via \`verify_${name}\` and skip gracefully.
- Support \`--reset-${name}\` for forced reinstallation.
- Have a \`stop\` that fully releases any bound ports.
- Have a \`remove\` that leaves \`verify_${name}\` returning non-zero and
  cleans up the workspace.

If validation fails, you will receive a PR comment addressed to **@copilot**
with the failing step name and the last ~50 lines of the log.  Fix the issue
and push to this branch — the workflow will re-run automatically.

---

> **Note**: generated PRs must be reviewed by a human before merging.
ENDOFBODY

  gh issue create \
    --title "Implement installer component: ${name}" \
    --body-file "$BODY_FILE" \
    --assignee copilot-swe-agent

  rm -f "$BODY_FILE"
done
