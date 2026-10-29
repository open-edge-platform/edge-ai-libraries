#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# run_tests.sh — Main test runner for oep-sdk-manager
#
# Usage:
#   ./tests/run_tests.sh              Run all tests
#   ./tests/run_tests.sh links        Run only UI link validation
#   ./tests/run_tests.sh scripts      Run only script validation
#   ./tests/run_tests.sh tutorials    Run only tutorial validation
#   ./tests/run_tests.sh --offline    Skip tests that require network access

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

TOTAL_PASS=0
TOTAL_FAIL=0
SUITE_RESULTS=()

run_suite() {
  local name="$1"
  local script="$2"

  echo ""
  echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${CYAN}║  ${name}${NC}"
  echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════╝${NC}"
  echo ""

  if bash "${script}"; then
    TOTAL_PASS=$((TOTAL_PASS + 1))
    SUITE_RESULTS+=("${GREEN}✓${NC} ${name}")
  else
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    SUITE_RESULTS+=("${RED}✗${NC} ${name}")
  fi
}

# Parse args
RUN_LINKS=false
RUN_SCRIPTS=false
RUN_TUTORIALS=false
OFFLINE=false
RUN_ALL=true

for arg in "$@"; do
  case "${arg}" in
    links)      RUN_LINKS=true; RUN_ALL=false ;;
    scripts)    RUN_SCRIPTS=true; RUN_ALL=false ;;
    tutorials)  RUN_TUTORIALS=true; RUN_ALL=false ;;
    --offline)  OFFLINE=true ;;
    --help|-h)
      echo "Usage: $0 [links|scripts|tutorials] [--offline]"
      echo ""
      echo "  links       Validate URLs in installer UI config"
      echo "  scripts     Validate shell install scripts"
      echo "  tutorials   Validate tutorial markdown files"
      echo "  --offline   Skip network-dependent checks"
      echo ""
      echo "With no arguments, all test suites run."
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown argument: ${arg}${NC}"
      exit 1
      ;;
  esac
done

export OFFLINE

echo -e "${BOLD}${CYAN}OEP SDK Manager — Test Suite${NC}"
echo -e "Repo: $(cd "${SCRIPT_DIR}/.." && pwd)"
echo -e "Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# Run selected suites
if ${RUN_ALL} || ${RUN_SCRIPTS}; then
  run_suite "Script Validation" "${SCRIPT_DIR}/validate_scripts.sh"
fi

if ${RUN_ALL} || ${RUN_TUTORIALS}; then
  run_suite "Tutorial Validation" "${SCRIPT_DIR}/validate_tutorials.sh"
fi

if ${RUN_ALL} || ${RUN_LINKS}; then
  if ${OFFLINE}; then
    echo ""
    echo -e "${YELLOW}⚠ Skipping UI link validation (--offline mode)${NC}"
  else
    run_suite "UI Link Validation" "${SCRIPT_DIR}/validate_ui_links.sh"
  fi
fi

# Final summary
echo ""
echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║  Final Summary${NC}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════╝${NC}"
echo ""

for result in "${SUITE_RESULTS[@]}"; do
  echo -e "  ${result}"
done

echo ""
echo -e "  Suites passed: ${GREEN}${TOTAL_PASS}${NC}  |  Suites failed: ${RED}${TOTAL_FAIL}${NC}"

if [[ ${TOTAL_FAIL} -gt 0 ]]; then
  echo ""
  echo -e "${RED}OVERALL: FAIL${NC}"
  exit 1
else
  echo ""
  echo -e "${GREEN}OVERALL: PASS${NC}"
  exit 0
fi
