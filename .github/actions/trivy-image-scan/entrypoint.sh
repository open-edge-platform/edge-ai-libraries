#!/bin/bash
set -e

IMAGE="$1"
SEVERITY="${2:-LOW,MEDIUM,HIGH,CRITICAL}"
OUTPUT_FORMAT="${3:-table}"
OUTPUT_FILE="$4"

echo "🔍 Scanning image: $IMAGE"
echo "⚠️ Severity filter: $SEVERITY"
echo "📄 Output format: $OUTPUT_FORMAT"

CMD="trivy image --severity \"$SEVERITY\" --format \"$OUTPUT_FORMAT\""

if [ -n "$OUTPUT_FILE" ]; then
  echo "💾 Saving report to: $OUTPUT_FILE"
  CMD="$CMD --output \"$OUTPUT_FILE\""
fi

CMD="$CMD \"$IMAGE\""
bash -c "$CMD"
