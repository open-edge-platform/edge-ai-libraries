#!/usr/bin/env bash
# Usage: create-component-issue.sh <specs_list_file>
#
# Reads a list of spec files and creates GitHub issues for each eligible spec.
# Each line in the list file is either:
#   <path>              (bare path, backward-compatible; treated as mode=new)
#   <status>\t<path>    (status letter A=new, M=modified, followed by a tab)
#
# Environment variables:
#   FORCE_REGENERATE   Set to "true" to bypass Guards 2 and 3.  Default: false.
#   MAX_TASKS_PER_RUN  Maximum number of new issues to create in one run.
#                      Default: 3.
#   ASSIGN_AGENT       Override agent assignment: "true" to always assign,
#                      "false" to never assign, "auto" (default) to derive from
#                      mode (new→assign, modified→label-gate).
#
# Requires: gh (GitHub CLI) authenticated via GH_TOKEN env var, jq.
set -euo pipefail

SPECS_LIST="${1:?Usage: $0 <specs_list_file>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_NEW="${SCRIPT_DIR}/../templates/component-task.md"
TEMPLATE_UPDATE="${SCRIPT_DIR}/../templates/component-update-task.md"
FORCE_REGENERATE="${FORCE_REGENERATE:-false}"
MAX_TASKS_PER_RUN="${MAX_TASKS_PER_RUN:-3}"
ASSIGN_AGENT="${ASSIGN_AGENT:-auto}"

