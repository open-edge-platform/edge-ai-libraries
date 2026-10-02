#!/bin/sh
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -eu

library_dir=${1:-/usr/local/lib}

# Intel's Python wheels include static symbols and debug sections that are
# unnecessary for dynamic loading. Only touch wheel-owned shared libraries:
# modifying Debian GPU drivers or the Python base here would copy those files
# from earlier Docker layers instead of reducing the image size.
find "$library_dir" -maxdepth 1 -type f -name '*.so*' ! -name 'libpython*' -size +1M |
    while IFS= read -r library; do
        if ! dpkg-query -S "$library" >/dev/null 2>&1; then
            strip --strip-unneeded "$library"
        fi
    done