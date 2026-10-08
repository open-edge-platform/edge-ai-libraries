#!/bin/sh
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -eu

library_dir=${1:-/usr/local/lib}

# Intel runtime wheels sometimes install separate, byte-identical copies of
# unversioned and versioned shared libraries. Keep every filename and its
# contents, but store identical large libraries as hard links in the image.
# Run this in the same Docker layer as pip install: removing files in a later
# layer would not reduce the size of the earlier layer.
cd "$library_dir"
# Choose one canonical for each checksum and mode/UID/GID combination so an
# incompatible first file cannot prevent later compatible files from linking.
find . -maxdepth 1 -type f -name '*.so*' -size +1M -exec sha256sum {} + |
    while IFS= read -r entry; do
        library=${entry#*  }
        checksum=${entry%% *}
        printf '%s:%s\t%s\n' "$checksum" "$(stat -c '%a:%u:%g' "$library")" "$library"
    done |
    sort |
    awk -F '\t' '$1 == key { print canonical "\t" $2; next } { key = $1; canonical = $2 }' |
    while IFS="$(printf '\t')" read -r original duplicate; do
        # A hard link shares permissions and ownership with the original.
        if [ "$(stat -c '%a:%u:%g' "$original")" = "$(stat -c '%a:%u:%g' "$duplicate")" ] &&
           [ "$(stat -c '%d:%i' "$original")" != "$(stat -c '%d:%i' "$duplicate")" ]; then
            ln -f "$original" "$duplicate"
        fi
    done