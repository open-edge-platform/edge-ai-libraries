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

1. **Express install** — detects Core Ultra iGPU / Arc (CRI) and offers to
   proceed non-interactively with profile defaults.
2. **Host prep** — runs `startup.sh` (curl/git, Docker, Node.js, Python),
   then an Intel GPU check (PCI vendor `8086`, `i915`/`xe` driver,
   `/dev/dri` render nodes, Level-Zero/OpenCL compute runtime readiness --
   assumed already provisioned, e.g. via Edge Pack, not installed by this
   step).
3. **Inference backend** — starts OpenVINO Model Server (Docker, GPU
   passthrough); optionally exports a Hugging Face model to OpenVINO IR via
   OVMS's own "-py" Docker image in `--pull` mode (`--model <id>`, a Hugging
   Face id such as `org/name`) --
   unlike plain `optimum-cli`, it also generates the MediaPipe graph OVMS's
   `/v3/chat/completions` endpoint needs. For gated Hugging Face models,
   export `HF_TOKEN` first. Set `HARNESS_OVMS_EXPORTER=export-model-py`,
   `=model-download`, or `=hf-snapshot` (a plain download, no conversion, for
   HF repos already published as ready-to-serve OpenVINO IR) for alternate
   exporters (see [Known limitations](known-limitations.md)). `model-download`
   can also pull from hubs other than Hugging Face (`--model-hub`/
   `HARNESS_MODEL_HUB`: `ollama`, `ultralytics`, `geti`, `pipeline-zoo-models`,
   `omz`, `remote-url`, `hls`) — only the default `openvino` hub produces
   something OVMS can serve; the rest are downloaded for your own use, not
   registered with OVMS. Always also builds/starts the **Inference Router**
   (IR) in front of OVMS, pointed at it as IR's one configured provider —
   this step is mandatory whenever OVMS is the managed backend, not
   optional. The router image is built locally from a pinned commit of
   `microservices/inference-router` in `open-edge-platform/edge-ai-libraries`.
   Set `HARNESS_LLM_ROUTER_ENDPOINT` instead to route the agent
   at an existing external OpenAI-compatible router/gateway and skip OVMS
   and IR entirely.
4. **Agent install** — installs the selected agent via its own official
   installer/package (`openclaw`, `dcode`, or Hermes's installer), wired to
   the Inference Router's endpoint (or the external router endpoint, if set).
5. **Onboarding** — wires the installed agent to that endpoint and checks it:
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
./install.sh --harness openclaw --model <huggingface-model-id>
```

```bash
./install.sh --harness deepagents-code --non-interactive
```

Or configure via environment variables:

```bash
export HARNESS_AGENT=openclaw
export HARNESS_HF_MODEL=<huggingface-model-id>
./install.sh --non-interactive
```

Options: `--non-interactive`, `--skip-gpu-check`, `--harness <name>`,
`--model <id>`, `--model-hub <hub>`; run `./install.sh --help` for the full
list of options and environment variables.

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
