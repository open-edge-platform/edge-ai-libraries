# Get Started

## What it does

1. **Express install** — detects Core Ultra iGPU / Arc (CRI) and offers to
   proceed non-interactively with profile defaults.
2. **Host prep** — Intel GPU check (PCI vendor `8086`, `i915`/`xe` driver,
   `/dev/dri` render nodes, Level-Zero/OpenCL compute runtime via apt) and
   Docker install/group setup.
3. **Node.js** — installs Node.js via `nvm` if the local version is below
   the configured minimum.
4. **Inference backend** — starts OpenVINO Model Server (Docker, GPU
   passthrough); optionally exports a Hugging Face model to OpenVINO IR via
   OVMS's own `export_model.py` first (`--hf-model <id>`) — unlike plain
   `optimum-cli`, it also generates the MediaPipe graph OVMS's
   `/v3/chat/completions` endpoint needs. Set `HARNESS_OVMS_EXPORTER=model-download`
   to use edge-ai-libraries' Model Download microservice's ephemeral
   container instead (see [Known limitations](known-limitations.md)). Set
   `HARNESS_LLM_ROUTER_ENDPOINT` instead to route the agent at an existing
   external OpenAI-compatible router/gateway and skip OVMS entirely.
5. **Agent install** — installs the selected agent via its own official
   installer/package (`openclaw`, `dcode`, or Hermes's installer), wired to
   the OVMS endpoint.
6. **Onboarding** — verifies the installed agent and prints the
   endpoint to configure (OpenClaw's own provider-setup UX isn't fabricated
   here — see its repo for exact steps).

## Usage

```bash
./install.sh --agent openclaw --hf-model <huggingface-model-id>
```

```bash
./install.sh --agent deepagents-code --non-interactive
```

Or configure via environment variables:

```bash
export HARNESS_AGENT=openclaw
export HARNESS_HF_MODEL=<huggingface-model-id>
./install.sh --non-interactive
```

See [Sandbox management](sandbox-management.md), [Running without a checkout](running-without-a-checkout.md),
and [Uninstall](uninstall.md) for the rest of the usage surface.
