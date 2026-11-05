#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# validate_ui_links.sh — Validate all URLs in config.js and HTML files
#
# Extracts every URL from the installer UI files and checks that they are
# reachable (HTTP 200/301/302). Reports broken links with context.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_JS="${REPO_ROOT}/docs/oep-sdk-manager-files/config.js"
SELECTOR_HTML="${REPO_ROOT}/docs/oep-sdk-manager-files/selector.html"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0
FAILURES=()

check_url() {
  local url="$1"
  local source="$2"
  local line="$3"

  # Skip mailto and javascript links
  if [[ "${url}" =~ ^mailto: ]] || [[ "${url}" =~ ^javascript: ]]; then
    SKIP=$((SKIP + 1))
    return
  fi

  local http_code
  http_code=$(curl -o /dev/null -s -w "%{http_code}" -L --max-time 15 \
    -A "Mozilla/5.0 OEP-SDK-Manager-Test" "${url}" 2>/dev/null || echo "000")

  if [[ "${http_code}" =~ ^(200|301|302|303|307|308)$ ]]; then
    PASS=$((PASS + 1))
    echo -e "  ${GREEN}✓${NC} [${http_code}] ${url}"
  else
    FAIL=$((FAIL + 1))
    FAILURES+=("${source}:${line} → [${http_code}] ${url}")
    echo -e "  ${RED}✗${NC} [${http_code}] ${url}  (${source}:${line})"
  fi
}

echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${CYAN} UI Link Validation${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""

# --- Extract URLs from config.js ---
echo -e "${CYAN}Checking config.js URLs...${NC}"

if [[ ! -f "${CONFIG_JS}" ]]; then
  echo -e "${RED}ERROR: config.js not found at ${CONFIG_JS}${NC}"
  exit 1
fi

# Extract all URLs (http/https) with line numbers
while IFS=: read -r line_num line_content; do
  # Extract URLs from the line
  while [[ "${line_content}" =~ (https?://[^\"\'\`\)\},[:space:]]+) ]]; do
    url="${BASH_REMATCH[1]}"
    # Clean trailing punctuation
    url="${url%\"}"
    url="${url%\'}"
    url="${url%\`}"
    check_url "${url}" "config.js" "${line_num}"
    # Remove matched URL to find next one in the same line
    line_content="${line_content#*"${url}"}"
  done
done < <(grep -n 'https\?://' "${CONFIG_JS}")

echo ""

# --- Extract URLs from selector.html ---
echo -e "${CYAN}Checking selector.html URLs...${NC}"

if [[ -f "${SELECTOR_HTML}" ]]; then
  while IFS=: read -r line_num line_content; do
    while [[ "${line_content}" =~ (https?://[^\"\'\`\)\},[:space:]]+) ]]; do
      url="${BASH_REMATCH[1]}"
      url="${url%\"}"
      url="${url%\'}"
      url="${url%\`}"
      check_url "${url}" "selector.html" "${line_num}"
      line_content="${line_content#*"${url}"}"
    done
  done < <(grep -n 'https\?://' "${SELECTOR_HTML}")
fi

echo ""

# --- Summary ---
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e " Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"

if [[ ${FAIL} -gt 0 ]]; then
  echo ""
  echo -e "${RED}Broken links:${NC}"
  for f in "${FAILURES[@]}"; do
    echo -e "  ${RED}✗${NC} ${f}"
  done
  exit 1
fi

exit 0
