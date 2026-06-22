#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Generate runtime credentials for a local VSS deployment.
#
# Per repo policy, credentials must not live in any committed file. This script
# writes strong random dev credentials into a GITIGNORED `vss.secrets.env` next
# to vss.config.env, which you then `source` before setup.sh.
#
# Properties:
#   - Idempotent: if vss.secrets.env already exists it is left untouched, so the
#     credentials stay stable across restarts (changing them after the first
#     deploy would invalidate existing Postgres/MinIO/RabbitMQ data volumes).
#   - Honors pre-set shell vars: any credential already exported is reused
#     instead of being randomized, so you can inject vault/CI secrets.
#   - File is created with 0600 perms and never committed.
#
# Usage:
#   ./.github/skills/vss-up/scripts/gen-secrets.sh            # create if absent
#   ./.github/skills/vss-up/scripts/gen-secrets.sh --force    # rotate (wipes file)
#   VSS_SECRETS_FILE=/path/to/secrets.env ./...gen-secrets.sh # custom location
#
# Then:
#   source .github/skills/vss-up/vss.config.env
#   source .github/skills/vss-up/vss.secrets.env
#   source setup.sh --summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="${VSS_SECRETS_FILE:-${SCRIPT_DIR}/../vss.secrets.env}"

if [ "${1:-}" = "--force" ]; then
  rm -f "$SECRETS_FILE"
elif [ -f "$SECRETS_FILE" ]; then
  echo "Secrets already present, reusing: $SECRETS_FILE"
  echo "(use --force to rotate — note this invalidates existing data volumes)"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required to generate credentials." >&2
  exit 1
fi

rand() { openssl rand -hex 24; }

umask 077
cat > "$SECRETS_FILE" <<EOF
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# AUTO-GENERATED local VSS credentials — DO NOT COMMIT (this file is gitignored).
# Regenerate with scripts/gen-secrets.sh --force (invalidates existing volumes).
export MINIO_ROOT_USER="${MINIO_ROOT_USER:-vss_minio}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-$(rand)}"
export POSTGRES_USER="${POSTGRES_USER:-vss_pg}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(rand)}"
export RABBITMQ_USER="${RABBITMQ_USER:-vss_rmq}"
export RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(rand)}"
export MQTT_USER="${MQTT_USER:-vss_mqtt}"
export MQTT_PASSWORD="${MQTT_PASSWORD:-$(rand)}"
EOF

chmod 600 "$SECRETS_FILE"
echo "Generated $SECRETS_FILE (gitignored, mode 600)."
echo "Next: source vss.config.env, source vss.secrets.env, then setup.sh <mode>."
