#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -e

IMAGE="$1"
SEVERITY="${2:-LOW,MEDIUM,HIGH,CRITICAL}"
OUTPUT_FORMAT="${3:-table}"
OUTPUT_FILE="$4"
FAIL_ON_FINDINGS="${5:-true}"

echo "🔍 Scanning image: $IMAGE"
echo "⚠️ Severity filter: $SEVERITY"
echo "📄 Output format: $OUTPUT_FORMAT"
echo "🚨 Fail on findings: $FAIL_ON_FINDINGS"

# Determine exit code parameter based on fail-on-findings
if [ "$FAIL_ON_FINDINGS" = "true" ]; then
  EXIT_CODE_PARAM="--exit-code 1"
else
  EXIT_CODE_PARAM="--exit-code 0"
fi

if [ -n "$OUTPUT_FILE" ]; then
  echo "💾 Saving report to: $OUTPUT_FILE"
  trivy image --severity "$SEVERITY" --format "$OUTPUT_FORMAT" --output "$OUTPUT_FILE" $EXIT_CODE_PARAM "$IMAGE"
else
  trivy image --severity "$SEVERITY" --format "$OUTPUT_FORMAT" $EXIT_CODE_PARAM "$IMAGE"
fi
