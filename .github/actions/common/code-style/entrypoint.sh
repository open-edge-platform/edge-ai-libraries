#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -e

TARGET_DIR="${1:-.}"
EXCLUDE_DIRS="${2:-}"
REPORT_FILE="clang-format-report.html

echo "Checking code style in: $TARGET_DIR"
if [ -n "$EXCLUDE_DIRS" ]; then
  echo "Excluding directories: $EXCLUDE_DIRS"
fi

PRUNE_EXPR=""
if [ -n "$EXCLUDE_DIRS" ]; then
  IFS=',' read -ra DIRS <<< "$EXCLUDE_DIRS"
  for d in "${DIRS[@]}"; do
    PRUNE_EXPR="$PRUNE_EXPR -path $TARGET_DIR/$d -prune -o"
  done
fi

eval "FILES=\$(find $TARGET_DIR $PRUNE_EXPR -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' \) -print)"

if [ -z "$FILES" ]; then
  echo "<p>No C/C++ files found in $TARGET_DIR</p>" >> "$REPORT_FILE"
  exit 0
fi

echo "Checking files..." | tee -a "$REPORT_FILE"
FORMAT_DIFF=$(clang-format -output-replacements-xml $FILES | grep "<replacement " || true)

if [ -n "$FORMAT_DIFF" ]; then
  echo "<h2>Code style issues found</h2>" >> "$REPORT_FILE"
  for file in $FILES; do
    echo "<h3>$file</h3>" >> "$REPORT_FILE"
    clang-format "$file" | diff -u "$file" - | diff2html -i stdin >> "$REPORT_FILE" || true
  done
  exit 1
else
  echo "<p>All files are properly formatted.</p>" >> "$REPORT_FILE"
fi
