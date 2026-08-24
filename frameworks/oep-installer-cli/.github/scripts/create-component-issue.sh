#!/usr/bin/env bash
# Usage: create-component-issue.sh <specs_list_file>
# Reads a newline-separated list of spec file paths, derives a component name
# for each, builds a detailed task-body file, and creates a GitHub issue
# assigned to copilot-swe-agent.
#
# Requires: gh (GitHub CLI) authenticated via GITHUB_TOKEN env var.
set -euo pipefail

SPECS_LIST="${1:?Usage: $0 <specs_list_file>}"

# Build list of available helpers once (embedded into every issue body)
HELPERS_LIST="$(find common/ license/ -type f 2>/dev/null | sort | sed 's|^|  - |')"

while IFS= read -r spec_file; do
  [ -f "$spec_file" ] || continue

  # Derive component name: strip directory + .md suffix, lowercase, dashes → underscores
  raw_name="$(basename "$spec_file" .md)"
  name="${raw_name,,}"
  name="${name//-/_}"

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

1. **File location**: \`module/${name}/debian\`

2. **Function naming** (see \`module/README.md\`):
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

3. **Functions to implement**:
   - Always implement \`install\`, \`remove\`, \`start\`, and \`stop\`.
   - Omit \`start\`/\`stop\` **only** when the spec describes a stateless
     system package with no runtime service (cite \`module/curl/debian\` as
     precedent).
   - Omit \`remove\` **only** for trivial system packages where removal
     could cause unintended side-effects (cite \`module/curl/debian\`).
   - Add \`debian_<NN>_license_${name}\` if the spec requires a click-through
     license; the function must print \`@@LICENSE-ID\`, \`@@LICENSE-TITLE\`,
     and the full license text (use \`ensure_license_fetch\` if fetching
     from a URL).

4. **Profile function**: \`debian_<NN>_profile_${name}\` must \`echo\` a
   space-separated list of **existing** component names that \`${name}\`
   depends on. Only list names that actually exist as directories under
   \`module/\`.

5. **\`configure_${name}\` / \`verify_${name}\` idiom**:
   - Define a \`configure_${name}\` function that sets local workspace,
     version, and repository variables (no global state).
   - Define a \`verify_${name}\` function that returns 0 if the component
     is already correctly installed, non-zero otherwise.

6. **Idempotent install**:
   - Call \`verify_${name}\` at the top of \`install\`; skip if already
     satisfied and \`--reset-${name}\` flag is absent.
   - Support the \`--reset-${name}\` flag to force reinstallation.

7. **\`remove\` robustness**: call \`stop\` first (with \`|| true\`),
   then clean up workspace/images/volumes.

8. **Helpers** – only reuse helpers that **actually exist** under \`common/\`
   or \`license/\`. Do **not** invent new helpers. Available helpers:
${HELPERS_LIST}

9. **Name conventions** (see \`module/README.md\`):
   - No global variable name collisions. Use \`local\` variables or
     suffix/prefix with \`_${name}\`.
   - Internal helper functions (if any) must be prefixed with the component
     name, e.g. \`${name}_setup_something\`.

10. **Reference implementations**:
    - Full app (profile + install + start + stop + remove):
      \`module/loitering_detection/debian\`
    - Minimal package (install only): \`module/curl/debian\`

---

### @@HIGHLIGHT guidance

\`@@HIGHLIGHT\` is a protocol consumed by \`ensure_panelled_logs\` in
\`common/linux/panelled_logs\` to show the user what to do after install or
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
done < "$SPECS_LIST"
