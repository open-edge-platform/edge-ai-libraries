<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Time Series Analytics Skills

Agent skills for the **Time Series Analytics** microservice.
Each skill teaches the agent how to work with this service through its real
interfaces — the REST API, UDF/TICKscript authoring, Docker Compose deploy, and
the source code — so common tasks run the same way every time.

These skills live under `.github/skills` as the canonical cross-harness
location. They are plain Markdown workflows and can be used by Copilot Chat,
Copilot CLI, Claude Code, Cursor, or local agent scripts.

A skill is a directory with a `SKILL.md` (YAML front matter + workflow) and
optional `references/` (deep docs loaded only when needed), `assets/` (templates
the agent copies), `scripts/` (helpers the agent runs), `example-prompts/`
(worked use-case scenarios), and `evals/` (behavior validation checks).

---

## What's in Here

Two **agent skills** that cover the two distinct ways people work with this
service:

- **User** — you want to build something *on top of* the deployed service:
  author a UDF, write a TICKscript, package and deploy it, feed it data, and
  wire up alerting. You don't touch the microservice's own Python source.
- **Dev** — you want to modify the microservice *itself*: add a REST route,
  change Kapacitor lifecycle behavior, run the test suite, or cut a release.

The skills are grounded in the **actual** source: real REST routes from
`src/main.py`, real UDF boilerplate from `udfs/`, real config shapes from
`config.json`/`schema.json`, real Kapacitor/TICKscript conventions, and real
build args from the `Dockerfile`.

---

## Catalog

| Skill | Persona | Use it when you want to… |
|---|---|---|
| [`time-series-analytics-user`](./time-series-analytics-user/SKILL.md) | Integrator | Build a new use case on the deployed service: author a UDF + TICKscript (threshold alert, rate-of-change / spike detection, rolling z-score, or pretrained-model inference per point or over a time window), package it as a tar, deploy via `POST /udfs/package` + `POST /config`, feed data through `POST /input`, and wire MQTT or OPC UA alerting. Ships `assets/udf_stream_template.py`, `assets/tick_template.tick`, and `scripts/package_udf.sh`. |
| [`time-series-analytics-dev`](./time-series-analytics-dev/SKILL.md) | Contributor | Develop the microservice itself: build/push the Docker image from source, run the unit and functional test suites, modify `src/main.py` (routes), `src/classifier_startup.py` (Kapacitor/UDF lifecycle), or `src/opcua_alerts.py`, and follow release/versioning conventions. |

Machine-readable catalog: [`skills-catalog.json`](./skills-catalog.json).

---

## Usage

Once installed, **describe your task in natural language** — the agent picks the
right skill from its `description`. You don't need to name skills explicitly.

| You say… | Skill that fires |
|---|---|
| "Build a UDF that flags pressure readings outside 80–150 bar" | `time-series-analytics-user` |
| "Detect sudden vibration spikes and send an MQTT alert" | `time-series-analytics-user` |
| "Deploy a pretrained IsolationForest model for anomaly detection" | `time-series-analytics-user` |
| "Wire up OPC UA alerting for a flagged sensor" | `time-series-analytics-user` |
| "Show me how to feed data to POST /input" | `time-series-analytics-user` |
| "Add a rolling z-score UDF for temperature monitoring" | `time-series-analytics-user` |
| "Run the time series analytics unit tests" | `time-series-analytics-dev` |
| "Add a GET /udfs endpoint to list deployed packages" | `time-series-analytics-dev` |
| "Build the time series analytics image from source" | `time-series-analytics-dev` |
| "Modify classifier_startup.py to change Kapacitor config" | `time-series-analytics-dev` |
| "Cut a release and update the CHANGELOG" | `time-series-analytics-dev` |
| "Debug why POST /config returns 200 but the UDF never processes data" | `time-series-analytics-dev` |

If the agent doesn't pick up the right skill, nudge it: *"use the
time-series-analytics-user skill"* or similar.

---

## Cross-Harness Discovery

- Copilot Chat instructions are at [`../copilot-instructions.md`](../copilot-instructions.md).
- Structured metadata for catalog tooling: [`skills-catalog.json`](./skills-catalog.json).
- All catalog paths are relative to the microservice root (`microservices/time-series-analytics/`).
- Keep skill bodies in one place: update each `SKILL.md`, then keep
  `skills-catalog.json`'s `description` and `triggers` in sync.
