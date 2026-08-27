#!/usr/bin/env bash
# validate-modules.sh — single source of truth for component static checks.
#
# Usage:
#   validate-modules.sh [options] [path ...]
#
# With no path arguments: validate the whole tree (module/, profile/).
# With path arguments: restrict reported findings to those paths.
#   IMPORTANT: the uniqueness check always scans the full tree (module/,
#   profile/, common/, license/) to build the symbol table, because a
#   collision is by definition cross-file — only the reporting is filtered.
#
# Options:
#   --github          Emit GitHub Actions workflow-command annotations
#                     (::error file=...::).  Auto-detected via GITHUB_ACTIONS.
#   --only=<check>    Run only the named check.  Repeatable.
#                     Values: bash-syntax, shellcheck, naming, highlight
#   --help            Show this message and exit.
#
# Exit codes:
#   0  all checks passed (highlight warnings never affect exit code)
#   1  one or more blocking checks failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
USE_GITHUB_ANNOTATIONS=0
[[ "${GITHUB_ACTIONS:-}" == "true" ]] && USE_GITHUB_ANNOTATIONS=1
ONLY_CHECKS=()
FILTER_PATHS=()

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --github)
      USE_GITHUB_ANNOTATIONS=1
      shift
      ;;
    --only=*)
      ONLY_CHECKS+=("${1#--only=}")
      shift
      ;;
    --help|-h)
      sed -n '/^# /s/^# //p' "$0"
      exit 0
      ;;
    --)
      shift
      FILTER_PATHS+=("$@")
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      FILTER_PATHS+=("$1")
      shift
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helper: emit an error annotation or plain message
# ---------------------------------------------------------------------------
emit_error() {
  local file="$1" line="$2" col="$3" msg="$4"
  if [[ "$USE_GITHUB_ANNOTATIONS" -eq 1 ]]; then
    if [[ -n "$file" && -n "$line" ]]; then
      echo "::error file=${file},line=${line},col=${col}::${msg}"
    else
      echo "::error::${msg}"
    fi
  else
    if [[ -n "$file" && -n "$line" ]]; then
      echo "${file}:${line}:${col}: error: ${msg}"
    else
      echo "error: ${msg}"
    fi
  fi
}

