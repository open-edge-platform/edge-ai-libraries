#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# validate_tutorials.sh — Validate tutorial markdown files
#
# Checks:
#   1. Toctree entries in index.md resolve to actual files
#   2. Each SDK has a get-started.md
#   3. Image references (![...](path)) resolve to actual files on disk
#   4. External URLs in markdown are reachable
#   5. Markdown headings structure (has H1, no orphan anchors)
#   6. Code blocks are properly fenced
#   7. No broken internal cross-references
#   8. Non-root container examples and host-owned workspace output

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCS_DIR="${REPO_ROOT}/docs"
USER_GUIDE="${DOCS_DIR}/user-guide"

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
echo -e "${CYAN} Tutorial Validation${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""

# ───────────────────────────────────────────
# 1. Verify toctree entries in index.md
# ───────────────────────────────────────────
echo -e "${CYAN}[1] Toctree entries in index.md${NC}"
INDEX_FILE="${USER_GUIDE}/index.md"

if [[ ! -f "${INDEX_FILE}" ]]; then
  fail "index.md not found at ${INDEX_FILE}"
else
  pass "index.md exists"

  # Extract toctree references (e.g., "metro-vision-ai-sdk/get-started")
  while IFS= read -r line; do
    # Match lines like: "Metro Vision AI SDK <metro-vision-ai-sdk/get-started>"
    if [[ "${line}" =~ \<([^>]+)\> ]]; then
      ref="${BASH_REMATCH[1]}"
      # Remove .md extension if present, then add it back
      ref="${ref%.md}"
      target="${USER_GUIDE}/${ref}.md"
      if [[ -f "${target}" ]]; then
        pass "Toctree entry resolves: ${ref}"
      else
        fail "Toctree entry NOT FOUND: ${ref} → ${target}"
      fi
    fi
  done < <(sed -n '/:::{toctree}/,/:::/p' "${INDEX_FILE}")
fi
echo ""

# ───────────────────────────────────────────
# 2. Each SDK directory has get-started.md
# ───────────────────────────────────────────
echo -e "${CYAN}[2] SDK get-started.md files${NC}"

EXPECTED_SDKS=("metro-vision-ai-sdk" "metro-gen-ai-sdk" "metro-visual-ai-demo-kit" "uav-mission-compute-sdk")

for sdk in "${EXPECTED_SDKS[@]}"; do
  sdk_dir="${USER_GUIDE}/${sdk}"
  if [[ ! -d "${sdk_dir}" ]]; then
    fail "SDK directory missing: ${sdk}/"
    continue
  fi
  pass "SDK directory exists: ${sdk}/"

  if [[ -f "${sdk_dir}/get-started.md" ]]; then
    pass "${sdk}/get-started.md exists"
  else
    fail "${sdk}/get-started.md MISSING"
  fi
done
echo ""

# ───────────────────────────────────────────
# 3. Image references
# ───────────────────────────────────────────
echo -e "${CYAN}[3] Image references in markdown${NC}"

