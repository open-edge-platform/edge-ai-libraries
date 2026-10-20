<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Get Started

## Prerequisites

`./install.sh` automatically runs `./startup.sh` first, which
installs/verifies `curl`/`git`, Docker, Node.js/npm (via `nvm`), and Python
(venv + PyYAML) -- there's only one script to run. `startup.sh` is idempotent
(safe to re-run; skips whatever is already present) and can also be run on
its own if you want finer-grained control (`--skip-base`, `--skip-docker`,
`--skip-nodejs`, `--skip-python`) or want to pre-provision a host before
installing anything:

```bash
./startup.sh --help
```

Notes on what it does with Docker:

- If `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` (either case) are set, it also
  writes them into the Docker daemon's own systemd config
  (`/etc/systemd/system/docker.service.d/http-proxy.conf`, root-only) so the
  daemon can pull images through the proxy, and restarts the daemon when that
  changes. This needs sudo; without it the step is skipped with a warning.
- If it just added your user to the `docker` group, it restarts itself under
  that group automatically, so no new terminal is needed. Only if that can't
  be done (`sg` and `sudo` both unavailable) does it exit with code `2` and
  ask you to open a new terminal (or run `newgrp docker`) and re-run.

## What it does

1. **Host prep** — runs `startup.sh` (curl/git, Docker, Node.js, Python),
   then an Intel GPU check (PCI vendor `8086`, `i915`/`xe` driver,
   `/dev/dri` render nodes, Level-Zero/OpenCL compute runtime readiness --
   assumed already provisioned, e.g. via Edge Pack, not installed by this
   step). Host users and groups are not modified: containers get render-node
   access through `--device` and `--group-add`.
