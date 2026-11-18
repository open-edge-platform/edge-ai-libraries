#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Generate runtime credentials for a local VSS deployment.
#
# Per repo policy, credentials must not live in any committed file. This script
# writes strong random dev credentials outside the checkout, under the user's
# config directory by default, which you then `source` before setup.sh.
#
# Properties:
#   - Idempotent: if the credentials file already exists it is left untouched,
#     so the credentials stay stable across restarts (changing them after the first
#     deploy would invalidate existing Postgres/MinIO/RabbitMQ data volumes).
#   - Honors pre-set shell vars: any credential already exported is reused
#     instead of being randomized, so you can inject vault/CI secrets.
#   - File is created with 0600 perms and never committed.
#
# Usage:
#   ./.github/skills/vss-deploy/scripts/gen-secrets.sh            # create if absent
#   ./.github/skills/vss-deploy/scripts/gen-secrets.sh --force    # rotate atomically
#   VSS_CREDENTIALS_FILE=/path/to/credentials ./...gen-secrets.sh  # custom location
#
# Then:
#   source .github/skills/vss-deploy/vss.config
#   source "${VSS_CREDENTIALS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/vss/vss.credentials}"
#   source setup.sh --summary

set -euo pipefail

CONFIG_BASE="${XDG_CONFIG_HOME:-${HOME:?HOME is required}/.config}"
DEFAULT_CREDENTIALS_FILE="$CONFIG_BASE/vss/vss.credentials"
CREDENTIALS_FILE="${VSS_CREDENTIALS_FILE:-${VSS_SECRETS_FILE:-$DEFAULT_CREDENTIALS_FILE}}"
CREDENTIALS_DIR="$(dirname "$CREDENTIALS_FILE")"
CREDENTIALS_NAME="$(basename "$CREDENTIALS_FILE")"
FORCE=0
TEMP_FILE=""

case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  *)
    echo "ERROR: unsupported argument: $1" >&2
    echo "Usage: $0 [--force]" >&2
    exit 2
    ;;
esac

if [ "$#" -gt 1 ]; then
  echo "ERROR: expected at most one argument." >&2
  echo "Usage: $0 [--force]" >&2
  exit 2
fi

if [ "$CREDENTIALS_FILE" = "$DEFAULT_CREDENTIALS_FILE" ]; then
  mkdir -p "$CREDENTIALS_DIR"
elif [ ! -d "$CREDENTIALS_DIR" ]; then
  echo "ERROR: credentials directory does not exist: $CREDENTIALS_DIR" >&2
  exit 1
fi

if [ -L "$CREDENTIALS_FILE" ]; then
  echo "ERROR: refusing to write credentials through a symbolic link: $CREDENTIALS_FILE" >&2
  exit 1
fi

if [ -e "$CREDENTIALS_FILE" ] && [ ! -f "$CREDENTIALS_FILE" ]; then
  echo "ERROR: credentials destination is not a regular file: $CREDENTIALS_FILE" >&2
  exit 1
fi

if [ "$FORCE" -eq 0 ] && [ -f "$CREDENTIALS_FILE" ]; then
  echo "Credentials already present, reusing: $CREDENTIALS_FILE"
  echo "(use --force to rotate - note this invalidates existing data volumes)"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required to generate credentials." >&2
  exit 1
fi

rand() { openssl rand -hex 24; }

cleanup() {
  if [ -n "$TEMP_FILE" ] && { [ -e "$TEMP_FILE" ] || [ -L "$TEMP_FILE" ]; }; then
    rm -f -- "$TEMP_FILE"
  fi
}

umask 077
TEMP_FILE="$(mktemp "$CREDENTIALS_DIR/.${CREDENTIALS_NAME}.tmp.XXXXXX")"
trap cleanup EXIT

{
  printf '%s\n' \
    '# SPDX-FileCopyrightText: (C) 2026 Intel Corporation' \
    '# SPDX-License-Identifier: Apache-2.0' \
    '#' \
    '# AUTO-GENERATED local VSS credentials - DO NOT COMMIT.' \
    '# Regenerate with scripts/gen-secrets.sh --force (invalidates existing volumes).'
  printf 'export MINIO_ROOT_USER=%q\n' "${MINIO_ROOT_USER:-vss_minio}"
  printf 'export MINIO_ROOT_PASSWORD=%q\n' "${MINIO_ROOT_PASSWORD:-$(rand)}"
  printf 'export POSTGRES_USER=%q\n' "${POSTGRES_USER:-vss_pg}"
  printf 'export POSTGRES_PASSWORD=%q\n' "${POSTGRES_PASSWORD:-$(rand)}"
  printf 'export RABBITMQ_USER=%q\n' "${RABBITMQ_USER:-vss_rmq}"
  printf 'export RABBITMQ_PASSWORD=%q\n' "${RABBITMQ_PASSWORD:-$(rand)}"
  printf 'export MQTT_USER=%q\n' "${MQTT_USER:-vss_mqtt}"
  printf 'export MQTT_PASSWORD=%q\n' "${MQTT_PASSWORD:-$(rand)}"
} > "$TEMP_FILE"

mv -T -f -- "$TEMP_FILE" "$CREDENTIALS_FILE"
TEMP_FILE=""
trap - EXIT

echo "Generated $CREDENTIALS_FILE (mode 600)."
echo "Next: source vss.config, source the generated credentials file, then setup.sh <mode>."
