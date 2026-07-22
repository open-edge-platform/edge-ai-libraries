---
name: vss-deploy
description: Deploy, dry-run, switch, inspect, stop, or clean the Video Search & Summarization (VSS) sample app using its real setup.sh modes, Docker Compose overlays, profiles, services, ports, and environment variables. Generates runtime credentials, deploys the chosen mode (summary / search / dual / unified), waits for health, and prints UI/API URLs. Use when users say "deploy vss", "spin up VSS", "run summary mode", "switch to search", "use GPU/vLLM", "which compose files do I need", "stop vss", "clean vss data", or ask deployment questions for sample-applications/video-search-and-summarization.
license: Apache-2.0
metadata:
  version: "2.0.0"
  tags: "vss deployment operational"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Deploy

Deploy, switch, inspect, and tear down VSS with `setup.sh`. Use this skill only
for `sample-applications/video-search-and-summarization`. Ground every answer in
the repository files - especially `setup.sh` and `docker/compose.*.yaml` - and do
not invent flags, services, ports, or variables. **Run the commands yourself and
relay the output;** do not hand the deploy command to the user (the lone
exception is `--setenv`, see below).

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-deploy. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-deploy"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## Mode routing

| User says | Mode flag | UI URL |
|---|---|---|
| "summary" / "summarize videos" / "summary only" | `--summary` | `http://<host-ip>:12345/` |
| "search" / "search my videos" / "search only" | `--search` | `http://<host-ip>:12345/` |
| "both" / "dual" / "side by side" / "two UIs" | `--summary --search` (alias `--dual`) | `…/summary/` and `…/search/` |
| "unified" / "one UI" / "search over summaries" / "all" | `--summary-and-search` (alias `--unified`, `--all`) | `http://<host-ip>:12345/` |

If the user is ambiguous, ask which mode; do **not** default silently.

## Quick deployment flow

1. Work from the app root:

   ```bash
   cd sample-applications/video-search-and-summarization
   ```

