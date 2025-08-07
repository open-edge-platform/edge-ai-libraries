#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
#!/bin/bash
set -e

SOURCE="${1:-/sources}"

SOURCE=$(realpath --relative-to=. "$SOURCE" | sed 's:/*$::')

mkdir -p /styled
mkdir -p "/styled/$(dirname "$SOURCE")"
cp -R "$SOURCE" "/styled/$SOURCE"

find "/styled/$SOURCE" \
  \( -name '*.c' \
  -o -name '*.cc' \
  -o -name '*.cpp' \
  -o -name '*.h' \
  -o -name '*.hh' \
  -o -name '*.hpp' \) \
  -exec sh -c "clang-format style=file -i '{}' 2>&1 | sed '/No such file or directory/d'" \;

output=$(diff -u --recursive "$SOURCE" "/styled/$SOURCE" || true)

if [[ -n "$output" ]]; then
    mkdir -p /output
    diff2html -F /output/diff.html -d word -s "side" -i stdin <<< "$output"
    sed -i '37d;38i<h1>Code style diff</h1>' /output/diff.html
    echo "❌ There are problems with code styles"
    exit 1
else
    echo "✅ Code styles are fine"
    exit 0
fi

