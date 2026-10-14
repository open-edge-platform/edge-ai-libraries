<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Video Summary Accuracy Analyzer Skills

Agent skills for the Video Summary Accuracy Analyzer. Each skill teaches the
agent how to use the analyzer's real interfaces (Docker Compose deployment,
the nginx gateway, and the documented REST API) so evaluations are run and
reported consistently.

These skills live under `.github/skills` as the canonical cross-harness
location. They are plain Markdown workflows and can be used by Codex,
Copilot CLI, Claude Code, or local agent scripts.

A skill is a directory with a `SKILL.md` (YAML front matter + workflow) and
optional `references/` (deep docs loaded only when needed), `scripts/`
(helpers the agent runs), `evals/` (behavior checks), and `benchmark/`
(recorded with/without-skill results).

---

## Catalog

| Skill | Persona | Use it when you want to... |
|---|---|---|
| [`video-summary-accuracy`](./video-summary-accuracy/SKILL.md) | Evaluator | Score a generated video summary against a reference summary, get a KPI table, traffic-light quality overview, evidence-backed discrepancies, and a plain-language verdict. |

You generally do not invoke skills manually. The agent uses each skill's
description and triggers to select relevant guidance automatically.

---

## Installation

Skills are discovered from a skills directory scanned by your agent.

### Option A - Copilot CLI or Claude Code (per-user)

Symlink skills from this repo into your user skills directory:

```bash
# From repository root
VSA_SKILLS="$(pwd)/tools/video-summary-accuracy-analyzer/.github/skills"

mkdir -p ~/.agents/skills
for d in "$VSA_SKILLS"/*/; do
  name="$(basename "$d")"
  ln -sfn "$d" ~/.agents/skills/"$name"
done

# Verify
ls -l ~/.agents/skills | grep video-summary-accuracy
```

If your setup scans `~/.copilot/skills/`, use that path instead.

### Option B - Project-local shared usage

Open `tools/video-summary-accuracy-analyzer` as the workspace, or configure
your agent to scan:

```text
tools/video-summary-accuracy-analyzer/.github/skills
```

### Verify install

Start a fresh agent session and try prompts such as:

- "Evaluate the accuracy of the generated summary in compare.md"
- "Is this generated video summary faithful to the reference?"
- "Score summary_eval.md; accept only if contradiction ratio is at most 10%"

---

## Usage

Use natural language requests; the agent selects matching skills.

| You say... | Skill likely used |
|---|---|
| "Evaluate compare.md and give me a verdict" | `video-summary-accuracy` |
| "Check factual consistency and MENLI of my generated summary" | `video-summary-accuracy` |
| "Does the generated summary keep the reference's event order?" | `video-summary-accuracy` |

If needed, you can nudge explicitly: "use the video-summary-accuracy skill".

The input Markdown file must contain two non-empty sections in this order:

```markdown
## Reference
<ground-truth summary>

## Generated
<summary to evaluate>
```

See [`../../compare.md`](../../compare.md) for an example.

---

## Skill Structure

```text
video-summary-accuracy/
├── SKILL.md
├── scripts/
│   ├── vsa-bootstrap.sh     # resolve (or sparse-clone) the analyzer root
│   └── extract_kpis.py      # validate the /evaluate response and extract KPIs
├── evals/
│   ├── evals.json
│   └── trigger-evals.json
└── benchmark/
    └── benchmark.md
```

Progressive disclosure keeps context efficient: the agent first reads skill
name and description, loads the workflow body when relevant, then loads
scripts only when needed.

The `evals/` directory captures skill quality checks:

- `trigger-evals.json`: validates trigger matching behavior.
- `evals.json`: validates response quality and workflow expectations.

---

## Cross-Harness Discovery

- Structured skill catalog: [`skill-catalog.json`](./skill-catalog.json)
- Analyzer deployment guide:
  [`../../docs/user-guide/get-started.md`](../../docs/user-guide/get-started.md)

Keep each `SKILL.md` as the source of truth for workflow details, and keep
catalog entries (description, triggers, requires) synchronized when skill
behavior changes.
