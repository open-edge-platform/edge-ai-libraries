# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Shared helper for fetching third-party scripts/files before executing or
# trusting them (OWASP A08:2021 Software and Data Integrity Failures) —
# every curl-then-run call site in this repo should route through here
# instead of downloading and executing bytes with no verification.

# sha256_of file — prints the lowercase hex SHA-256 digest of file, using
# whichever hashing tool is available (sha256sum on Linux, shasum on macOS).
sha256_of() {
  local file="$1"
  if command_exists sha256sum; then
    sha256sum "$file" | awk '{print $1}'
  elif command_exists shasum; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    error "No SHA-256 tool available (sha256sum/shasum) to verify '$file'."
  fi
}

# assert_shell_script file label — rejects a download that doesn't start
# with a sh/bash shebang, so an HTML error page, redirect, or truncated
# response can never be handed to `bash` as if it were the real installer.
assert_shell_script() {
  local file="$1" label="${2:-script}"
  head -1 "$file" | grep -qE '^#!.*(sh|bash)' \
    || error "$label does not start with a shell shebang — possible download
corruption or an unexpected response (HTML error page, redirect, etc)."
}

# fetch_and_verify url dest label [expected_sha256] — downloads over HTTPS
# only (rejects protocol downgrade/redirect via curl --proto), retries
# transient network/5xx failures with backoff, rejects empty responses, and
# hard-fails on a SHA-256 mismatch when expected_sha256 is given. With no
# pinned hash available, warns and prints the actual hash so it can be
# reviewed and pinned.
fetch_and_verify() {
  local url="$1" dest="$2" label="$3" expected_sha256="${4:-}"
  [[ "$url" == https://* ]] || error "$label URL must use https://: $url"
  curl -fsSL --proto '=https' --proto-redir '=https' \
    --retry 3 --retry-delay 2 --retry-all-errors \
    "$url" -o "$dest" \
    || error "Failed to download $label from $url after retries"
  [[ -s "$dest" ]] || error "$label download is empty or missing: $url"
  local actual_sha256
  actual_sha256="$(sha256_of "$dest")"
  if [[ -n "$expected_sha256" ]]; then
    if [[ "${actual_sha256,,}" != "${expected_sha256,,}" ]]; then
      rm -f "$dest"
      error "$label failed SHA-256 verification.
  URL:      $url
  Expected: $expected_sha256
  Actual:   $actual_sha256
Refusing to use a download that does not match its pinned checksum."
    fi
    info "$label integrity verified (SHA-256: ${actual_sha256:0:16}…)"
  else
    warn "$label has no pinned checksum — downloaded SHA-256: $actual_sha256"
    warn "Pin this value (see scripts/lib/verify.sh call sites) once you've reviewed it."
  fi
}
