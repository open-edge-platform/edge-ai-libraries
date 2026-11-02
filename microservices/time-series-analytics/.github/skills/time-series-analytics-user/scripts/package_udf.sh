#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# package_udf.sh <udf_name> [<workdir>]
#
# Validates naming conventions and creates <udf_name>.tar for upload to
# POST /udfs/package.  Run from the use-case directory (the one containing
# udfs/, tick_scripts/, and optionally models/).
#
# The tar contains no wrapping top-level directory, as required by the
# microservice's package validator.  Internal layout:
#
#   udfs/<udf_name>.py
#   tick_scripts/<udf_name>.tick
#   models/                   (included only when the directory exists)
#
# Exit codes: 0 = success, 1 = missing required files.

set -euo pipefail

UDF_NAME="${1:?Usage: $(basename "$0") <udf_name> [<workdir>]}"
WORKDIR="${2:-.}"

cd "$WORKDIR"

ERRORS=0

if [[ ! -f "udfs/${UDF_NAME}.py" ]]; then
    echo "ERROR: udfs/${UDF_NAME}.py not found" >&2
    ERRORS=$((ERRORS + 1))
fi

if [[ ! -f "tick_scripts/${UDF_NAME}.tick" ]]; then
    echo "ERROR: tick_scripts/${UDF_NAME}.tick not found" >&2
    ERRORS=$((ERRORS + 1))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo "Packaging failed: fix the errors above before retrying." >&2
    exit 1
fi

# Warn about model files that won't be mounted by the microservice.
# The microservice only mounts models whose filename starts with udfs.name.
if [[ -d "models" ]]; then
    while IFS= read -r -d '' f; do
        base=$(basename "$f")
        if [[ "$base" != "${UDF_NAME}"* ]]; then
            echo "WARNING: models/${base} does not start with '${UDF_NAME}' — the microservice will not mount it" >&2
        fi
    done < <(find models -maxdepth 1 -type f -print0 2>/dev/null)
fi

# Build tar entries — no wrapping directory.
TAR_ENTRIES=("udfs/${UDF_NAME}.py" "tick_scripts/${UDF_NAME}.tick")
if [[ -d "models" ]]; then
    TAR_ENTRIES+=("models/")
fi

tar cf "${UDF_NAME}.tar" "${TAR_ENTRIES[@]}"
echo "Created ${UDF_NAME}.tar  [${TAR_ENTRIES[*]}]"
