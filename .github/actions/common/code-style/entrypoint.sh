#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -e

TARGET_DIR="${1:-.}"
REPORT_FILE="clang-format-report.txt"
echo "Checking code style in: $TARGET_DIR"

FILES=$(find "$TARGET_DIR" -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' \))

if [ -z "$FILES" ]; then
  echo "No C/C++ files found in $TARGET_DIR"
  exit 0
fi

echo "Checking files..." | tee -a "$REPORT_FILE"
FORMAT_DIFF=$(clang-format -output-replacements-xml $FILES | grep "<replacement " || true)

if [ -n "$FORMAT_DIFF" ]; then
  echo "Code style issues found. See $REPORT_FILE for details." | tee -a "$REPORT_FILE"
  for file in $FILES; do
    echo "---- $file ----" >> "$REPORT_FILE"
    clang-format "$file" | diff -u "$file" - >> "$REPORT_FILE" || true
  done
  exit 1
else
  echo "All files are properly formatted." | tee -a "$REPORT_FILE"
fi