2. **Provide config + credentials.** `setup.sh` reads everything from the shell
   environment and aborts on the first missing required var. The repository now
   provides `.env.example` as a general application template, but this skill
   keeps config and generated secrets split so credentials never enter a
   committed file:
   - **Non-secret config** - models, ports, tuning - lives in committed
     [`vss.config.env`](./vss.config.env).
   - **Credentials** are generated at runtime into the **gitignored**
     `vss.secrets.env` by [`scripts/gen-secrets.sh`](./scripts/gen-secrets.sh)
     (strong random values, created once and reused so data volumes stay valid).

   Generate secrets once, then source both files in the same shell:

   ```bash
   ./.github/skills/vss-deploy/scripts/gen-secrets.sh     # makes vss.secrets.env if absent
   source .github/skills/vss-deploy/vss.config.env
   source .github/skills/vss-deploy/vss.secrets.env
   ```

   Common to every mode: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`.
   Mode-specific model vars (`VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`,
   `OD_MODEL_NAME` for summary; `MULTIMODAL_EMBEDDING_MODEL` for search/dual;
   `TEXT_EMBEDDING_MODEL` for unified) ship with defaults in `vss.config.env` -
   see [`references/env-vars.md`](./references/env-vars.md) for the full table.
   To inject your own credentials (vault/CI) instead of random ones, export them
   before running `gen-secrets.sh` - it reuses any credential already set.

3. **Dry-run first when unsure** - append `config` to render the resolved
   `.env`/compose without starting containers, then review before the real deploy:

   ```bash
   source setup.sh --summary config     # or --search / --summary --search / --summary-and-search
   ```

4. **Deploy - run it yourself.** `setup.sh` must be **sourced** (it uses `return`
   and exports env while building the Compose command), but it does not need the
   user's interactive shell: deploy uses `docker compose up -d` (detached), so
   containers keep running after the subshell exits. First bring any prior stack
   down so a stale/wrong-mode deployment can't collide, then deploy - run the whole
   chain in one `bash -c` invocation:

   ```bash
   bash -c '
     source setup.sh --stop                                  # clear any running stack first
     ./.github/skills/vss-deploy/scripts/gen-secrets.sh       # secrets if absent
     source .github/skills/vss-deploy/vss.config.env
     source .github/skills/vss-deploy/vss.secrets.env
     source setup.sh --summary                                # the chosen mode
   '
   ```

   **Run this in the background** (`run_in_background: true`) or with a long
   timeout. Before Compose starts, `setup.sh` launches a transient
   `vss-model-download` container on loopback port `8640` when the selected OD
   artifact or an OVMS VLM/split LLM artifact is missing. It submits REST jobs, waits up to
   `MODEL_DOWNLOAD_JOB_TIMEOUT` per job (default `5400` seconds), writes failed
   service logs to `ov_models/model-download-*.log`, removes the transient
   container, and only then runs `docker compose up -d`.

   > **Only exception:** `--setenv` exists solely to leave env vars in the user's
   > *interactive* shell for later manual use - a subshell can't do that, so for
   > that verb only, give the user the `!`-prefixed command to run themselves.

5. **Wait for health**, then **print URLs** (see
   [`scripts/wait-health.sh`](./scripts/wait-health.sh)):

   ```bash
   ./.github/skills/vss-deploy/scripts/wait-health.sh "${HOST_IP:-localhost}" "${APP_HOST_PORT:-12345}"
   ```

## Mode aliases and config-only inspection

`setup.sh` normalizes `--summary --search` and `--search --summary` to `--dual`;
`--summary-and-search`, `--search-and-summary`, and `--all` to `--unified`;
`config` to `--dual config`; `config --summary` to `--summary config`; and
`--down` to `--stop`. Use config mode to verify the resolved Compose without
starting containers:

```bash
source setup.sh --summary config
source setup.sh --search config
source setup.sh --summary --search config
source setup.sh --summary-and-search config
```

## Choose OVMS, vLLM, CPU, or GPU

Default summarization backend is OVMS (`ovms-service`, profile `ovms`) from
`docker/compose.summary.yaml`.

```bash
source setup.sh --summary                                                # OVMS CPU default
VLM_TARGET_DEVICE=GPU source setup.sh --summary                          # OVMS GPU for VLM
LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=<llm> source setup.sh --summary # OVMS GPU for LLM
ENABLE_VLLM=true source setup.sh --summary                               # vLLM CPU backend
ENABLE_VLLM_GPU=true source setup.sh --summary                           # experimental vLLM XPU/GPU backend
ENABLE_EMBEDDING_GPU=true source setup.sh --search                       # GPU for search embeddings
```

For vLLM, `setup.sh` adds `docker/compose.vllm.yaml`, starts `vllm-cpu-service`
(profile `vllm`) on host port `8200`, and uses `VLM_MODEL_NAME` for both
captioning and final summary. Experimental `ENABLE_VLLM_GPU=true` instead adds
`docker/compose.vllm.xpu.yaml`, selects profile `vllm-xpu`, and disables OVMS.
For OVMS GPU, `setup.sh` adds
`docker/compose.gpu_ovms.yaml` and switches `ovms-service` to
`openvino/model_server:2026.1-gpu`.

The skill's fresh `bash -c` deployment flow prevents derived OVMS storage names
from leaking between runs. If switching from OVMS to vLLM manually in the same
interactive shell, first run
`unset VLM_STORAGE_MODEL_NAME LLM_STORAGE_MODEL_NAME`; otherwise Compose can
reuse an OVMS storage alias that vLLM does not serve.

## Lifecycle: bring down or reset

Run these yourself via `bash -c 'source setup.sh …'`. `--stop`/`--down`/
`--clean-data` are mode-agnostic and need no env vars.

```bash
source setup.sh --stop       # stop/remove containers across all VSS overlays/profiles
source setup.sh --down       # alias for --stop
source setup.sh --clean-data # also removes the VSS application data volumes
source setup.sh --help       # full help
```

`--clean-data` removes `docker_minio_data`, `docker_pg_data`, `docker_vdms-db`,
`docker_audio_analyzer_data`, `docker_data-prep`, and `docker_collector_signals`.
It does not remove the host-backed `ov_models/` model cache.

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

1. `ERROR: <VAR> is not set` → missing shell env var; re-source `vss.config.env`
   + `vss.secrets.env` (step 2).
2. `Invalid EMBEDDING_PROCESSING_MODE` → set `EMBEDDING_PROCESSING_MODE` to `api`
   or `sdk`.
3. Health never goes green → `docker compose ps` for crashed containers, then
   `docker compose logs <service>`. The heavy ones are model servers (`ovms`,
   `vlm-ov`/`vllm`, embedding).
4. Wrong/partial stack already running → `source setup.sh --stop` then redeploy.
5. Setup fails before Compose starts → inspect the reported
   `ov_models/model-download-*.log`; if loopback port `8640` is occupied, set
   `MODEL_DOWNLOAD_HOST_PORT` to a free port and rerun.

For anything past these basics - model-server crashes, OVMS token/cache/GPU
errors, host model-cache or model-download permission failures, search returning no results,
NPU/OpenGL issues - hand off to the
[`vss-troubleshoot`](../vss-troubleshoot/SKILL.md) skill and the canonical guide
[`docs/user-guide/troubleshooting.md`](../../../docs/user-guide/troubleshooting.md).

## References

- Exact mode-to-overlay/profile/service/URL mapping:
  [`references/modes-and-overlays.md`](./references/modes-and-overlays.md).
- Required and optional environment variables:
  [`references/env-vars.md`](./references/env-vars.md).