emit_warning() {
  local file="$1" line="$2" msg="$3"
  if [[ "$USE_GITHUB_ANNOTATIONS" -eq 1 ]]; then
    if [[ -n "$file" ]]; then
      echo "::warning file=${file},line=${line}::${msg}"
    else
      echo "::warning::${msg}"
    fi
  else
    if [[ -n "$file" ]]; then
      echo "${file}:${line}: warning: ${msg}"
    else
      echo "warning: ${msg}"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Determine which paths to validate
# ---------------------------------------------------------------------------
if [[ "${#FILTER_PATHS[@]}" -eq 0 ]]; then
  # No filter: validate whole tree
  mapfile -d '' ALL_FILES < <(
    find module profile -type f ! -name '*.md' -print0 2>/dev/null || true
  )
else
  # Validate only files under the given paths
  mapfile -d '' ALL_FILES < <(
    for p in "${FILTER_PATHS[@]}"; do
      if [[ -f "$p" ]]; then
        printf '%s\0' "$p"
      elif [[ -d "$p" ]]; then
        find "$p" -type f ! -name '*.md' -print0
      fi
    done
  )
fi

# ---------------------------------------------------------------------------
# Helper: should we run a particular check?
# ---------------------------------------------------------------------------
run_check() {
  local name="$1"
  if [[ "${#ONLY_CHECKS[@]}" -eq 0 ]]; then
    return 0
  fi
  for c in "${ONLY_CHECKS[@]}"; do
    [[ "$c" == "$name" ]] && return 0
  done
  return 1
}

OVERALL_FAILED=0

# ---------------------------------------------------------------------------
# Check 1: bash -n syntax
# ---------------------------------------------------------------------------
if run_check bash-syntax; then
  echo "=== bash -n syntax check ==="
  bash_failed=0
  for f in "${ALL_FILES[@]}"; do
    if ! output="$(bash -n "$f" 2>&1)"; then
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        # bash -n output format: file: line N: message
        if [[ "$line" =~ ^([^:]+):\ line\ ([0-9]+):\ (.*)$ ]]; then
          emit_error "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "1" "${BASH_REMATCH[3]}"
        else
          emit_error "$f" "" "" "$line"
        fi
      done <<< "$output"
      bash_failed=1
    fi
  done
  if [[ "$bash_failed" -ne 0 ]]; then
    OVERALL_FAILED=1
  else
    echo "bash -n check passed."
  fi
fi

# ---------------------------------------------------------------------------
# Check 2: shellcheck
# ---------------------------------------------------------------------------
if run_check shellcheck; then
  echo "=== shellcheck ==="
  if [[ "${#ALL_FILES[@]}" -eq 0 ]]; then
    echo "No files to lint."
  elif ! command -v shellcheck >/dev/null 2>&1; then
    emit_error "" "" "" "Missing required tool: shellcheck"
    OVERALL_FAILED=1
  else
    # Module and profile files are sourced fragments with no shebang.
    # SC2148 (missing shebang) is disabled accordingly.
    # All other error-severity findings are treated as failures.
    if ! sc_output="$(shellcheck \
      --shell=bash \
      --exclude=SC2148 \
      --severity=error \
      --check-sourced \
      --format=gcc \
      "${ALL_FILES[@]}" 2>&1)"; then
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        if [[ "$line" =~ ^([^:]+):([0-9]+):([0-9]+):\ (error|warning|info|style):\ (.*)$ ]]; then
          emit_error "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[5]}"
        else
          emit_error "" "" "" "$line"
        fi
      done <<< "$sc_output"
      OVERALL_FAILED=1
    else
      echo "Shellcheck passed."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Check 3: Function-name uniqueness + interface-function suffix
# ---------------------------------------------------------------------------
if run_check naming; then
  echo "=== Function naming convention ==="

  # openedge-cli's subcommand_bootstrap concatenates every selected module/profile
  # fragment plus common/ and license/ into one rendered script.  If two files
  # define the same function name the last one cat-ed silently wins.  Collisions
  # must be detected here, before the rendered script is produced.
  #
  # NOTE: The uniqueness check always scans the *full* tree (module/, profile/,
  # common/, license/) to build the symbol table, because a collision is
  # cross-file by definition.  The reported findings are then filtered to only
  # those involving the paths the caller asked about (FILTER_PATHS).

  tmpfile="$(mktemp)"
  trap 'rm -f "$tmpfile"' EXIT

  # Collect all top-level function definitions across the whole tree.
  # Pattern is tolerant of zero or more spaces before (): funcname() or funcname ()
  # Each output line: funcname:file:lineno
  while IFS= read -r f; do
    while IFS=: read -r lineno decl; do
      func="$(printf '%s' "$decl" | grep -oE '^[a-zA-Z_][a-zA-Z0-9_]+')"
      [[ -n "$func" ]] && printf '%s:%s:%s\n' "$func" "$f" "$lineno"
    done < <(grep -nE '^[a-zA-Z_][a-zA-Z0-9_]* *\(\)' "$f" 2>/dev/null || true)
  done < <(find module profile common license -type f ! -name '*.md' 2>/dev/null | sort) \
    > "$tmpfile"

  naming_failed=0

  # Helper: is a file within the requested FILTER_PATHS (or no filter active)?
  in_filter() {
    local f="$1"
    if [[ "${#FILTER_PATHS[@]}" -eq 0 ]]; then
      return 0
    fi
    for p in "${FILTER_PATHS[@]}"; do
      if [[ "$f" == "$p" || "$f" == "$p/"* ]]; then
        return 0
      fi
    done
    return 1
  }

  # Report any function name defined in more than one file.
  while IFS= read -r func; do
    mapfile -t defs < <(grep "^${func}:" "$tmpfile")
    # Only report if at least one definition is in the filtered paths
    report=0
    for def in "${defs[@]}"; do
      fpath="${def#*:}"; fpath="${fpath%:*}"
      in_filter "$fpath" && report=1 && break
    done
    [[ "$report" -eq 0 ]] && continue

    for def in "${defs[@]}"; do
      fpath="${def#*:}"; fpath="${fpath%:*}"
      ln="${def##*:}"
      others="$(printf '%s\n' "${defs[@]}" | grep -Fv "${func}:${fpath}:" \
        | sed "s|^${func}:||;s|:[0-9]*$||" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
      emit_error "$fpath" "$ln" "1" "Duplicate function '${func}'; also defined in: ${others}"
    done
    naming_failed=1
  done < <(cut -d: -f1 "$tmpfile" | sort | uniq -d)

  # Interface functions must carry a suffix matching their component directory name,
  # since act_find_deps dispatches by that suffix.
  # e.g. debian_90_install_smart_parking must be inside module/smart_parking/
  for dir in module/*/ profile/*/; do
    name="$(basename "$dir")"
    for file in "${dir}"*; do
      [[ -f "$file" ]] || continue
      [[ "$(basename "$file")" == *.md ]] && continue
      in_filter "$file" || continue
      while IFS=: read -r lineno decl; do
        func="$(printf '%s' "$decl" | grep -oE '^[a-zA-Z_][a-zA-Z0-9_]+')"
        [[ -z "$func" ]] && continue
        if [[ "$func" =~ ^[a-z]+_[0-9]{2}_(profile|license|install|remove|start|stop)_ ]] && \
           [[ "$func" != *_${name} ]]; then
          emit_error "$file" "$lineno" "1" \
            "Interface function '${func}' suffix does not match component name '${name}'"
          naming_failed=1
        fi
      done < <(grep -nE '^[a-zA-Z_][a-zA-Z0-9_]* *\(\)' "$file" || true)
    done
  done

  if [[ "$naming_failed" -ne 0 ]]; then
    echo ""
    echo "One or more function name violations were found."
    OVERALL_FAILED=1
  else
    echo "All function names are globally unique and interface functions are correctly named."
  fi
fi

# ---------------------------------------------------------------------------
# Check 4: @@HIGHLIGHT advisory (non-blocking — warnings only, never fails)
# ---------------------------------------------------------------------------
if run_check highlight; then
  echo "=== @@HIGHLIGHT guidance (non-blocking) ==="
  for dir in module/*/; do
    name="$(basename "$dir")"
    for file in "${dir}"*; do
      [[ -f "$file" ]] || continue
      [[ "$(basename "$file")" == "README.md" ]] && continue

      # Determine the highest order number used in this file
      max_order=$(grep -oE "^[a-z]+_([0-9]{2})_(install|start)_${name}" "$file" \
        | grep -oE '[0-9]{2}' | sort -rn | head -1 || true)

      [[ -z "$max_order" ]] && continue

      # Only warn for components with order >= 60
      if [[ "$max_order" -ge 60 ]] 2>/dev/null; then
        if ! grep -q '@@HIGHLIGHT' "$file"; then
          emit_warning "$file" "1" \
            "Component '${name}' (order ${max_order}) has no @@HIGHLIGHT lines. Consider adding one to the start or install function."
        fi
      fi
    done
  done
  echo "@@HIGHLIGHT check complete (warnings only, non-blocking)."
fi

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
if [[ "$OVERALL_FAILED" -ne 0 ]]; then
  echo ""
  echo "One or more checks failed. See findings above."
  exit 1
fi

echo ""
echo "All checks passed."
exit 0
