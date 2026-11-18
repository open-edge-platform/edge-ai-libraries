#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Build liboptical-flow-sdk0 / -dev / python3-optical-flow-sdk debs (CPU+OpenCL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x debian/rules
dpkg-buildpackage -us -uc -b
ls -la ../liboptical-flow-sdk*.deb ../python3-optical-flow-sdk*.deb 2>/dev/null || \
  ls -la ../*optical-flow-sdk*.deb
echo "Install: sudo apt install ./liboptical-flow-sdk0_*.deb ./liboptical-flow-sdk-dev_*.deb ./python3-optical-flow-sdk_*.deb"
