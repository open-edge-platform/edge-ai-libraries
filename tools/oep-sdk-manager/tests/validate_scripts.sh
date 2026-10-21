#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# validate_scripts.sh — Validate install scripts
#
# Checks:
#   1. ShellCheck linting (if installed)
#   2. Bash syntax validation (bash -n)
#   3. Required patterns: shebang, set -euo pipefail, repositories, images, NAME
#   4. Docker image tags are pinned (not :latest)
#   5. Expected CLI flags are supported
#   6. Script is executable or can be sourced

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0
FAILURES=()

pass() {
  PASS=$((PASS + 1))
  echo -e "  ${GREEN}✓${NC} $1"
}

fail() {
  FAIL=$((FAIL + 1))
  FAILURES+=("$1")
  echo -e "  ${RED}✗${NC} $1"
}

warn() {
  WARN=$((WARN + 1))
  echo -e "  ${YELLOW}⚠${NC} $1"
}

echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${CYAN} Script Validation${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""

if [[ ! -d "${SCRIPTS_DIR}" ]]; then
  echo -e "${RED}ERROR: scripts/ directory not found${NC}"
  exit 1
fi

SCRIPT_FILES=("${SCRIPTS_DIR}"/*.sh)

if [[ ${#SCRIPT_FILES[@]} -eq 0 ]]; then
  echo -e "${RED}ERROR: No .sh files found in scripts/${NC}"
  exit 1
fi

for script in "${SCRIPT_FILES[@]}"; do
  name="$(basename "${script}")"
  echo -e "${CYAN}--- ${name} ---${NC}"

  # 1. Bash syntax check
  if bash -n "${script}" 2>/dev/null; then
    pass "Bash syntax valid"
  else
    fail "${name}: Bash syntax error"
  fi

  # 2. ShellCheck (if available)
  if command -v shellcheck >/dev/null 2>&1; then
    if shellcheck -S warning -e SC1091 "${script}" >/dev/null 2>&1; then
      pass "ShellCheck passed"
    else
      fail "${name}: ShellCheck warnings/errors"
      shellcheck -S warning -e SC1091 "${script}" 2>&1 || true
    fi
  else
    warn "ShellCheck not installed — skipping"
  fi

  # 3. Shebang line
  first_line=$(head -1 "${script}")
  if [[ "${first_line}" == "#!/bin/bash" ]] || [[ "${first_line}" == "#!/usr/bin/env bash" ]]; then
    pass "Shebang present: ${first_line}"
  else
    fail "${name}: Missing or incorrect shebang (got: ${first_line})"
  fi

  # 4. Strict mode
  if grep -q 'set -euo pipefail' "${script}"; then
    pass "Strict mode (set -euo pipefail)"
  else
    fail "${name}: Missing 'set -euo pipefail'"
  fi

  # 5. Required arrays
  if grep -q '^repositories=(' "${script}"; then
    pass "repositories=() array defined"
  else
    fail "${name}: Missing repositories=() array"
  fi

  if grep -q '^images=(' "${script}"; then
    pass "images=() array defined"
  else
    fail "${name}: Missing images=() array"
  fi

  # 6. NAME variable
  if grep -q '^NAME=' "${script}"; then
    name_val=$(grep '^NAME=' "${script}" | head -1 | cut -d'"' -f2)
    pass "NAME defined: \"${name_val}\""
  else
    fail "${name}: Missing NAME variable"
  fi

  # 7. Docker image tags — no :latest allowed
  latest_images=$(grep -oP '"[^"]+:latest"' "${script}" || true)
  if [[ -z "${latest_images}" ]]; then
    pass "No :latest Docker image tags"
  else
    fail "${name}: Found :latest Docker image tags: ${latest_images}"
  fi

  # 8. Expected CLI flags
  for flag in "--skip-system-check" "--skip-docker" "--skip-images" "--skip-git-clone" "--help"; do
    if grep -qF -- "${flag}" "${script}"; then
      pass "Supports ${flag}"
    else
      fail "${name}: Missing support for ${flag}"
    fi
  done

  # 9. Repository URLs are valid format
  while IFS= read -r repo_line; do
    repo_url=$(echo "${repo_line}" | grep -oP 'https://github\.com/[^"|]+' || true)
    if [[ -n "${repo_url}" ]]; then
      if [[ "${repo_url}" =~ ^https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+ ]]; then
        pass "Valid repo URL: ${repo_url}"
      else
        fail "${name}: Malformed repo URL: ${repo_url}"
      fi
    fi
  done < <(grep -A 20 '^repositories=(' "${script}" | grep 'github.com')

  echo ""
done

# --- Summary ---
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e " Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"

if [[ ${FAIL} -gt 0 ]]; then
  echo ""
  echo -e "${RED}Failures:${NC}"
  for f in "${FAILURES[@]}"; do
    echo -e "  ${RED}✗${NC} ${f}"
  done
  exit 1
fi

exit 0
