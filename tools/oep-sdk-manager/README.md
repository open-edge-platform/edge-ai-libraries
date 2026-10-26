<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# OEP SDK Manager

OEP SDK Manager is maintained in `edge-ai-libraries/tools/oep-sdk-manager/`.

## Validation

From this directory, run:

```bash
bash tests/run_tests.sh --offline
bash tests/run_tests.sh links
```

With Node.js 18 or later, run the selector and iframe regression tests:

```bash
node --test tests/selector.test.js
```

The offline suite checks installer scripts and tutorial files without network
access. Install ShellCheck to include shell linting; CI requires it.
The link suite checks the selector's external URLs and requires network access.
The offline suite tests installer OS checks and repository configuration in isolation;
it does not install packages, pull images, clone repositories, or launch workloads.

## Supported SDKs and hosts

The current installers support **Ubuntu 24.04 LTS and Ubuntu 26.04 LTS** hosts.
Ubuntu 22.04 is no longer supported, including when `--skip-system-check` skips hardware checks.
Pinned container image versions and their base operating systems are unchanged.

| SDK | Installer | Suite repository |
| --- | --- | --- |
| Metro Gen AI SDK | [metro-gen-ai-sdk.sh](scripts/metro-gen-ai-sdk.sh) | [Metro AI Suite](https://github.com/open-edge-platform/metro-ai-suite) |
| Metro Vision AI SDK | [metro-vision-ai-sdk.sh](scripts/metro-vision-ai-sdk.sh) | [Metro AI Suite](https://github.com/open-edge-platform/metro-ai-suite) |
| Metro Visual AI Demo Kit | [metro-visual-ai-demo-kit.sh](scripts/metro-visual-ai-demo-kit.sh) | [Metro AI Suite](https://github.com/open-edge-platform/metro-ai-suite) |
| UAV Mission Compute SDK | [uav-mission-compute-sdk.sh](scripts/uav-mission-compute-sdk.sh) | [Federal and Aerospace AI Suite](https://github.com/open-edge-platform/federal-and-aerospace-ai-suite) |

The `latest` selection downloads the renamed installers from the `main` branch of
`edge-ai-libraries/tools/oep-sdk-manager/scripts/`.
The 2026.1 and 2026.2 selections use the original installer filenames in
`edge-ai-suites/metro-ai-suite/metro-sdk-manager/scripts/` on
`release-2026.1.0` and `release-2026.2.0`, respectively.
Those historical installers retain their original platform and repository behavior.
Version 2026.0 is no longer offered.
Current installers clone source repositories from `main`.
Existing selector SDK identifiers are retained so bookmarked selections continue to work.

The Metro suite is cloned into `~/oep/metro-ai-suite`.
The UAV suite is cloned into `~/oep/federal-and-aerospace-ai-suite`, and startup
runs from its `uav-mission-compute-sdk` subdirectory.
Existing checkouts under the previous suite repository name are not migrated or removed.

## Overview

The selector shares its bundled stylesheet and UI styling with the
[OEP CLI Installer](../../frameworks/oep-installer-cli/docs/oep-cli-installer-files/).
It uses transparent backgrounds, bordered choices with consistent spacing,
section dividers, and a GitHub source link.
The iframe resizer follows content changes and window resizing so the embedded
selector can grow and shrink without accumulating blank space.
SDK configuration remains embedded in the JavaScript; CLI-specific profiles,
module lifecycle commands, and remote configuration loading are not used.


The SDK Manager is a comprehensive development tool that streamlines the process of discovering, installing, and managing multiple software development kits for edge AI applications. Designed for developers working with Intel's edge computing ecosystem, it eliminates the complexity of manually configuring SDK combinations by providing automated dependency resolution, version compatibility checking, and integrated toolchain setup. The tool supports interactive wizard-guided selection for developers to download and install the SDK directly into their development environment.

Built with developer productivity in mind, the SDK Manager handles cross-platform builds, maintains isolated development environments, and provides real-time compatibility validation across different SDK versions. It includes extensive documentation with code samples, API references, and troubleshooting guides. Whether you're prototyping edge AI solutions or deploying production applications, the SDK Manager ensures consistent, reproducible development environments across your team and deployment targets.
