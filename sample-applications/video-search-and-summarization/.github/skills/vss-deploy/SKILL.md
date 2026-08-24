---
name: vss-deploy
description: Deploys and manages VSS through setup.sh and its Docker Compose overlays. Use this skill for local lifecycle tasks such as configuration, startup, mode changes, inspection, shutdown, data cleanup, and health checks. It supports summary, search, dual, and unified modes with GPU and vLLM variants.
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

## Answer contract when the host is not reachable

The user may be planning ahead, or Docker / the VSS source may be unavailable
here. In that case **do not stall and do not invent output.** Answer with the
exact command sequence instead: the bootstrap step, the config/secrets step, the
`setup.sh` invocation with its flags, the health wait, and the resulting URLs -
plus which command the user must run themselves and why. State plainly that the
commands were not executed. Never end the answer by asking whether to run them.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It resolves the app root in this order and prints it
as the only line on stdout:

1. **Walk up from the current directory** looking for a VSS app root - a
   directory carrying all three markers `setup.sh`, `docker/`, and
   `pipeline-manager/`.
2. **Ask git for the enclosing repository** (`git rev-parse --show-toplevel`) and
   check whether it holds `sample-applications/video-search-and-summarization`,
   or is itself a VSS app root. This is what makes your own clone - or a fork -
   work unchanged.
3. **Reuse a checkout a previous bootstrap already placed** in
   `${XDG_CACHE_HOME:-$HOME/.cache}/vss-src/edge-ai-libraries`.

If any of those hit, that checkout is **reused and NO clone is performed**. Only
when all three miss does it clone - and then only a **shallow (`--depth 1`),
single-branch, sparse** checkout of just
`sample-applications/video-search-and-summarization` from `main`:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-deploy. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-deploy"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it. The bootstrap refuses
to overwrite an existing non-VSS clone destination.

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
   keeps config and generated credentials split so credentials never enter a
   committed file:
   - **Non-secret config** - models, ports, tuning - lives in committed
     [`vss.config`](./vss.config).
   - **Credentials** are generated at runtime outside the checkout, at
     `${XDG_CONFIG_HOME:-$HOME/.config}/vss/vss.credentials`, by
     [`scripts/gen-secrets.sh`](./scripts/gen-secrets.sh) (strong random values,
     created once and reused so data volumes stay valid).

   Generate credentials once, then source both files in the same shell:

   ```bash
   export VSS_CREDENTIALS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/vss/vss.credentials"
   ./.github/skills/vss-deploy/scripts/gen-secrets.sh     # creates it if absent
   source .github/skills/vss-deploy/vss.config
   source "$VSS_CREDENTIALS_FILE"
   ```

   Common to every mode: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`.
   Mode-specific model vars (`VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`,
   `OD_MODEL_NAME` for summary; `MULTIMODAL_EMBEDDING_MODEL` for search/dual;
   `TEXT_EMBEDDING_MODEL` for unified) ship with defaults in `vss.config` -
   see [`references/env-vars.md`](./references/env-vars.md) for the full table.
   To inject your own credentials (vault/CI) instead of random ones, export them
   before running `gen-secrets.sh` - it reuses any credential already set.

3. **Dry-run first when unsure** - append `config` to render the resolved
   Compose configuration without starting containers, then review before the real deploy:

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
     export VSS_CREDENTIALS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/vss/vss.credentials"
     ./.github/skills/vss-deploy/scripts/gen-secrets.sh       # creates it if absent
     source .github/skills/vss-deploy/vss.config
     source "$VSS_CREDENTIALS_FILE"
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
   > that verb only, give the user the `!`-prefixed command to run themselves:
   >
   > ```bash
   > APP_HOST_PORT=18080 source setup.sh --setenv      # port override optional
   > ```
   >
   > `--setenv` takes **no mode flag**. `setup.sh` rejects any two-argument form
   > other than `<mode> config` / `config <mode>`, so `--setenv --summary-and-search`
   > fails with "Invalid argument combination". It returns before the mode dispatch,
   > so it exports the mode-agnostic vars (credentials, `APP_HOST_PORT`, registry and
   > device settings) - not the mode-derived ones such as `VS_INDEX_NAME` or
   > `EMBEDDING_MODEL_NAME`. Export those by hand if the user needs full parity for
   > manual `docker compose` calls.

5. **Wait for health**, then **print URLs**. Keep the probe in the invoking
   shell so this skill does not ship an executable network helper:

   ```bash
   VSS_BASE="http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}"
   deadline=$(( $(date +%s) + 300 ))
   until curl -sf --max-time 5 "$VSS_BASE/manager/health" >/dev/null; do
     if [ "$(date +%s)" -ge "$deadline" ]; then
       echo "VSS health check timed out: $VSS_BASE/manager/health" >&2
       docker compose ps
       exit 1
     fi
     sleep 5
   done
   echo "UI: $VSS_BASE/"
   echo "Pipeline Manager: $VSS_BASE/manager/docs"
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

Run these yourself via `bash -c 'source setup.sh …'`. `--stop`, `--down`,
`--clean-data`, and config-only inspection (`<mode> config`) **skip the required
environment validation** entirely, so they are mode-agnostic and need no config
or credentials sourced first.

```bash
source setup.sh --stop       # stop/remove containers across all VSS overlays/profiles
source setup.sh --down       # alias for --stop
source setup.sh --clean-data # also removes the VSS application data volumes
source setup.sh --help       # full help
```

`--clean-data` removes the **user-data** volumes only: `docker_minio_data`,
`docker_pg_data`, `docker_vdms-db`, `docker_milvus-db`, `docker_milvus-etcd`,
`docker_audio_analyzer_data`, and `docker_data-prep` (volumes absent in the
current mode are skipped). The **model-cache** volumes -
`docker_dataprep-yolox-models`, `docker_ov-models`, `docker_vllm_model_cache` -
and the host-backed `ov_models/` directory are deliberately **preserved**, so a
`--clean-data` never forces a costly model re-download.

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

1. `ERROR: <VAR> is not set` → missing shell env var; re-source `vss.config`
   plus `$VSS_CREDENTIALS_FILE` (step 2).
2. `Invalid VECTORDB_BACKEND` → set `VECTORDB_BACKEND` to `vdms`
   or `milvus`.
3. Health never goes green → `docker compose ps` for crashed containers, then
   `docker compose logs <service>`. The heavy ones are model servers (`ovms`,
   `vlm-ov`/`vllm`, embedding).
4. Wrong/partial stack already running → `source setup.sh --stop` then redeploy.
5. Setup fails before Compose starts → inspect the reported
   `ov_models/model-download-*.log`; if loopback port `8640` is occupied, set
   `MODEL_DOWNLOAD_HOST_PORT` to a free port and rerun.

For anything past these basics - model-server crashes, OVMS token/cache/GPU
errors, host model-cache or model-download permission failures, search returning no results,
NPU/OpenGL issues - hand off to the installed `vss-troubleshoot` skill by name
and the canonical guide at `docs/user-guide/troubleshooting.md`.

## References

- Exact mode-to-overlay/profile/service/URL mapping:
  [`references/modes-and-overlays.md`](./references/modes-and-overlays.md).
- Required and optional environment variables:
  [`references/env-vars.md`](./references/env-vars.md).
