<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# AGENTS.md — OEP SDK Manager

You are an AI assistant working on the OEP SDK Manager project. This document provides instructions, patterns, and boundaries for making changes to this codebase.

## Project Overview

OEP SDK Manager is a comprehensive development tool that streamlines discovering, installing, and managing multiple SDKs for Intel edge AI applications. It consists of two main parts:

1. **Documentation UI** (`docs/`) — A Sphinx-based documentation site with an embedded interactive SDK selector built with HTML, CSS, and JavaScript. Includes tutorial sections for each SDK.
2. **Installation Scripts** (`scripts/`) — Bash scripts that install each SDK by pulling Docker images and cloning source repositories from GitHub.

### SDKs

| SDK | Install Script | Tutorials | Description |
|:----|:---------------|:----------|:------------|
| Metro Vision AI SDK | `scripts/metro-vision-ai-sdk.sh` | `docs/user-guide/metro-vision-ai-sdk/` | DL Streamer, OpenVINO, Pipeline Server, Scenescape — visual AI inference & spatial analytics |
| Metro Gen AI SDK | `scripts/metro-gen-ai-sdk.sh` | `docs/user-guide/metro-gen-ai-sdk/` | Audio Analyzer, VLM serving, embedding, document ingestion |
| Metro Visual AI Demo Kit | `scripts/metro-visual-ai-demo-kit.sh` | `docs/user-guide/metro-visual-ai-demo-kit/` | DL Streamer Pipeline Server, Node-RED, Grafana, MQTT, MediaMTX |
| UAV Mission Compute SDK | `scripts/uav-mission-compute-sdk.sh` | `docs/user-guide/uav-mission-compute-sdk/` |  |

The Metro SDKs install Docker container images and clone `metro-ai-suite` plus their library dependencies.
The UAV SDK clones `federal-and-aerospace-ai-suite`.
Current source clones and the selector's `latest` installer commands use `main`.
The 2026.1 and 2026.2 selections retain the original `edge-ai-suites` release URLs and installer filenames.
The selector does not offer 2026.0.
Supported hosts are Ubuntu 24.04 LTS and Ubuntu 26.04 LTS; container image OS tags are independent of the host version.

## Repository Structure

```
tools/oep-sdk-manager/
├── docs/                              # Sphinx documentation source
│   ├── oep-sdk-manager-files/
│   │   ├── selector.html          # Interactive SDK selector UI
│   │   ├── style.css              # Selector styles
│   │   ├── config.js              # SDK options, versions, install commands
│   │   └── iframe-resizer.js      # Responsive iframe helper
│   └── user-guide/
│       ├── index.md                   # Landing page (embeds installer iframe)
│       ├── release-notes.md
│       ├── metro-vision-ai-sdk/       # Vision SDK tutorials (get-started + tutorials 1-6)
│       ├── metro-gen-ai-sdk/          # Gen AI SDK tutorials (get-started)
│       ├── metro-visual-ai-demo-kit/        # Demo Kit tutorials (get-started + tutorials 1-3)
│       └── uav-mission-compute-sdk/  # UAV Mission Compute SDK tutorials (get-started)
├── scripts/
│   ├── metro-vision-ai-sdk.sh         # Vision SDK installer
│   ├── metro-gen-ai-sdk.sh            # Gen AI SDK installer
│   ├── metro-visual-ai-demo-kit.sh          # Metro Visual AI Demo Kit installer
│   └── uav-mission-compute-sdk.sh   # UAV Mission Compute SDK installer
├── .gitignore
├── README.md
└── AGENTS.md                          # This file
```

> [!NOTE]
> Files such as `Makefile`, `requirements.txt`, `VERSION`, `dict.txt`, `docconf/`, `docs/conf.py`, and `docs/substitutions.txt` are generated/managed by the CI pipeline and listed in `.gitignore`. They are not tracked in this repo.

## Tech Stack

- **Documentation**: Sphinx 8.2, pydata-sphinx-theme, MyST Markdown
- **Installer UI**: Vanilla HTML/CSS/JS (embedded via iframe in Sphinx output)
- **Install Scripts**: Bash (strict mode: `set -euo pipefail`)
- **Docker Images**: Each SDK defines its images array in the install script
- **Source Repos**: GitHub repos (edge-ai-libraries, metro-ai-suite) cloned from `main`
- **Source Branch**: `main` — Docker images are pinned to the latest available stable tags where possible
- **Linting**: ShellCheck, markdownlint, doc8, pylint, black, yamllint, reuse (license), Trivy
- **Build System**: GNU Make with Python virtualenv (provided by CI; `Makefile` and `requirements.txt` are gitignored)

## Core Commands

