# Release Notes: Chat Q&A Core Sample Application

## Version 2026.3.0-rc1

**Release Date:** November 6, 2026

> **Note:** Helm Chart support will be deprecated in the next release. Limited validation has been performed on the Helm charts for this release.

**New:**

- Added NPU acceleration support for embedding, reranking, and LLM inference models running on the OpenVINO™ Runtime.
- Upgraded the Ollama runtime to v0.40.12.
- Updated GPU drivers.
- Consolidated OpenVINO Docker image releases, removing device-specific runtime images and standardizing image delivery across supported hardware platforms.
- Updated backend and frontend dependencies to address reported security vulnerabilities and enhance overall platform security and reliability.

## Version 2026.2.0

**Release Date:** September 9, 2026

**New:**

- Updated the Ollama runtime to version `0.30.10`.
- Upgraded OpenVINO packages to version `2026.2.1`.
- Transitioned dependency management from `Poetry` to `uv`.
- Updated backend and frontend dependency packages to remediate reported security vulnerabilities and improve overall platform security.

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- The HF token is made optional. Now, it is only required when the user downloads gated models.

**Upgrade Notes:**

- Upgraded the OLLAMA binary version.
- Dependency Upgrades: Upgraded application dependencies flagged by Dependabot for known vulnerabilities.

## Version 1.3.2

**Release Date:** WW09 2026

- Upgrade Ollama binary to latest version 0.17.0.
- Upgrade GPU drivers for PTL support.
- Dependency Upgrades. Upgraded application dependencies flagged by Dependabot for known vulnerabilities.

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <release-notes/release-notes-2025.md>

:::
hide_directive-->