# Validate MAX_TASKS_PER_RUN is a positive integer.
if ! [[ "$MAX_TASKS_PER_RUN" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::MAX_TASKS_PER_RUN must be a positive integer, got: '${MAX_TASKS_PER_RUN}'"
  exit 1
fi

# Validate template files exist.
if [[ ! -f "$TEMPLATE_NEW" ]]; then
  echo "::error::Template file not found: ${TEMPLATE_NEW}"
  exit 1
fi
if [[ ! -f "$TEMPLATE_UPDATE" ]]; then
  echo "::error::Template file not found: ${TEMPLATE_UPDATE}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Ensure required labels exist (idempotent via --force).
# ---------------------------------------------------------------------------
ensure_labels () {
  gh label create "needs-generation" \
    --description "Modified-spec issue awaiting maintainer dispatch of the Copilot coding agent" \
    --color "FBCA04" \
    --force 2>/dev/null || true
  gh label create "generate-component" \
    --description "Apply to a needs-generation issue to dispatch the Copilot coding agent" \
    --color "0E8A16" \
    --force 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# render_template – substitute {{PLACEHOLDER}} markers using bash string
# replacement (no sed/envsubst, safe for multi-line values containing
# shell-special characters).  SPEC_CONTENT and CURRENT_IMPLEMENTATION are
# substituted last so spec text containing literal "{{NAME}}" etc. is not
# further expanded.
# Usage: render_template <template_file> <name> <spec_file> <helpers_list> \
#                        <spec_content> [<current_impl>]
# ---------------------------------------------------------------------------
render_template () {
  local template="$1"
  local name="$2"
  local spec_file="$3"
  local helpers_list="$4"
  local spec_content="$5"
  local current_impl="${6:-}"
  local body
  body="$(<"$template")"

  body="${body//\{\{NAME\}\}/$name}"
  body="${body//\{\{SPEC_FILE\}\}/$spec_file}"
  body="${body//\{\{HELPERS_LIST\}\}/$helpers_list}"
  body="${body//\{\{CURRENT_IMPLEMENTATION\}\}/$current_impl}"
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
eligible_modes=()

while IFS= read -r raw_line; do
  # Parse optional "<status>\t<path>" format; default status to A (new).
  if [[ "$raw_line" == *$'\t'* ]]; then
    status="${raw_line%%$'\t'*}"
    spec_file="${raw_line#*$'\t'}"
  else
    status="A"
    spec_file="$raw_line"
  fi

  [ -f "$spec_file" ] || continue

  # Map status letter to mode.
  if [[ "$status" == "M" ]]; then
    mode="modified"
  else
    mode="new"
  fi

  # Derive component name: strip directory + .md suffix, lowercase, dashes → underscores
  raw_name="$(basename "$spec_file" .md)"
  name="${raw_name,,}"
  name="${name//-/_}"

  # Guard 2 – behaviour depends on mode:
  #   mode=new      → skip if module/<name>/ exists (original behaviour).
  #   mode=modified → module/<name>/ is expected to exist; proceed.
  #                   If it does NOT exist, demote to new (with a notice).
  if [[ "$FORCE_REGENERATE" != "true" ]]; then
    if [[ "$mode" == "new" ]] && [[ -d "module/${name}/" ]]; then
      echo "::notice::Skipping ${spec_file}: module/${name}/ already exists. Delete the module directory or set FORCE_REGENERATE=true to regenerate."
      continue
    fi
    if [[ "$mode" == "modified" ]] && [[ ! -d "module/${name}/" ]]; then
      echo "::notice::${spec_file}: mode=modified but module/${name}/ does not exist — treating as new."
      mode="new"
    fi
  fi

  # Guard 3 – skip if an open issue with the same mode-appropriate title exists.
  if [[ "$FORCE_REGENERATE" != "true" ]]; then
    if [[ "$mode" == "modified" ]]; then
      issue_title="Update installer component: ${name}"
    else
      issue_title="Implement installer component: ${name}"
    fi
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
  eligible_modes+=("$mode")
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

# Ensure required labels exist before creating any issue.
ensure_labels

# ---------------------------------------------------------------------------
# Pass 2 – create issues for eligible specs
# ---------------------------------------------------------------------------
for i in "${!eligible_specs[@]}"; do
  spec_file="${eligible_specs[$i]}"
  name="${eligible_names[$i]}"
  mode="${eligible_modes[$i]}"

  # Determine whether to assign the Copilot coding agent immediately.
  if [[ "$ASSIGN_AGENT" == "true" ]]; then
    assign_now="true"
  elif [[ "$ASSIGN_AGENT" == "false" ]]; then
    assign_now="false"
  else
    # auto: new → assign immediately; modified → label-gate
    if [[ "$mode" == "new" ]]; then
      assign_now="true"
    else
      assign_now="false"
    fi
  fi

  BODY_FILE="$(mktemp --suffix=.md)"

  if [[ "$mode" == "modified" ]]; then
    # Gather current implementation for the update template.
    current_impl=""
    if [[ -f "module/${name}/debian" ]]; then
      current_impl=$'```bash\n'"$(cat "module/${name}/debian")"$'\n```'
      if [[ -f "module/${name}/linux" ]]; then
        current_impl+=$'\n\n`module/'"${name}"$'/linux`:\n```bash\n'"$(cat "module/${name}/linux")"$'\n```'
      fi
    fi

    issue_title="Update installer component: ${name}"
    render_template "$TEMPLATE_UPDATE" "$name" "$spec_file" "$HELPERS_LIST" \
      "$(cat "$spec_file")" "$current_impl" > "$BODY_FILE"

    if [[ "$assign_now" == "true" ]]; then
      issue_url="$(gh issue create \
        --title "$issue_title" \
        --body-file "$BODY_FILE" \
        --assignee copilot-swe-agent)"
      echo "::notice::Created issue (mode=modified, agent dispatched immediately): ${issue_url}"
    else
      issue_url="$(gh issue create \
        --title "$issue_title" \
        --body-file "$BODY_FILE" \
        --label "needs-generation")"
      echo "::notice::Created issue (mode=modified, awaiting generate-component label): ${issue_url}"
    fi
  else
    issue_title="Implement installer component: ${name}"
    render_template "$TEMPLATE_NEW" "$name" "$spec_file" "$HELPERS_LIST" \
      "$(cat "$spec_file")" > "$BODY_FILE"

    if [[ "$assign_now" == "true" ]]; then
      issue_url="$(gh issue create \
        --title "$issue_title" \
        --body-file "$BODY_FILE" \
        --assignee copilot-swe-agent)"
      echo "::notice::Created issue (mode=new, agent dispatched): ${issue_url}"
    else
      issue_url="$(gh issue create \
        --title "$issue_title" \
        --body-file "$BODY_FILE" \
        --label "needs-generation")"
      echo "::notice::Created issue (mode=new, awaiting generate-component label): ${issue_url}"
    fi
  fi

  rm -f "$BODY_FILE"
done