2. **Inference backend** — requires a model: pass `--model` (the installer
   prompts for it on a terminal and fails otherwise, unless a model is already
   exported from an earlier run). Starts OpenVINO Model Server (Docker, GPU
   passthrough) and fetches that model from its hub
   (see [Model sources](#model-sources)). By default a Hugging Face id such
   as `org/name` is converted to OpenVINO IR via OVMS's own "-py" Docker image
   in `--pull` mode — unlike plain `optimum-cli`, that also generates the
   MediaPipe graph OVMS's `/v3/chat/completions` endpoint needs. For gated
   Hugging Face models, export `HF_TOKEN` first. Set
   `HARNESS_OVMS_EXPORTER=export-model-py` or `=hf-snapshot` (a plain
   download, no conversion, for HF repos already published as ready-to-serve
   OpenVINO IR) for alternate exporters (see
   [Known limitations](known-limitations.md)). Always also starts the
   **Inference Router** (IR) — every inference request goes through it. The
   router is the published `intel/inference-router` image, pulled once
   (set `HARNESS_IR_BUILD_FROM_SOURCE=1` to build it from a pinned commit of
   `microservices/inference-router` in `open-edge-platform/edge-ai-libraries`
   instead). By default IR's one configured provider is the local OVMS. Set
   `HARNESS_LLM_ROUTER_ENDPOINT` (and, if it needs one,
   `HARNESS_LLM_ROUTER_API_KEY`) to point IR at an existing external
   OpenAI-compatible endpoint instead; OVMS is then not started, and
   `--model` names the model that endpoint serves.
3. **Agent install** — installs the selected agent harness via its own official
   installer/package (`openclaw`, `dcode`, or Hermes's installer), wired to
   the Inference Router's endpoint.
4. **Onboarding** — wires the installed agent to that endpoint and checks it:
   - **OpenClaw:** registers the endpoint as a custom `ovms` model provider
     (`openclaw config set models.providers.ovms …`), sets it as the default
     model, and runs a smoke test. If `openclaw config set` fails (e.g. its
     Gateway daemon is running), it prints the exact manual command instead.
   - **Deep Agents Code (`dcode`):** writes its provider config and runs a
     smoke test; the smoke test is reported as failed if dcode prints an
     error, even when it exits 0.
   - **Hermes:** prints the endpoint and where to point a provider in its
     own config (`~/.hermes/config.yaml`); there is no automated smoke test.

Published ports (OVMS and the Router) bind to loopback
(`127.0.0.1`) by default, so nothing is reachable from other machines unless
you opt in with `HARNESS_ADVERTISED_HOST` (or the prompt that sets it) or
`HARNESS_BIND_HOST`.

## Usage

```bash
./install.sh --harness openclaw --model <org/name>
```

For example, with a small Hugging Face model (any supported model works):

```bash
./install.sh --harness openclaw --model Qwen/Qwen2.5-0.5B-Instruct
```

```bash
./install.sh --harness deepagents-code --model <org/name> --non-interactive
```

Or configure via environment variables:

```bash
export HARNESS_AGENT=openclaw
export HARNESS_HF_MODEL=<org/name>
./install.sh --non-interactive
```

For example:

```bash
export HARNESS_AGENT=openclaw
export HARNESS_HF_MODEL=Qwen/Qwen2.5-0.5B-Instruct
./install.sh --non-interactive
```

Options: `--non-interactive`, `--skip-gpu-check`, `--harness <name>`,
`--model <model-name>`, `--model-hub <hub>`, `--model-config <json>`,
`--model-revision <rev>`, `--model-type <type>`,
`--model-precision <int4|int8|fp16|fp32>`, `--model-device <device>`; run
`./install.sh --help` for the full list of options and environment variables.

## Model sources

`--model` is the model's name as its hub names it, and `--model-hub` says
which hub to fetch it from. Without `--model-hub` the hub is `openvino`: a
Hugging Face id that is converted to OpenVINO IR. Any other hub selects the
Model Download service's ephemeral container (`get_model.sh`, pinned and
checksum-verified) on its own — there is no need to set
`HARNESS_OVMS_EXPORTER`.

| `--model-hub` | `--model` is | Extra input | Served to agents |
|---|---|---|---|
| `openvino` (default) | Hugging Face id, `org/name` | `--model-precision`, `--model-device`; `HF_TOKEN` for gated models | yes |
| `huggingface` | Hugging Face id, `org/name` | `--model-revision`; `HF_TOKEN` for gated models | only if the repo already contains an OVMS `graph.pbtxt` |
| `remote-url` | plain name substituted for `{name}` | `--model-config '{"url":"https://…/{name}.tar"}'`; the URL must match Model Download's allowlist | only if the tarball contains a `graph.pbtxt` |
| `ollama` | `name`, `name:tag`, or a namespaced reference such as `hf.co/user/repo:tag` | | no (OVMS cannot load Ollama models yet) |
| `ultralytics` | model name or a comma-separated list | `--model-config '{"quantize":"coco128"}'` for INT8 | no |
| `geti` | Geti project name | `GETI_HOST`, `GETI_TOKEN`, `GETI_WORKSPACE_ID` | no |
| `pipeline-zoo-models`, `omz` | model name or a comma-separated list | | no |
| `hls` | any label | `--model-type 3d-pose`, `rppg` or `ai-ecg` | no |

A model is served — registered with OVMS and wired to the Inference Router
— only when the download contains an OVMS `graph.pbtxt`. Everything else is
downloaded and tracked (`./install.sh models list` shows it as "not served by
OVMS"), and the installer says why agents will not use it. The router stays
on whatever OVMS already serves, so one model is served at a time.

```bash
# default: Hugging Face id, converted to OpenVINO IR
./install.sh --harness openclaw --model <org/name>

# Ollama: downloaded and tracked, not served by OVMS yet
./install.sh --harness openclaw --model-hub ollama --model <name:tag>

# a model tarball from an allowed URL
./install.sh --harness openclaw --model-hub remote-url --model <name> \
  --model-config '{"url":"https://github.com/open-edge-platform/edge-ai-resources/raw/main/{name}.tar"}'
```

Options that an exporter does not use (for example `--model-device` with the
default exporter) are reported as ignored.

Other commands:

```bash
./install.sh status                                # host, OVMS/Router and agent health (read-only)
./install.sh onboard                               # re-run onboarding only
./install.sh models list                           # exported/downloaded models
./install.sh models remove <name>                  # delete one (and its OVMS config entry)
./install.sh mcp register <name> <url> [agent]     # register an MCP endpoint (Hermes, OpenClaw, or HARNESS_MCP_REGISTER_CMD)
./install.sh skill <install|list|remove> [path|name]   # Hermes skills only
```

See [Running without a checkout](running-without-a-checkout.md),
and [Uninstall](uninstall.md) for the rest of the usage surface.
