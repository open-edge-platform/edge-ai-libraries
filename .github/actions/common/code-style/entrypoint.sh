#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
#!/bin/bash
set -e

TARGET_DIR="${1:-.}"
EXCLUDE_DIRS="${2:-}"
REPORT_FILE="clang-format-report.html"

echo "<html><body>" > "$REPORT_FILE"
echo "Checking code style in: $TARGET_DIR" | tee -a "$REPORT_FILE"
if [ -n "$EXCLUDE_DIRS" ]; then
  echo "Excluding directories: $EXCLUDE_DIRS" | tee -a "$REPORT_FILE"
fi

FIND_ARGS=("$TARGET_DIR")
if [ -n "$EXCLUDE_DIRS" ]; then
  IFS=',' read -ra DIRS <<< "$EXCLUDE_DIRS"
  for d in "${DIRS[@]}"; do
    FIND_ARGS+=(-path "$TARGET_DIR/$d" -prune -o)
  done
fi
FIND_ARGS+=(-type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' \) -print)

FILES=($(find "${FIND_ARGS[@]}"))

if [ ${#FILES[@]} -eq 0 ]; then
  echo "<p>No C/C++ files found.</p>" >> "$REPORT_FILE"
  echo "</body></html>" >> "$REPORT_FILE"
  exit 0
fi

ISSUES_FOUND=0

for file in "${FILES[@]}"; do
  CHANGES=$(clang-format -output-replacements-xml "$file" | grep "<replacement " || true)
  if [ -n "$CHANGES" ]; then
    ISSUES_FOUND=1
    echo "<h3>$file</h3>" >> "$REPORT_FILE"
    diff -u "$file" <(clang-format "$file") >> "$TEMP_DIFF"
  fi
done

if [ $ISSUES_FOUND -eq 1 ]; then
  diff2html -i file -s line -F "$REPORT_FILE" "$TEMP_DIFF"
else
  echo "<p>All files are properly formatted.</p>" >> "$REPORT_FILE"
fi

echo "</body></html>" >> "$REPORT_FILE"

if [ $ISSUES_FOUND -eq 1 ]; then
  echo "Code-style found issues"
  exit 1
fi

