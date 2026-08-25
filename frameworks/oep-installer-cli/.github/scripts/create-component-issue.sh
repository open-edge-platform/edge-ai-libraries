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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../templates/component-task.md"
FORCE_REGENERATE="${FORCE_REGENERATE:-false}"
MAX_TASKS_PER_RUN="${MAX_TASKS_PER_RUN:-3}"

# Validate MAX_TASKS_PER_RUN is a positive integer.
if ! [[ "$MAX_TASKS_PER_RUN" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::MAX_TASKS_PER_RUN must be a positive integer, got: '${MAX_TASKS_PER_RUN}'"
  exit 1
fi

# Validate template file exists.
if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "::error::Template file not found: ${TEMPLATE_FILE}"
  exit 1
fi

# ---------------------------------------------------------------------------
# render_template – substitute {{PLACEHOLDER}} markers using bash string
# replacement (no sed/envsubst, safe for multi-line values containing
# shell-special characters).  SPEC_CONTENT is substituted last so that
# spec text containing literal "{{NAME}}" etc. is not further expanded.
# Usage: render_template <template_file> <name> <spec_file> <helpers_list> <spec_content>
# ---------------------------------------------------------------------------
render_template () {
  local template="$1"
  local name="$2"
  local spec_file="$3"
  local helpers_list="$4"
  local spec_content="$5"
  local body
  body="$(<"$template")"

  body="${body//\{\{NAME\}\}/$name}"
  body="${body//\{\{SPEC_FILE\}\}/$spec_file}"
  body="${body//\{\{HELPERS_LIST\}\}/$helpers_list}"
  body="${body//\{\{SPEC_CONTENT\}\}/$spec_content}"

  printf '%s\n' "$body"
}

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
  render_template "$TEMPLATE_FILE" "$name" "$spec_file" "$HELPERS_LIST" "$(cat "$spec_file")" > "$BODY_FILE"

  gh issue create \
    --title "Implement installer component: ${name}" \
    --body-file "$BODY_FILE" \
    --assignee copilot-swe-agent

  rm -f "$BODY_FILE"
done
