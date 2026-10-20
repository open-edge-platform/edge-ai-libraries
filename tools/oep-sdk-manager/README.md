# OEP SDK Manager

OEP SDK Manager is maintained in `edge-ai-libraries/tools/oep-sdk-manager/`.
It was previously located in `metro-ai-suite/metro-sdk-manager/`.

## Validation

From this directory, run:

```bash
bash tests/run_tests.sh --offline
bash tests/run_tests.sh links
```

The offline suite checks installer scripts and tutorial files without network
access. Install ShellCheck to include shell linting; CI requires it.
The link suite checks the selector's external URLs and requires network access.
Installers are not executed by either suite.

Current download links use `edge-ai-libraries/tools/oep-sdk-manager/scripts/`.
Release-specific downloads stay pinned to their original release branches.

## Overview


The SDK Manager is a comprehensive development tool that streamlines the process of discovering, installing, and managing multiple software development kits for edge AI applications. Designed for developers working with Intel's edge computing ecosystem, it eliminates the complexity of manually configuring SDK combinations by providing automated dependency resolution, version compatibility checking, and integrated toolchain setup. The tool supports interactive wizard-guided selection for developers to download and install the SDK directly into their development environment.

Built with developer productivity in mind, the SDK Manager handles cross-platform builds, maintains isolated development environments, and provides real-time compatibility validation across different SDK versions. It includes extensive documentation with code samples, API references, and troubleshooting guides. Whether you're prototyping edge AI solutions or deploying production applications, the SDK Manager ensures consistent, reproducible development environments across your team and deployment targets.
