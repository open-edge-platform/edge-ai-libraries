<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Skills

Agent skills for the **Video Search and Summarization (VSS)** sample application.
Each skill teaches the agent how to drive VSS through its real interfaces —
`setup.sh` deploy modes and the Pipeline Manager REST API — so common tasks run
the same way every time.

These skills live under `.github/skills` as the canonical cross-harness
location. They are plain Markdown workflows and can be used by Codex, Copilot
CLI, Claude Code, or local agent scripts.

A skill is a directory with a `SKILL.md` (YAML front matter + workflow) and
optional `references/` (deep docs loaded only when needed), `scripts/` (helpers
the agent runs), and `eval/` (behaviour checks).

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

## Catalog

| Skill | Use it when the user wants to… | Backed by |
|---|---|---|
| [`vss-up`](./vss-up/SKILL.md) | deploy / stop / dry-run VSS in any mode | `setup.sh` modes + `vss-up/vss.config.env` (+ generated `vss.secrets.env`) |
| [`vss-doctor`](./vss-doctor/SKILL.md) | check health, see which mode is live, debug a broken stack | `/manager/health`, `app/features`, `docker compose` |
| [`vss-summarize`](./vss-summarize/SKILL.md) | summarize a video, run/inspect the summary pipeline | `POST/GET /manager/summary` |
| [`vss-search`](./vss-search/SKILL.md) | upload, index, and natural-language search videos | `/manager/videos`, `/manager/search/query` |
| [`vss-build`](./vss-build/SKILL.md) | build / push the VSS docker images from source | `build.sh` (true source) |

## Conventions

- **Run commands yourself** and relay results; don't ask the user to run them.
- **Probe before acting.** Hit `GET /manager/health` before any API workflow; if
  it fails, route to `vss-up`.
- Endpoints assume the nginx prefix `/manager/…` for the Pipeline Manager.
- Run repo-local commands from the repository root unless a skill says
  otherwise.
