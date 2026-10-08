
<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Release Notes: Agent Quality Handler

## Version 2026.3.0

**TBD**

This release introduces **dynamic agent routing**, a **configuration-driven
agent registry**, and **custom-agent output persistence**, along with deployment
and documentation improvements.

**New**

- **Dynamic Agent Orchestration**: added severity-based routing and Deep Agents planning with dependency-safe execution ordering.
- **Configurable Agent Registry**: added support for registering custom agents, declaring dependencies, and creating prompt-driven specialists without custom orchestration code.
- **Custom-Agent Results**: added audit details, persisted output history, and additive `extra_agents` API results for registered custom agents.
- **Deployment Lifecycle Script**: added a centralized script for configuring, building, starting, stopping, and cleaning standard and development deployments.

**Improved**

- **Reliability and Compatibility**: preserved built-in result contracts while improving partial-failure handling, route normalization, and dependency-aware agent execution.
- **Dependencies and Documentation**: updated the LangGraph and supporting AI stack, expanded automated test coverage, and documented routing, registry integration, APIs, and deployment workflows.

**Fixed**

- **Deployment Cleanup**: corrected Compose path handling and ensured teardown includes profile-specific services such as mock storage.

---

## Version 2026.2.0

**Release Date:** September 9, 2026

**New**:

- Standalone Agent Quality Handler with Policy, Analysis, Evidence, and Ticketing graph stages.
- Direct REST API metrics on port `5002`.
- Rule-based fallback mode by default.
- Optional `llm` Compose profile providing OVMS and model download.
- Private Compose MQTT broker plus authenticated support for external MQTT.
- Required external storage API configured by `STORAGE_SERVICE_URL`.
- Event-driven Detection Service batch-complete integration over MQTT.
- Queryable per-agent JSON output history on the named Docker volume.
- Added configurable mounts for downstream-provided agent config and prompt assets.
- Startup validation for runtime configuration and required assets.
- Graph failures reported with status `error`, structured errors, and preserved partial results.

Detection Service, storage, a web UI, and Nginx are not included in this
standalone deployment.
