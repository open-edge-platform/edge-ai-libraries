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
#                      spec status only (A→assign, M→label-gate).
#   REJECTED_LOOKBACK_DAYS
#                      Look back this many days for a closed-unmerged PR or
#                      closed issue for the same component. If found, always
#                      force label-gated dispatch. Default: 30.
#
# Requires: gh (GitHub CLI) authenticated via GH_TOKEN env var, jq.
set -euo pipefail

SPECS_LIST="${1:?Usage: $0 <specs_list_file>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_NEW="${SCRIPT_DIR}/../templates/component-new-task.md"
TEMPLATE_UPDATE="${SCRIPT_DIR}/../templates/component-update-task.md"
FORCE_REGENERATE="${FORCE_REGENERATE:-false}"
MAX_TASKS_PER_RUN="${MAX_TASKS_PER_RUN:-3}"
ASSIGN_AGENT="${ASSIGN_AGENT:-auto}"
REJECTED_LOOKBACK_DAYS="${REJECTED_LOOKBACK_DAYS:-30}"

# Validate MAX_TASKS_PER_RUN is a positive integer.
if ! [[ "$MAX_TASKS_PER_RUN" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::MAX_TASKS_PER_RUN must be a positive integer, got: '${MAX_TASKS_PER_RUN}'"
  exit 1
fi
if ! [[ "$REJECTED_LOOKBACK_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::REJECTED_LOOKBACK_DAYS must be a positive integer, got: '${REJECTED_LOOKBACK_DAYS}'"
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
  gh label create "NEEDS-GENERATION" \
    --description "Modified-spec issue awaiting maintainer dispatch of the Copilot coding agent" \
    --color "FBCA04" \
    --force 2>/dev/null || true
  gh label create "GENERATE-COMPONENT" \
    --description "Apply to a NEEDS-GENERATION issue to dispatch the Copilot coding agent" \
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
#                        <rejected_prior_art> <spec_content> [<current_impl>]
# ---------------------------------------------------------------------------
render_template () {
  local template="$1"
  local name="$2"
  local spec_file="$3"
  local helpers_list="$4"
  local rejected_prior_art="$5"
  local spec_content="$6"
  local current_impl="${7:-}"
  local body
  body="$(<"$template")"

  body="${body//\{\{NAME\}\}/$name}"
  body="${body//\{\{SPEC_FILE\}\}/$spec_file}"
  body="${body//\{\{HELPERS_LIST\}\}/$helpers_list}"
  body="${body//\{\{CURRENT_IMPLEMENTATION\}\}/$current_impl}"
  body="${body//\{\{REJECTED_PRIOR_ART\}\}/$rejected_prior_art}"
  body="${body//\{\{SPEC_CONTENT\}\}/$spec_content}"

  printf '%s\n' "$body"
}

# Build list of available helpers once (embedded into every issue body).
# Extract real callable function symbols from common/ and license/, annotated
# with their source file.  Exclude framework-internal functions (act_*, _*,
# subcommand_*, ensure_panelled_logs, ensure_license_gate) that components
# must not call directly.
HELPERS_LIST="$(
  grep -roE '^ensure_[a-z0-9_]+' common/ license/ 2>/dev/null \
    | grep -Ev ':(ensure_panelled_logs|ensure_license_gate)$' \
    | sed 's/^\(.*\):\(.*\)/  - \2  (\1)/' \
    | sort -u
)"

# Rejected-prior-art discovery outputs.
REJECTED_PRIOR_ART_BLOCK=""
REJECTED_PRIOR_ART_REF=""

find_rejected_prior_art () {
  local name="$1"
  local spec_file="$2"
  local since_date
  local search_q
  local prs_json
  local issues_json
  local hit
  local hit_kind
  local hit_number
  local hit_title

  REJECTED_PRIOR_ART_BLOCK=""
  REJECTED_PRIOR_ART_REF=""

  since_date="$(date -u -d "-${REJECTED_LOOKBACK_DAYS} days" +%Y-%m-%d 2>/dev/null || true)"
  if [[ -n "$since_date" ]]; then
    search_q="updated:>=${since_date}"
  else
    search_q=""
  fi

  if ! prs_json="$(gh pr list \
    --state closed \
    --limit 200 \
    --search "$search_q" \
    --json number,title,mergedAt,headRefName,body,updatedAt 2>/dev/null)"; then
    echo "::notice::${spec_file}: rejected-prior-art PR check could not be completed; continuing with normal spec-status dispatch rule."
    prs_json="[]"
  fi

  if ! issues_json="$(gh issue list \
    --state closed \
    --limit 200 \
    --search "$search_q" \
    --json number,title,updatedAt 2>/dev/null)"; then
    echo "::notice::${spec_file}: rejected-prior-art issue check could not be completed; continuing with normal spec-status dispatch rule."
    issues_json="[]"
  fi

  hit="$(jq -rn \
    --arg name "$name" \
    --arg needle "${name,,}" \
    --argjson prs "$prs_json" \
    --argjson issues "$issues_json" \
    '
      ($prs
        | map(
            select(.mergedAt == null)
            | select(
                ([
                   (.headRefName // ""),
                   (.title // ""),
                   (.body // "")
                 ]
                 | map(ascii_downcase)
                 | join("\n")
                ) | contains($needle)
              )
            | {
                kind: "pr",
                number: .number,
                title: (.title // ""),
                updatedAt: (.updatedAt // "")
              }
          )) as $pr_hits
      | ($issues
          | map(
              select(
                (.title // "") == ("Implement installer component: " + $name)
                or
                (.title // "") == ("Update installer component: " + $name)
              )
              | {
                  kind: "issue",
                  number: .number,
                  title: (.title // ""),
                  updatedAt: (.updatedAt // "")
                }
            )) as $issue_hits
      | ($pr_hits + $issue_hits | sort_by(.updatedAt) | last) as $hit
      | if $hit == null
        then ""
        else "\($hit.kind)\t\($hit.number)\t\($hit.title)"
        end
    ')"

  if [[ -n "$hit" ]]; then
    IFS=$'\t' read -r hit_kind hit_number hit_title <<< "$hit"
    if [[ "$hit_kind" == "pr" ]]; then
      REJECTED_PRIOR_ART_REF="PR #${hit_number}"
      REJECTED_PRIOR_ART_BLOCK="$(cat <<EOF
## ⚠️ Rejected prior attempt

      A previous implementation attempt for this component was closed without merging (${REJECTED_PRIOR_ART_REF}). Treat that work as **rejected prior art**, not a baseline.

- Start strictly from the current \`main\` branch.
- Do **not** resume, cherry-pick from, or otherwise reuse a branch from a closed PR.
- In your PR description, explain how your approach differs from ${REJECTED_PRIOR_ART_REF} and why.
EOF
)"
    else
      REJECTED_PRIOR_ART_REF="issue #${hit_number}"
      REJECTED_PRIOR_ART_BLOCK="$(cat <<EOF
## ⚠️ Rejected prior attempt

A previous implementation attempt for this component was previously closed (${REJECTED_PRIOR_ART_REF}). Treat that work as **rejected prior art**, not a baseline.

- Start strictly from the current \`main\` branch.
- Do **not** resume, cherry-pick from, or otherwise reuse a branch from a closed PR.
- In your PR description, explain how your approach differs from the rejected attempt and why.
EOF
)"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Pass 1 – collect eligible specs (apply Guards 2 and 3)
# ---------------------------------------------------------------------------
eligible_specs=()
eligible_names=()
eligible_statuses=()
eligible_templates=()
eligible_has_baselines=()

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

  # Map status letter to normalized spec status.
  if [[ "$status" == "M" ]]; then
    spec_status="M"
  else
    spec_status="A"
  fi

  # Derive component name: strip directory + .md suffix, lowercase, dashes → underscores
  raw_name="$(basename "$spec_file" .md)"
  name="${raw_name,,}"
  name="${name//-/_}"

  if [[ -d "module/${name}/" ]]; then
    has_baseline="true"
    template_kind="update"
    issue_title="Update installer component: ${name}"
  else
    has_baseline="false"
    template_kind="new"
    issue_title="Implement installer component: ${name}"
  fi

  # Guard 2 – newly added specs still skip when the module directory exists.
  # NOTE: template selection and dispatch gating are intentionally decoupled:
  # demotion or template fallback must NEVER escalate privilege.
  if [[ "$FORCE_REGENERATE" != "true" ]]; then
    if [[ "$spec_status" == "A" ]] && [[ "$has_baseline" == "true" ]]; then
      echo "::notice::Skipping ${spec_file}: module/${name}/ already exists. Delete the module directory or set FORCE_REGENERATE=true to regenerate."
      continue
    fi
  fi

  # Guard 3 – skip if an open issue with the same mode-appropriate title exists.
  if [[ "$FORCE_REGENERATE" != "true" ]]; then
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
  eligible_statuses+=("$spec_status")
  eligible_templates+=("$template_kind")
  eligible_has_baselines+=("$has_baseline")
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
  spec_status="${eligible_statuses[$i]}"
  template_kind="${eligible_templates[$i]}"
  has_baseline="${eligible_has_baselines[$i]}"

  # Determine whether to assign the Copilot coding agent immediately.
  # Default dispatch decision is derived from spec status only:
  #   A (added) -> assign immediately
  #   M (modified) -> label-gate
  if [[ "$ASSIGN_AGENT" == "true" ]]; then
    assign_now="true"
  elif [[ "$ASSIGN_AGENT" == "false" ]]; then
    assign_now="false"
  else
    if [[ "$spec_status" == "A" ]]; then
      assign_now="true"
    else
      assign_now="false"
    fi
  fi

  find_rejected_prior_art "$name" "$spec_file"
  rejected_prior_art_forced="false"
  if [[ -n "$REJECTED_PRIOR_ART_BLOCK" ]]; then
    assign_now="false"
    rejected_prior_art_forced="true"
    echo "::notice::${spec_file}: forcing NEEDS-GENERATION because rejected prior attempt detected (${REJECTED_PRIOR_ART_REF})."
  fi

  BODY_FILE="$(mktemp --suffix=.md)"

  if [[ "$template_kind" == "update" ]]; then
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
      "$REJECTED_PRIOR_ART_BLOCK" "$(cat "$spec_file")" "$current_impl" > "$BODY_FILE"

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
        --label "NEEDS-GENERATION")"
      echo "::notice::Created issue (template=update, awaiting GENERATE-COMPONENT label): ${issue_url}"
    fi
  else
    issue_title="Implement installer component: ${name}"
    render_template "$TEMPLATE_NEW" "$name" "$spec_file" "$HELPERS_LIST" \
      "$REJECTED_PRIOR_ART_BLOCK" "$(cat "$spec_file")" > "$BODY_FILE"

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
        --label "NEEDS-GENERATION")"
      echo "::notice::Created issue (template=new, awaiting GENERATE-COMPONENT label): ${issue_url}"
    fi
  fi

  echo "::notice::dispatch decision: spec=${spec_file}; spec_status=${spec_status}; has_baseline=${has_baseline}; template=${template_kind}; dispatched=${assign_now}; rejected_prior_art=${rejected_prior_art_forced}"

  rm -f "$BODY_FILE"
done
