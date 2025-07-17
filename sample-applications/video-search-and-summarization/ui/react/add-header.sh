#!/bin/bash

# Usage: ./add-header.sh "src/**/*.js"
# Example: ./add-header.sh "src/**/*.js"

pattern="$1"
header="// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0"

# Use 'shopt -s globstar' to enable ** pattern in bash 4+
shopt -s globstar nullglob

# Expand files matching the pattern
files=( $pattern )

if [ ${#files[@]} -eq 0 ]; then
  echo "No files found matching pattern: $pattern"
  exit 1
fi

for file in "${files[@]}"; do
  # Check if file already has the header
  if head -n 1 "$file" | grep -qF "$header"; then
    echo "Header already present in $file, skipping..."
    continue
  fi

  # Create a temp file with header + original content
  {
    echo "$header"
    cat "$file"
  } > "$file.tmp" && mv "$file.tmp" "$file"

  echo "Header added to $file"
done