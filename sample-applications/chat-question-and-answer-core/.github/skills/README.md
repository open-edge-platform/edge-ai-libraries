<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Skills

Agent skills for the Chat Question-and-Answer Core sample application.
Each skill teaches the agent how to use real project interfaces such as
Docker Compose, Helm, pytest, vitest, and documented REST APIs so routine
tasks are handled consistently.

These skills live under `.github/skills` as the canonical cross-harness
location. They are plain Markdown workflows and can be used by Codex,
Copilot CLI, Claude Code, or local agent scripts.

A skill is a directory with a `SKILL.md` (YAML front matter + workflow) and
optional `references/` (deep docs loaded only when needed), `scripts/`
(helpers the agent runs), and `evals/` (behavior checks).

---

## What's in Here

A curated set of agent skills for the ChatQnA sample application. Each skill
captures implementation-specific operational knowledge so AI coding agents can
perform build, deploy, API validation, and test workflows with fewer mistakes.

Skills are grounded in real project sources: `scripts/setup_env.sh`,
`docker/compose.yaml`, `chart/` values, backend and UI test commands, and
`docs/user-guide/api-reference.md`.

Every skill is self-contained with a `SKILL.md` entry point plus optional
`references/`, `scripts/`, `assets/`, and `evals/`.

---

## Catalog

A reference of all ChatQnA skills and intended usage:

| Skill | Persona | Use it when you want to... |
|---|---|---|
| [`chatqna-build`](./chatqna-build/SKILL.md) | Ops | Build backend/UI images from source using Docker or Compose build workflows, with registry and tag control. |
| [`chatqna-docker-deploy`](./chatqna-docker-deploy/SKILL.md) | Ops | Deploy ChatQnA with Docker Compose for OpenVINO CPU/GPU or Ollama, verify health, and stop/reset services. |
| [`chatqna-helm-deploy`](./chatqna-helm-deploy/SKILL.md) | Ops | Deploy ChatQnA to Kubernetes with Helm, map setup env values to overrides, verify readiness, and uninstall. |
| [`chatqna-run-unit-tests`](./chatqna-run-unit-tests/SKILL.md) | Contributor | Run backend and UI unit tests with runtime-aware backend options, optional coverage, and pass/fail evidence. |
| [`chatqna-api-smoke-test`](./chatqna-api-smoke-test/SKILL.md) | Integrator | Validate REST endpoints using curl-based smoke checks, including runtime-specific OpenVINO or Ollama APIs. |
| [`chatqna-troubleshoot`](./chatqna-troubleshoot/SKILL.md) | SRE | Troubleshoot startup, API, runtime, model, and UI failures for Docker Compose or Helm deployments using evidence-driven diagnostics. |

You generally do not invoke skills manually. The agent uses each skill's
description and triggers to select relevant guidance automatically.

---

## Installation

Skills are discovered from a skills directory scanned by your agent.

### Option A - Copilot CLI or Claude Code (per-user)

Symlink skills from this repo into your user skills directory:

```bash
# From repository root
CHATQNA_SKILLS="$(pwd)/sample-applications/chat-question-and-answer-core/.github/skills"

mkdir -p ~/.agents/skills
for d in "$CHATQNA_SKILLS"/chatqna-*/; do
	name="$(basename "$d")"
	ln -sfn "$d" ~/.agents/skills/"$name"
done

# Verify
ls -l ~/.agents/skills | grep chatqna-
```

If your setup scans `~/.copilot/skills/`, use that path instead.

### Option B - Project-local shared usage

Keep skills in the repo and configure your agent to scan:

```text
sample-applications/chat-question-and-answer-core/.github/skills
```

### Verify install

Start a fresh agent session and try prompts such as:

- "Deploy ChatQnA with Docker Compose OpenVINO GPU"
- "Run backend and UI unit tests"
- "Smoke test /v1/chatqna APIs"

---

## Usage

Use natural language requests; the agent selects matching skills.

Example intent mapping:

| You say... | Skill likely used |
|---|---|
| "Build ChatQnA images from source" | `chatqna-build` |
| "Deploy ChatQnA with Docker Compose and verify health" | `chatqna-docker-deploy` |
| "Deploy ChatQnA to Kubernetes with Helm values override" | `chatqna-helm-deploy` |
| "Run unit tests for backend openvino runtime" | `chatqna-run-unit-tests` |
| "Validate docs, openapi, and chat endpoint" | `chatqna-api-smoke-test` |
| "Troubleshoot ChatQnA health check or chat 500 errors" | `chatqna-troubleshoot` |

If needed, you can nudge explicitly: "use the chatqna-helm-deploy skill".

---

## Skill Structure

Typical layout:

```text
chatqna-<skill-name>/
├── SKILL.md
├── references/
├── scripts/
└── evals/
		├── evals.json
		└── trigger-evals.json
```

Progressive disclosure keeps context efficient: the agent first reads skill
name and description, loads the workflow body when relevant, then loads
references or scripts only when needed.

The optional `evals/` directory captures skill quality checks:

- `trigger-evals.json`: validates trigger matching behavior.
- `evals.json`: validates response quality and workflow expectations.

---

## Cross-Harness Discovery

- Canonical router for this sample:
	[`../copilot-instruction.md`](../copilot-instruction.md)
- Structured skill catalog:
	[`skill-catalog.json`](./skill-catalog.json)
- Root-level agents should start at
	[`../../AGENTS.md`](../../AGENTS.md).
- Claude agents should start at
	[`../../CLAUDE.md`](../../CLAUDE.md).
- Cursor agents should start at
	[`../../.cursor/rules/chatqna.mdc`](../../.cursor/rules/chatqna.mdc).

Keep each `SKILL.md` as source of truth for workflow details, and keep catalog entries (description, triggers, requires) synchronized when skill behavior changes.
