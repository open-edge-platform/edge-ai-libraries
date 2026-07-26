<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Skills

Agent skills for the **Video Search and Summarization (VSS)** sample application.
Each skill teaches the agent how to drive VSS through its real interfaces -
`setup.sh` deploy modes and the Pipeline Manager REST API - so common tasks run
the same way every time.

These skills live under `.github/skills` as the canonical cross-harness
location. They are plain Markdown workflows and can be used by Codex, Copilot
CLI, Claude Code, or local agent scripts.

A skill is a directory with a `SKILL.md` (YAML front matter + workflow) and
optional `references/` (deep docs loaded only when needed), `scripts/` (helpers
the agent runs), and `eval/` (behavior checks).

---

## What's in Here

A curated set of **agent skills** for the Video Search & Summarization (VSS) sample
application. Each skill packages the institutional knowledge needed to work with a specific
part of VSS - deploying it, calling its APIs, tuning the pipeline, onboarding models, extending
the services, and more - so that an AI coding agent (GitHub Copilot CLI, Claude Code, Cursor,
or any agent that supports the [Agent Skills format](https://anthropic.com/news/skills)
gets it right the first time.

Skills are grounded in the **actual** VSS source: real `setup.sh` flags, Docker Compose
overlays, the OpenAPI spec, OVMS model layout, NestJS module conventions, the FastMCP proxy,
and the search/embedding internals. They reference real file paths so guidance stays accurate.

Every skill is a self-contained directory with a `SKILL.md` (the entry point the agent reads)
plus optional `references/` (deep-dive docs loaded on demand), `scripts/` (runnable helpers),
and `assets/` (templates).

---

## Catalog

A comprehensive reference of all VSS skills and their use cases:

| Skill | Persona | Use it when you want to… |
|---|---|---|
| [`vss-deploy`](./vss-deploy/SKILL.md) | Ops | Deploy, dry-run, switch modes, inspect config, stop, or clean VSS in any mode (Summary, Search, Dual, Unified); choose OVMS vs vLLM and CPU vs GPU; manage Compose overlays/ports/credentials. Generates secrets, waits for health, prints URLs. Ships `scripts/gen-secrets.sh`, `scripts/wait-health.sh`, and `vss.config.env`. |
| [`vss-build`](./vss-build/SKILL.md) | Ops | Build or push the VSS Docker images from source; manage registry/tag and proxy controls. |
| [`vss-troubleshoot`](./vss-troubleshoot/SKILL.md) | Ops | Check health and which mode is live, then diagnose a broken deployment - containers, OVMS/vLLM load, DLStreamer, RabbitMQ/MinIO/Postgres/VDMS, "no summary", "search returns nothing". Probes Pipeline Manager health/feature endpoints; ships `scripts/triage.sh`. |
| [`vss-model-onboarding`](./vss-model-onboarding/SKILL.md) | Ops | Bring a new VLM/embedding model into OVMS (OpenVINO IR conversion + model-dir layout). Ships `scripts/prepare_ovms_model.py`. |
| [`vss-deploy-helm`](./vss-deploy-helm/SKILL.md) | Ops | Deploy VSS to Kubernetes via the Helm chart; map Compose/modes to `values.yaml`. |
| [`vss-summarize-video`](./vss-summarize-video/SKILL.md) | Integrator | Summarize a video through the Pipeline Manager; run/inspect the summary pipeline. Start, poll, and retrieve results. |
| [`vss-search-index`](./vss-search-index/SKILL.md) | Integrator | Upload, index, and natural-language search videos; generate embeddings and run queries with optional filtering. |
| [`vss-api-client`](./vss-api-client/SKILL.md) | Integrator | Call the REST/WebSocket APIs correctly (upload → process → progress → summary, and search queries). Ships `scripts/api_smoke.py`. |
| [`vss-e2e-smoke`](./vss-e2e-smoke/SKILL.md) | Integrator | One-command end-to-end verification per mode. Ships `scripts/e2e_summary.sh` and `e2e_search.sh`. |
| [`vss-mcp-integration`](./vss-mcp-integration/SKILL.md) | Integrator | Configure/extend the spec-driven FastMCP proxy that exposes VSS search to AI agents. |
| [`vss-pipeline-config`](./vss-pipeline-config/SKILL.md) | Contributor | Tune chunk duration, frames per chunk, multi-frame factor, sampling, audio transcript - with latency/quality trade-offs. |
| [`vss-dlstreamer-pipeline`](./vss-dlstreamer-pipeline/SKILL.md) | Contributor | Understand/modify the EVAM (DLStreamer Pipeline Server) ingestion pipelines and frame/chunk extraction. |
| [`vss-add-nest-module`](./vss-add-nest-module/SKILL.md) | Contributor | Scaffold a new pipeline-manager NestJS module the idiomatic way. Ships `assets/module-template/`. |
| [`vss-search-internals`](./vss-search-internals/SKILL.md) | Contributor | Work on embeddings & VDMS retrieval; understand frame-embedding (Search) vs summary-text-embedding (Unified). |
| [`vss-observability`](./vss-observability/SKILL.md) | Contributor | Enable OpenTelemetry, trace a video end-to-end, find latency bottlenecks. |

You don't invoke skills by hand in normal use - the agent reads each skill's `description` and
**automatically consults the relevant one** when your request matches. Installation just makes
them discoverable.

---

## Works with or without the VSS source (auto-bootstrap)

Every skill is self-contained and no longer assumes the VSS application source is
already sitting in your workspace. Each skill ships an identical
`scripts/vss-bootstrap.sh` and begins with an **Environment setup (run first)**
section that the agent executes before anything else. The bootstrap:

- **Detects an existing checkout** by walking up from the current directory and
  inspecting the enclosing git repo. If you are already anywhere inside a VSS
  checkout, it is reused and **nothing is cloned** - it just resolves and `cd`s
  into the app root.
- **Clones only when needed.** If no VSS source is found (e.g. the skill is
  installed standalone in a central skills directory with no application code
  present), it performs a shallow, **single-branch**, **sparse** checkout of just
  `sample-applications/video-search-and-summarization` from `main`, then `cd`s in.

This means the skills work identically whether they live inside the VSS repo or in
a centralized `~/.agents/skills/` install with no application code nearby.

Override the clone source with environment variables before running a skill:

| Variable | Default | Purpose |
|---|---|---|
| `VSS_REPO_URL` | `https://github.com/open-edge-platform/edge-ai-libraries.git` | Repo to clone from |
| `VSS_REPO_BRANCH` | `main` | Branch to fetch |
| `VSS_CLONE_DIR` | `${XDG_CACHE_HOME:-$HOME/.cache}/vss-src/edge-ai-libraries` | Where the sparse checkout lands |
| `VSS_FORCE_CLONE` | `0` | Set to `1` to skip detection and always clone |

You can also run the bootstrap directly to see the resolved app root:

```bash
APP_ROOT="$(bash .github/skills/vss-troubleshoot/scripts/vss-bootstrap.sh)" && cd "$APP_ROOT"
```

---

## Installation

Skills are discovered from a skills directory that your agent scans at startup. Pick the option
that matches your agent.

### Option A - GitHub Copilot CLI / Claude Code (per-user, recommended)

These agents load skills from `~/.agents/skills/`. The cleanest approach is to **symlink** each
skill from this repo so updates flow automatically (no copying, no drift):

```bash
# From the repo root, point this at the skills directory:
VSS_SKILLS="$(pwd)/sample-applications/video-search-and-summarization/.github/skills"

mkdir -p ~/.agents/skills
for d in "$VSS_SKILLS"/vss-*/; do
  name="$(basename "$d")"
  ln -sfn "$d" ~/.agents/skills/"$name"
done

# Verify
ls -l ~/.agents/skills | grep vss-
```

Prefer copies over symlinks (e.g., to pin a version)? Swap the `ln -sfn` line for
`cp -r "$d" ~/.agents/skills/"$name"`.

> Some setups also scan `~/.copilot/skills/`. If yours does, use that path instead of
> `~/.agents/skills/` in the commands above.

### Option C - Project-local (share with your team via the repo)

Keep the skills in the repo (where they already live) and point your agent's skills path at this
directory, if your agent supports a configurable skills path. That way everyone who clones the
repo gets the same skills. Check your agent's docs for the skills-directory setting and set it
to:

```
sample-applications/video-search-and-summarization/.github/skills
```

### Verifying the install

Start a fresh agent session and ask something a skill should catch, e.g.:

> "Deploy VSS in summary mode with GPU"  → should consult **vss-deploy**
> "VSS is up but no summary ever appears"  → should consult **vss-troubleshoot**

If the agent lists the skill among its available skills (or visibly uses it), you're set.

---

## Usage

Once installed, **just describe your task in natural language** - the agent decides when a skill
applies based on its `description`. You generally don't name skills explicitly. 

#### Some Examples:

> **Note:** These are most  examples and are not guaranteed or only way to invoke the skills.

| You say… | Skill that fires |
|---|---|
| "Deploy VSS in summary mode with GPU" | `vss-deploy` |
| "Spin up VSS in search mode" | `vss-deploy` |
| "Switch my VSS deployment from summary to search mode" | `vss-deploy` |
| "What compose files do I need for dual mode?" | `vss-deploy` |
| "Bring VSS down and clean the data" | `vss-deploy` |
| "OVMS won't start and the container keeps restarting" | `vss-troubleshoot` |
| "Is VSS up? What mode is running?" | `vss-troubleshoot` |
| "VSS is broken - debug it for me" | `vss-troubleshoot` |
| "I want to use a different VLM for summarization" | `vss-model-onboarding` |
| "Deploy VSS to our k8s cluster with vLLM" | `vss-deploy-helm` |
| "Summaries are too slow - what can I tune?" | `vss-pipeline-config` |
| "Add a new module to pipeline-manager for X" | `vss-add-nest-module` |
| "Change how frames are extracted in the ingestion pipeline" | `vss-dlstreamer-pipeline` |
| "How does unified-mode search differ from search mode?" | `vss-search-internals` |
| "Why is processing slow? Trace a video for me." | `vss-observability` |
| "Write a script to upload a video and poll for the summary" | `vss-api-client` |
| "Expose VSS search to my AI agent over MCP" | `vss-mcp-integration` |
| "Verify my fresh VSS install actually works" | `vss-e2e-smoke` |
| "Summarize this video for me" | `vss-summarize-video` |
| "Search my videos for X" | `vss-search-index` |
| "Build and push the VSS images" | `vss-build` |

If the agent doesn't pick up a skill when it should, you can nudge it: *"use the vss-deploy
skill"* or similar.

### Running the bundled scripts directly

Some skills ship scripts you (or the agent) can run standalone. They take the deployment's base
URL/ports as arguments or environment variables - check each script's header for usage:

```bash
# Cross-service triage of a running deployment
bash .github/skills/vss-troubleshoot/scripts/triage.sh

# End-to-end smoke tests (point at your running deployment)
bash .github/skills/vss-e2e-smoke/scripts/e2e_summary.sh
bash .github/skills/vss-e2e-smoke/scripts/e2e_search.sh

# Exercise the API happy-path
python .github/skills/vss-api-client/scripts/api_smoke.py

# Scaffold a new OVMS model directory
python .github/skills/vss-model-onboarding/scripts/prepare_ovms_model.py --help
```

---

## How a skill is structured

```
vss-troubleshoot/
├── SKILL.md                     # entry point: frontmatter (name, description) + instructions
├── references/
│   └── common-failures.md       # deep-dive docs the agent loads only when needed
├── scripts/
│   └── triage.sh                # runnable helper
└── evals/
    ├── evals.json               # skill output validation rules
    └── trigger-evals.json       # trigger-matching behavior checks
    
```

Progressive disclosure keeps things efficient: the agent always sees the lightweight
`name` + `description`, reads the `SKILL.md` body when the skill triggers, and only pulls in
`references/`/`scripts/` when the task actually calls for them.

The optional `evals/` directory contains structured validation rules that verify
the skill's outputs and triggers are correct. `evals.json` validates skill outputs and assertions,
while `trigger-evals.json` ensures skill triggers fire on the right user intents.
These checks run during skill testing and CI/CD pipelines to ensure the skill's guidance remains accurate as the codebase evolves.

---

## Cross-Harness Discovery

- All agents should start at
  [../copilot-instructions.md](../copilot-instructions.md).
- Root-level agents should use [../../AGENTS.md](../../AGENTS.md) as a router.
- Claude agents should use [../../CLAUDE.md](../../CLAUDE.md) as a router.
- Cursor agents should start at
  [../../.cursor/rules/vss.mdc](../../.cursor/rules/vss.mdc).
- Tools that prefer structured metadata should read
  [skill-catalog.json](./skill-catalog.json).
- All catalog paths are relative to the repository root.
- Keep the skill body in one place: update each `SKILL.md`, then keep the
  catalog description and triggers in sync.

---
