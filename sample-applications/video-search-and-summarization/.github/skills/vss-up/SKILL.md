---
name: vss-up
description: Deploy, dry-run, stop, or clean the Video Search and Summarization (VSS) stack in any mode using setup.sh. Routes by use case — summary only, search only, dual (two UIs), or unified (search over summaries) — validates the required shell env vars for the chosen mode first, runs the deploy, waits for health, and prints the UI/API URLs. Use when the user says "deploy vss", "start vss", "bring up summary/search/dual/unified", "stop vss", "clean vss data", or "why won't vss come up".
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vss deployment operational"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Up

Bring the VSS stack up (or down) with `setup.sh`. This is a **routing skill**:
one entry point, a routing table that picks the mode, and one
[`references/`](./references) file per mode with the exact env requirements and
URLs. Always **run the commands yourself** and relay output.

## Mode Routing

| User says | Mode flag | Reference |
|---|---|---|
| "summary" / "summarize videos" / "summary only" | `--summary` | [`references/summary.md`](./references/summary.md) |
| "search" / "search my videos" / "search only" | `--search` | [`references/search.md`](./references/search.md) |
| "both" / "dual" / "side by side" / "two UIs" | `--summary --search` (alias `--dual`) | [`references/dual.md`](./references/dual.md) |
| "unified" / "one UI" / "search over summaries" / "all" | `--summary-and-search` (alias `--unified`, `--all`) | [`references/unified.md`](./references/unified.md) |

If the user is ambiguous, ask which mode; do **not** default silently.

## Workflow

1. **Pick the mode** from the table and open its reference for the exact env vars.
2. **Set env vars** — `setup.sh` reads config from the shell and aborts on the
   first missing var. Config and secrets are split (repo policy: no credentials
   in committed files):
   - **Non-secret config** lives in committed [`vss.config.env`](./vss.config.env)
     (models, ports, tuning).
   - **Credentials** are generated at runtime into the **gitignored**
     `vss.secrets.env` by [`scripts/gen-secrets.sh`](./scripts/gen-secrets.sh)
     (strong random values, created once and reused so data volumes stay valid).

   Generate secrets once, then source both files in the same shell:
   ```bash
   ./.github/skills/vss-up/scripts/gen-secrets.sh        # makes vss.secrets.env if absent
   source .github/skills/vss-up/vss.config.env
   source .github/skills/vss-up/vss.secrets.env
   ```
   Then confirm nothing required for the chosen mode is still missing. Common to
   every deploy mode: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `POSTGRES_USER`,
   `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`. Mode-specific vars
   are listed in each reference. Check with e.g.:
   ```bash
   for v in MINIO_ROOT_USER MINIO_ROOT_PASSWORD POSTGRES_USER POSTGRES_PASSWORD \
            RABBITMQ_USER RABBITMQ_PASSWORD; do
     [ -n "${!v:-}" ] || echo "MISSING: $v"
   done
   ```
   To inject your own credentials (vault/CI) instead of random ones, export them
   before running `gen-secrets.sh` — it reuses any credential already set. See
   [`references/env-defaults.md`](./references/env-defaults.md) for per-mode
   requirements and GPU/gated-model caveats.
3. **Dry-run first when unsure** — append `config` to generate the resolved
   `.env`/compose without starting containers (e.g. `source setup.sh --summary config`).
   Review, then deploy for real.
4. **Deploy — run it yourself; do not hand the command to the user.** `setup.sh`
   must be **sourced** (it exports env and uses `return`), but it does **not** need
   the user's interactive shell: deploy uses `docker compose up -d` (detached), so
   the containers keep running after the subshell exits. Run the whole chain in one
   `bash -c 'source …'` invocation via the Bash tool.

   First **bring any prior stack down** so a stale/wrong-mode deployment can't
   collide with the new one (`--stop` is mode-agnostic and needs no env vars), then
   deploy:
   ```bash
   bash -c '
     source setup.sh --stop                                  # clear any running stack first
     ./.github/skills/vss-up/scripts/gen-secrets.sh           # secrets if absent
     source .github/skills/vss-up/vss.config.env
     source .github/skills/vss-up/vss.secrets.env
     source setup.sh --summary                                # the chosen mode
   '
   ```
   **Run this in the background** (`run_in_background: true`) or with a long
   timeout — the first deploy pulls large model-server images and `up -d` blocks
   until those pulls finish, which can exceed the Bash tool's default timeout.

   For a dry-run, swap the last line for `source setup.sh --summary config`.

   > **Only exception:** `--setenv` exists solely to leave env vars in the user's
   > *interactive* shell for later manual use — a subshell can't do that, so for
   > that verb only, give the user the `!`-prefixed command to run themselves.
5. **Wait for health**, then **print URLs** (see [`scripts/wait-health.sh`](./scripts/wait-health.sh)):
   ```bash
   ./.github/skills/vss-up/scripts/wait-health.sh "${HOST_IP:-localhost}" "${APP_HOST_PORT:-12345}"
   ```

## Lifecycle commands

Run all of these yourself via `bash -c 'source setup.sh …'` (the `--setenv` row
is the lone exception — see step 4). `--stop`/`--down`/`--clean-data` are
mode-agnostic and need no env vars.

| Goal | Command |
|---|---|
| Dry-run (env + compose only) | `source setup.sh <mode> config` |
| Set env vars only, no containers | `source setup.sh --setenv` (user's shell only) |
| Stop all containers | `source setup.sh --stop` (alias `--down`) |
| Stop **and** wipe user-data volumes | `source setup.sh --clean-data` |
| Full help | `source setup.sh --help` |

## Default ports & URLs

`HOST_IP` is auto-detected by `setup.sh`; `APP_HOST_PORT` defaults to `12345`.

| Surface | URL |
|---|---|
| UI (summary / search / unified) | `http://<HOST_IP>:<APP_HOST_PORT>/` |
| UI (dual mode) | `…/summary/` and `…/search/` |
| Pipeline Manager API + docs | `…/manager/docs`, health `…/manager/health` |
| Data Prep docs (search modes) | `http://<HOST_IP>:7890/docs` |
| Embedding server docs (search modes) | `http://<HOST_IP>:9777/docs` |

## Troubleshooting ("why won't vss come up")

1. `ERROR: <VAR> is not set` → missing shell env var; see step 2 and the mode
   reference.
2. `Invalid EMBEDDING_PROCESSING_MODE` → set `EMBEDDING_PROCESSING_MODE` to
   `api` or `sdk`.
3. Health never goes green → `docker compose ps` for crashed containers, then
   `docker compose logs <service>`. The heavy ones are model servers (`ovms`,
   `vlm-ov`/`vllm`, embedding).
4. Wrong/partial stack already running → `source setup.sh --stop` then redeploy.

For anything past these basics — model-server crashes, OVMS token/cache/GPU
errors, `ov-models` volume permission failures, search returning no results,
NPU/OpenGL issues — hand off to the [`vss-doctor`](../vss-doctor/SKILL.md) skill
and the canonical guide
[`docs/user-guide/troubleshooting.md`](../../../docs/user-guide/troubleshooting.md),
which has a symptom → fix section for each.