> [!NOTE]
> The `Makefile`, `requirements.txt`, and Sphinx config files are provided by CI and are gitignored.
> Build and lint commands (`make build`, `make lint`, etc.) are only available in the CI pipeline.
> Locally, you can run the install scripts and lint with standalone tools as shown below.

### Running Install Scripts

```bash
# Install a specific SDK
bash scripts/metro-vision-ai-sdk.sh
bash scripts/metro-gen-ai-sdk.sh
bash scripts/metro-visual-ai-demo-kit.sh

# Skip specific steps
bash scripts/metro-vision-ai-sdk.sh --skip-system-check --skip-docker --skip-images --skip-git-clone

# Show help for any script
bash scripts/metro-vision-ai-sdk.sh --help
```

### Local Linting (standalone tools)

```bash
# Lint shell scripts
shellcheck scripts/*.sh

# Lint Markdown files
markdownlint-cli2 "**/*.md"
```

## Code Style & Conventions

### Shell Scripts (`scripts/`)

- Shebang: `#!/bin/bash`
- Strict mode: `set -euo pipefail` at the top
- Quote all variable expansions: `"${var}"` not `$var`
- Use Google Shell Style Guide comment headers for functions
- Each script defines its `repositories=()` and `images=()` arrays at the top
- Support `--skip-system-check`, `--skip-docker`, `--skip-images`, `--skip-git-clone`, `--help` flags
- Color-coded output using `info()`, `warn()`, `err()`, `success()` helper functions

### Documentation (`docs/`)

- Write in MyST Markdown (`.md` files)
- Use ATX-style headings (`#`, `##`, `###`)
- One sentence per line for cleaner diffs
- Images go in `images/` subdirectory next to the tutorial
- Use `<!--hide_directive ... hide_directive-->` for Sphinx-only directives that should not render on GitHub

### Installer UI (`docs/oep-sdk-manager-files/`)

- Vanilla JS — no frameworks or bundlers
- All SDK options, versions, and install commands are defined in `config.js`
- `selector.html` is embedded as an iframe in the Sphinx docs landing page
- Keep the UI self-contained with no external HTTP fetches

### License Headers

All new source files must include:

```
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
```

Use the language-appropriate comment syntax (`#`, `//`, `/* */`).

## Adding a New SDK

1. Create the install script in `scripts/<sdk-name>.sh` following the existing pattern (define `repositories`, `images`, `NAME`).
2. Add a tutorial directory under `docs/user-guide/<sdk-name>/` with at minimum `get-started.md`.
3. Add the SDK entry to `docs/oep-sdk-manager-files/config.js` (options, components, and install commands).
4. Register the tutorial in the toctree in `docs/user-guide/index.md`.

## Security Rules

- **Never** commit secrets, tokens, passwords, or API keys.
- Docker image tags must reference specific versions, not `latest` or mutable tags.
- All dependencies must be compatible with Apache-2.0.
- Install scripts must validate inputs and fail safely on errors (`set -euo pipefail`).

## File Modification Rules

1. When updating Docker image versions in `scripts/`, also update the corresponding component lists in `docs/oep-sdk-manager-files/config.js`.
2. Do not add gitignored build/config files (`Makefile`, `requirements.txt`, `VERSION`, `docconf/`, `docs/conf.py`, etc.) — those are managed by CI.
3. Test install scripts with `--skip-images` for a dry-run validation.

## Test Suite

Tests live in `tests/` and validate the installer UI, shell scripts, and tutorial documentation.

### Run all tests

```bash
bash tests/run_tests.sh
```

### Run individual suites

```bash
bash tests/run_tests.sh scripts     # Shell script validation only
bash tests/run_tests.sh tutorials   # Tutorial markdown validation only
bash tests/run_tests.sh links       # UI link validation only (network required)
bash tests/run_tests.sh --offline   # All tests except network-dependent URL checks
```

### What each suite validates

- **`validate_scripts.sh`** — Bash syntax (`bash -n`), ShellCheck (if installed), shebang, `set -euo pipefail`, required arrays (`repositories`, `images`), `NAME` variable, no `:latest` Docker tags, CLI flags (`--skip-system-check`, `--skip-docker`, `--skip-images`, `--skip-git-clone`, `--help`), GitHub repo URL format.
- **`validate_tutorials.sh`** — Toctree entries in `index.md` resolve to files, each SDK has `get-started.md`, image references (`![](path)`) resolve to actual files, external URLs are reachable (skips `localhost` / placeholder URLs), H1 headings present, code fences balanced, tutorial numbering sequential.
- **`validate_ui_links.sh`** — Extracts all URLs from `config.js` and `selector.html`, verifies each is reachable via HTTP.