while IFS= read -r md_file; do
  md_name="${md_file#"${REPO_ROOT}/"}"
  md_dir="$(dirname "${md_file}")"

  # Extract markdown image refs: ![alt](path)
  while IFS=: read -r line_num match; do
    # Extract the image path from ![...](path)
    img_path=$(echo "${match}" | grep -oP '!\[[^\]]*\]\(\K[^)]+' || true)
    if [[ -z "${img_path}" ]]; then
      continue
    fi

    # Skip external URLs
    if [[ "${img_path}" =~ ^https?:// ]]; then
      continue
    fi

    # Resolve relative path
    full_path="${md_dir}/${img_path}"
    if [[ -f "${full_path}" ]]; then
      pass "${md_name}:${line_num} → ${img_path}"
    else
      fail "${md_name}:${line_num} → Image NOT FOUND: ${img_path}"
    fi
  done < <(grep -n '!\[' "${md_file}" || true)

done < <(find "${DOCS_DIR}" -name '*.md' -type f | sort)
echo ""

# ───────────────────────────────────────────
# 4. External URLs in markdown files
# ───────────────────────────────────────────
echo -e "${CYAN}[4] External URLs in markdown files${NC}"

URL_COUNT=0
URL_FAIL=0

if [[ "${OFFLINE:-false}" == "true" ]]; then
  warn "Skipping external tutorial URLs (--offline mode)"
else
  while IFS= read -r md_file; do
    md_name="${md_file#"${REPO_ROOT}/"}"

    while IFS=: read -r line_num line_content; do
      # Extract URLs from markdown links [text](url) and bare URLs
      while [[ "${line_content}" =~ (https?://[^\)\"\'\>\`[:space:]]+) ]]; do
        url="${BASH_REMATCH[1]}"
        # Clean trailing punctuation
        url="${url%\.}"
        url="${url%,}"

        # Skip localhost, placeholder, and example URLs
        if [[ "${url}" =~ localhost ]] || [[ "${url}" =~ \<[a-zA-Z_]+\> ]] || [[ "${url}" =~ ^https?://\< ]]; then
          WARN=$((WARN + 1))
          echo -e "  ${YELLOW}⚠${NC} Skipped (placeholder): ${md_name}:${line_num} → ${url}"
          line_content="${line_content#*"${url}"}"
          continue
        fi

        URL_COUNT=$((URL_COUNT + 1))

        http_code=$(curl -o /dev/null -s -w "%{http_code}" -L --max-time 15 \
          -A "Mozilla/5.0 OEP-SDK-Manager-Test" "${url}" 2>/dev/null || echo "000")

        if [[ "${http_code}" =~ ^(200|301|302|303|307|308)$ ]]; then
          pass "[${http_code}] ${md_name}:${line_num} → ${url}"
        else
          URL_FAIL=$((URL_FAIL + 1))
          fail "[${http_code}] ${md_name}:${line_num} → ${url}"
        fi

        line_content="${line_content#*"${url}"}"
      done
    done < <(grep -n 'https\?://' "${md_file}" || true)

  done < <(find "${DOCS_DIR}" -name '*.md' -type f | sort)
fi
echo ""

# ───────────────────────────────────────────
# 5. Markdown structure
# ───────────────────────────────────────────
echo -e "${CYAN}[5] Markdown structure${NC}"

while IFS= read -r md_file; do
  md_name="${md_file#"${REPO_ROOT}/"}"

  # Check for H1 heading
  if grep -qm1 '^# ' "${md_file}"; then
    pass "${md_name}: Has H1 heading"
  else
    warn "${md_name}: No H1 heading found"
  fi

  # Check code blocks are balanced (even number of ```)
  fence_count=$(grep -c '^```' "${md_file}" || true)
  if (( fence_count % 2 == 0 )); then
    pass "${md_name}: Code fences balanced (${fence_count})"
  else
    fail "${md_name}: Unbalanced code fences (${fence_count} found)"
  fi

done < <(find "${DOCS_DIR}" -name '*.md' -type f | sort)
echo ""

# ───────────────────────────────────────────
# 6. Tutorial numbering continuity
# ───────────────────────────────────────────
echo -e "${CYAN}[6] Tutorial numbering continuity${NC}"

for sdk in "${EXPECTED_SDKS[@]}"; do
  sdk_dir="${USER_GUIDE}/${sdk}"
  if [[ ! -d "${sdk_dir}" ]]; then
    continue
  fi

  tutorials=$(find "${sdk_dir}" -name 'tutorial-*.md' -type f | sort)
  if [[ -z "${tutorials}" ]]; then
    warn "${sdk}: No tutorial files found"
    continue
  fi

  prev_num=0
  while IFS= read -r tut_file; do
    tut_name=$(basename "${tut_file}" .md)
    num=$(echo "${tut_name}" | grep -oP '\d+' || true)
    if [[ -z "${num}" ]]; then
      fail "${sdk}/${tut_name}: Cannot parse tutorial number"
      continue
    fi

    expected=$((prev_num + 1))
    if [[ "${num}" -eq "${expected}" ]]; then
      pass "${sdk}/tutorial-${num}.md: Sequential (${num})"
    else
      fail "${sdk}/tutorial-${num}.md: Gap in numbering (expected ${expected}, got ${num})"
    fi
    prev_num="${num}"
  done <<< "${tutorials}"
done
echo ""

# ───────────────────────────────────────────
# 7. Toctree references in get-started.md (tutorial links)
# ───────────────────────────────────────────
echo -e "${CYAN}[7] Get-started toctree references${NC}"

for sdk in "${EXPECTED_SDKS[@]}"; do
  gs_file="${USER_GUIDE}/${sdk}/get-started.md"
  if [[ ! -f "${gs_file}" ]]; then
    continue
  fi

  # Check for toctree entries
  if grep -q ':::{toctree}' "${gs_file}"; then
    while IFS= read -r line; do
      if [[ "${line}" =~ \<([^>]+)\> ]]; then
        ref="${BASH_REMATCH[1]}"
        ref="${ref%.md}"
        target="${USER_GUIDE}/${sdk}/${ref}.md"
        if [[ -f "${target}" ]]; then
          pass "${sdk}/get-started.md → ${ref}"
        else
          fail "${sdk}/get-started.md → ${ref} NOT FOUND"
        fi
      fi
    done < <(sed -n '/:::{toctree}/,/:::/p' "${gs_file}")
  fi
done
echo ""

# ───────────────────────────────────────────
# 8. Non-root container examples
# ───────────────────────────────────────────
echo -e "${CYAN}[8] Non-root container examples${NC}"

shell_commands() {
  awk '
    /^```(bash|sh|shell)$/ { in_shell = 1; next }
    /^```/ { in_shell = 0 }
    in_shell {
      if (sub(/\\[[:space:]]*$/, "")) {
        command = command $0 " "
      } else {
        print command $0
        command = ""
      }
    }
  ' "$1"
}

root_user_pattern="(^|[[:space:]])(--user([[:space:]]*=[[:space:]]*|[[:space:]]+)|-u[[:space:]=]*)[\"']?(root|0+)(:[^[:space:]\"']*)?[\"']?([[:space:]]|$)"
root_package_setup_pattern='^[[:space:]]*docker exec --user root metro-openvino-gpu apt-get (update([[:space:]]+&&)?|install -y --no-install-recommends([[:space:]]+/gpu-debs/[[:alnum:]_.+~-]+[.]deb)+)[[:space:]]*$'

while IFS= read -r md_file; do
  md_name="${md_file#"${REPO_ROOT}/"}"
  root_runtime_found=false
  while IFS= read -r command; do
    # Permit only direct APT setup in the named GPU container, not root inference.
    if [[ "${md_file}" == "${USER_GUIDE}/metro-vision-ai-sdk/tutorial-1.md" ]] &&
       [[ "${command}" =~ ${root_package_setup_pattern} ]]; then
      continue
    fi
    root_runtime_found=true
  done < <(shell_commands "${md_file}" | grep -E -- "${root_user_pattern}" || true)
  if [[ "${root_runtime_found}" == "true" ]]; then
    fail "${md_name}: Root runtime user flag in a shell example"
  else
    pass "${md_name}: No root runtime user flags"
  fi
done < <(find "${DOCS_DIR}" -name '*.md' -type f | sort)

OWNERSHIP_TUTORIALS=(
  "metro-vision-ai-sdk/get-started.md"
  "metro-vision-ai-sdk/tutorial-1.md"
  "metro-vision-ai-sdk/tutorial-3.md"
  "metro-vision-ai-sdk/tutorial-4.md"
  "metro-vision-ai-sdk/tutorial-5.md"
  "metro-visual-ai-demo-kit/tutorial-1.md"
)

for tutorial in "${OWNERSHIP_TUTORIALS[@]}"; do
  md_file="${USER_GUIDE}/${tutorial}"
  if [[ ! -f "${md_file}" ]]; then
    fail "${tutorial}: Missing ownership-sensitive tutorial"
    continue
  fi

  run_count=0
  while IFS= read -r command; do
    run_count=$((run_count + 1))
    if [[ "${command}" == *'--user "$(id -u):$(id -g)"'* ]]; then
      pass "${tutorial}: Container ${run_count} uses the host UID:GID"
    else
      fail "${tutorial}: Container ${run_count} must use the host UID:GID"
    fi
  done < <(shell_commands "${md_file}" | grep -E '^[[:space:]]*docker run ' || true)

  if [[ "${run_count}" -eq 0 ]]; then
    fail "${tutorial}: No container runtime examples found"
  fi
  if shell_commands "${md_file}" | grep -E '(/root/\.Xauthority|HOME=/root([[:space:]]|$)|sudo[[:space:]]+\./metro_vision_pipeline\.sh)' >/dev/null; then
    fail "${tutorial}: Root home or sudo wrapper conflicts with non-root execution"
  else
    pass "${tutorial}: No root home or sudo wrapper assumptions"
  fi
done
echo ""

# ───────────────────────────────────────────
# 9. Selector installer and tutorial targets
# ───────────────────────────────────────────
echo -e "${CYAN}[9] Selector targets${NC}"
CONFIG_JS="${DOCS_DIR}/oep-sdk-manager-files/config.js"
INSTALL_BASE="https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/"
EXPECTED_INSTALLERS=(
  "metro-gen-ai-sdk.sh"
  "metro-vision-ai-sdk.sh"
  "metro-visual-ai-demo-kit.sh"
  "uav-mission-compute-sdk.sh"
)

if [[ ! -f "${CONFIG_JS}" ]]; then
  fail "Selector configuration is missing"
else
  for installer in "${EXPECTED_INSTALLERS[@]}"; do
    if grep -qF "${INSTALL_BASE}${installer}" "${CONFIG_JS}" && [[ -f "${REPO_ROOT}/scripts/${installer}" ]]; then
      pass "Selector points to main installer: ${installer}"
    else
      fail "Selector installer missing or invalid: ${installer}"
    fi
  done

  install_count=0
  while IFS= read -r url; do
    install_count=$((install_count + 1))
    installer="${url##*/}"
    if [[ "${url}" == "${INSTALL_BASE}${installer}" ]] && [[ -f "${REPO_ROOT}/scripts/${installer}" ]]; then
      pass "Installer URL resolves locally: ${installer}"
    elif [[ "${url}" =~ ^https://raw\.githubusercontent\.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026\.[12]\.0/metro-ai-suite/metro-sdk-manager/scripts/(oep-vision-ai-sdk|oep-gen-ai-sdk|visual-ai-demo-kit|uav-mission-compute-sdk)\.sh$ ]]; then
      pass "Versioned installer URL uses its original release path: ${installer}"
    else
      fail "Installer URL must use a current main installer or an original 2026.1/2026.2 release path: ${url}"
    fi
  done < <(grep -oE 'https://raw\.githubusercontent\.com/[^`" ]+\.sh' "${CONFIG_JS}" || true)
  if [[ "${install_count}" -ne 11 ]]; then
    fail "Expected 11 selector installer rules, found ${install_count}"
  fi

  while IFS= read -r target; do
    sdk="${target%/get-started.html}"
    if [[ -f "${USER_GUIDE}/${sdk}/get-started.md" ]]; then
      pass "Selector tutorial resolves locally: ${sdk}"
    else
      fail "Selector tutorial is missing: ${sdk}"
    fi
  done < <(grep -oE '[a-z-]+/get-started\.html' "${CONFIG_JS}" || true)
fi
echo ""

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
