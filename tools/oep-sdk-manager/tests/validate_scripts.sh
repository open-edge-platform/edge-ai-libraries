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
EXPECTED_SCRIPTS=(
  "metro-gen-ai-sdk.sh"
  "metro-vision-ai-sdk.sh"
  "metro-visual-ai-demo-kit.sh"
  "uav-mission-compute-sdk.sh"
)

for expected_script in "${EXPECTED_SCRIPTS[@]}"; do
  if [[ -f "${SCRIPTS_DIR}/${expected_script}" ]]; then
    pass "Installer exists: ${expected_script}"
  else
    fail "Missing installer: ${expected_script}"
  fi
done

installer_definitions() {
  sed '/^main "\$@"$/d' "$1"
}

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

  case "${name}" in
    metro-gen-ai-sdk.sh)
      expected_name="Metro Gen AI SDK"
      expected_repos=$'https://github.com/open-edge-platform/edge-ai-libraries|main|edge-ai-libraries\nhttps://github.com/open-edge-platform/metro-ai-suite|main|metro-ai-suite'
      ;;
    metro-vision-ai-sdk.sh)
      expected_name="Metro Vision AI SDK"
      expected_repos=$'https://github.com/open-edge-platform/edge-ai-libraries|main|edge-ai-libraries\nhttps://github.com/open-edge-platform/metro-ai-suite|main|metro-ai-suite\nhttps://github.com/open-edge-platform/scenescape|main|scenescape'
      ;;
    metro-visual-ai-demo-kit.sh)
      expected_name="Metro Visual AI Demo Kit"
      expected_repos="https://github.com/open-edge-platform/metro-ai-suite|main|metro-ai-suite"
      ;;
    uav-mission-compute-sdk.sh)
      expected_name="UAV Mission Compute SDK"
      expected_repos="https://github.com/open-edge-platform/federal-and-aerospace-ai-suite|main|federal-and-aerospace-ai-suite"
      ;;
    *)
      fail "Unexpected installer: ${name}"
      continue
      ;;
  esac

  actual_config=$(bash -c 'source /dev/stdin; printf "%s\n" "${NAME}" "${repositories[@]}"' < <(installer_definitions "${script}"))
  if [[ "${actual_config}" == "${expected_name}"$'\n'"${expected_repos}" ]]; then
    pass "${name}: SDK name and main-branch clone destinations match"
  else
    fail "${name}: SDK name or repository configuration mismatch"
  fi

  for version in 24.04 26.04; do
    if bash -c 'source /dev/stdin; check_supported_os ubuntu "$1"' _ "${version}" \
      < <(installer_definitions "${script}") >/dev/null 2>&1; then
      pass "${name}: Accepts Ubuntu ${version}"
    else
      fail "${name}: Must accept Ubuntu ${version}"
    fi
  done

  for version in 24.04 26.04 22.04; do
    if output=$(bash -c '
      source /dev/stdin
      bring_up_uav_sdk() { :; }
      main --skip-system-check --skip-docker --skip-images --skip-git-clone
    ' < <(installer_definitions "${script}" | sed "s|source /etc/os-release|NAME='Fixture Linux'; ID=ubuntu; VERSION_ID=${version}|") 2>&1); then
      if [[ "${version}" == "22.04" ]]; then
        fail "${name}: Main must reject Ubuntu 22.04 even with skip flags"
      elif [[ "${output}" != *"${expected_name} installation completed successfully!"* ]]; then
        fail "${name}: OS detection must preserve the SDK name"
      else
        pass "${name}: Main accepts Ubuntu ${version} with operations skipped"
      fi
    elif [[ "${version}" == "22.04" && "${output}" == *"Unsupported operating system:"* ]]; then
      pass "${name}: Main rejects Ubuntu 22.04 even with skip flags"
    else
      fail "${name}: Unexpected main result for Ubuntu ${version}: ${output}"
    fi
  done

  for os_version in "ubuntu:22.04" "ubuntu:25.10" "debian:26.04" "unknown:unknown"; do
    IFS=: read -r os_id version <<< "${os_version}"
    if output=$(bash -c 'source /dev/stdin; check_supported_os "$1" "$2"' _ "${os_id}" "${version}" \
      < <(installer_definitions "${script}") 2>&1); then
      fail "${name}: Must reject ${os_version}"
    elif [[ "${output}" == *"Unsupported operating system:"* ]]; then
      pass "${name}: Rejects ${os_version} with an explicit error"
    else
      fail "${name}: OS validation failed without the expected error for ${os_version}"
    fi
  done

  if grep -qF 'check_supported_os "${os_id}" "${os_version}"' "${script}"; then
    pass "${name}: Main validates the host OS"
  else
    fail "${name}: Main must validate the host OS"
  fi

  if help_output=$(bash "${script}" --help) && [[ "${help_output}" == *"${expected_name} Installation Script"* ]]; then
    pass "${name}: Help uses the SDK name"
  else
    fail "${name}: Help must display the SDK name"
  fi

  echo ""
done

uav_script="${SCRIPTS_DIR}/uav-mission-compute-sdk.sh"
if [[ -f "${uav_script}" ]]; then
  test_home=$(mktemp -d)
  sdk_dir="${test_home}/oep/federal-and-aerospace-ai-suite/uav-mission-compute-sdk"
  mkdir -p "${sdk_dir}"
  if output=$(HOME="${test_home}" bash -c '
    source /dev/stdin
    command_exists() { return 0; }
    make() { printf "%s|%s\n" "${PWD}" "$*"; }
    populate_env_credentials() { printf "env|%s\n" "$1"; }
    bring_up_uav_sdk
  ' < <(installer_definitions "${uav_script}") 2>&1) \
    && [[ "${output}" == *"${sdk_dir}|init"* ]] \
    && [[ "${output}" == *"${sdk_dir}|up-sim-camera"* ]] \
    && [[ "${output}" == *"env|${sdk_dir}/.env"* ]]; then
    pass "UAV startup uses the standalone Federal and Aerospace suite directory"
  else
    fail "UAV startup working directory mismatch: ${output}"
  fi
  rmdir "${sdk_dir}" "${test_home}/oep/federal-and-aerospace-ai-suite" "${test_home}/oep" "${test_home}"
fi

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
