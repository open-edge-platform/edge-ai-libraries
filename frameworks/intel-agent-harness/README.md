# Intel Agent Harness

A generic setup script for deploying your own Node.js-based CLI/agent
project onto Intel hardware (tested against Intel Core Ultra iGPU and Arc
(CRI) GPUs; degrades gracefully to CPU-only when no Intel GPU is present).

## Vision: Harness + edge microservices

This project has two parts:

1. **The Harness** — the standalone agent-plus-inference stack this repo
   already installs (OpenClaw / LangGraph Deep Agents / Hermes, wired to a
   local OpenVINO Model Server). This is what `./install.sh` sets up today,
   and it's meant to run on its own, independent of any particular edge use
   case. In the code/CLI this is still called the "agent" install step
   (`HARNESS_AGENT`, `scripts/lib/agents.sh`) — "Harness" is the product
   name for that same stack.
2. **Edge/client microservices** — a separate, additive track: driving real
   edge/client experiences by deploying independently-published edge
   workloads alongside the Harness. Implemented as a generic mechanism
   (`./install.sh edge ...`, see "Edge microservices" under Usage) rather
   than anything project-specific — configure it via `EDGE_SERVICE_*` env
   vars to clone/build/run any Dockerized service and optionally register
   its endpoint with the Harness agent over MCP.

Uses a staged install flow (spinner/logging helpers, Node.js-via-nvm
bootstrap, Docker setup, CLI verification, third-party notice, express
install) with a
**Docker-based sandbox manager** for running containerized workloads —
Intel GPUs don't need a CDI step, since render nodes under `/dev/dri` pass
straight through to containers via `--device`.

This installer installs **real, independently-published open-source agent
projects** rather than something invented for Intel:

| Agent | Verified package | License |
|---|---|---|
| `openclaw` | npm `openclaw` — github.com/openclaw/openclaw | MIT |
| `deepagents-code` | npm `deepagents` (LangGraph) — github.com/langchain-ai/deepagentsjs | MIT |
| `hermes` | Nous Research's official installer — github.com/NousResearch/hermes-agent (curl \| bash from hermes-agent.nousresearch.com, not npm) | MIT |

The inference backend is **configurable**. By default it's a local
**OpenVINO Model Server** (OVMS) serving an OpenAI-compatible
`/v3/chat/completions` endpoint on Intel Core Ultra iGPU and Arc (CRI)
GPUs — but setting `HARNESS_LLM_ROUTER_ENDPOINT` routes the agent to any
existing OpenAI-compatible endpoint instead (e.g. Ollama, vLLM), and this
installer never starts, stops, or health-checks that endpoint (`status`
reports it as "Routed externally").

## What it does

1. **Third-party software notice** — must be accepted once (interactively,
   or via `--yes-i-accept-third-party-software` / `ACCEPT_THIRD_PARTY_SOFTWARE=1`)
   before anything installs. Text lives in `notice.json`.
2. **Express install** — detects Core Ultra iGPU / Arc (CRI) and offers to
   proceed non-interactively with profile defaults.
3. **Host prep** — Intel GPU check (PCI vendor `8086`, `i915`/`xe` driver,
   `/dev/dri` render nodes, Level-Zero/OpenCL compute runtime via apt) and
   Docker install/group setup.
4. **Node.js** — installs Node.js via `nvm` if the local version is below
   the configured minimum.
5. **Inference backend** — starts OpenVINO Model Server (Docker, GPU
   passthrough); optionally exports a Hugging Face model to OpenVINO IR via
   OVMS's own `export_model.py` first (`--hf-model <id>`) — unlike plain
   `optimum-cli`, it also generates the MediaPipe graph OVMS's
   `/v3/chat/completions` endpoint needs. Set `HARNESS_LLM_ROUTER_ENDPOINT`
   instead to route the agent at an existing external OpenAI-compatible
   router/gateway and skip OVMS entirely.
6. **Harness install** — `npm install -g openclaw`, or scaffolds a thin
   LangGraph `deepagents` runner, wired to the OVMS endpoint.
7. **Onboarding** — verifies the installed Harness agent and prints the
   endpoint to configure (OpenClaw's own provider-setup UX isn't fabricated
   here — see its repo for exact steps).

## Usage

```bash
./install.sh --agent openclaw --hf-model <huggingface-model-id>
```

```bash
./install.sh --agent deepagents-code --non-interactive --yes-i-accept-third-party-software
```

Or configure via environment variables:

```bash
export HARNESS_AGENT=openclaw
export HARNESS_HF_MODEL=<huggingface-model-id>
./install.sh --non-interactive --yes-i-accept-third-party-software
```

### Sandbox management (for your own containerized project)

```bash
./install.sh sandbox list
./install.sh sandbox create my-project your-image:tag
./install.sh sandbox stop my-project
./install.sh sandbox backup my-project        # commits a recovery image
./install.sh sandbox recover my-project        # restarts, or rebuilds from backup
./install.sh sandbox destroy my-project --force
./install.sh connect my-project                # open a shell inside it
```

### Sandbox gateway (optional)

By default, sandboxes publish their port straight to the host — simple, but
the container holds its own credentials/env directly and anything on the
host can reach it. Set `HARNESS_GATEWAY_ENABLED=1` to instead route sandbox
traffic through a single shared reverse-proxy container: sandboxes join a
private Docker network with no published port, and the gateway is the only
thing that can reach them.

```bash
export HARNESS_GATEWAY_ENABLED=1
./install.sh sandbox create my-project your-image:tag
./install.sh sandbox list                 # shows the gateway route instead of a host port
```

Routes live in a JSON file under `~/.intel-agent/gateway/`, re-read by the
proxy on every request — no gateway restart needed to add/remove one. A
route can carry a server-held credential (`Authorization` header) that's
injected on the way to the real target; the client's own `Authorization`
header is never forwarded. This is intentionally a single lightweight proxy
container, not a systemd-managed daemon or a full-featured gateway product —
just enough to avoid publishing sandbox ports directly.

### Status

```bash
./install.sh status
```

Read-only combined health view: Docker/GPU, the OpenVINO Model Server, the
installed Harness agent, and every registered sandbox in one place.

### Edge microservices (generic — any Dockerized MCP/HTTP service)

`edge` is a thin, project-agnostic layer over the sandbox manager: it
clones a repo (or uses a prebuilt image), builds it, runs it as a sandbox,
and can register its endpoint with the installed Harness agent as an MCP
server. It has no knowledge of any specific project — configure it entirely
via env vars:

```bash
export EDGE_SERVICE_REPO_URL=https://github.com/<org>/<repo>.git
export EDGE_SERVICE_DOCKERFILE=path/to/Dockerfile   # relative to the repo root
export EDGE_SERVICE_ENV="SOME_VAR=value"            # optional, space-separated KEY=VALUE
export EDGE_SERVICE_CONTAINER_PORT=8000             # optional, if the image has a fixed listen port

./install.sh edge create my-service
./install.sh edge endpoint my-service
./install.sh edge register-mcp my-service hermes
./install.sh edge destroy my-service
```

Use `EDGE_SERVICE_IMAGE=<prebuilt-image>` instead of `EDGE_SERVICE_REPO_URL`/
`EDGE_SERVICE_DOCKERFILE` to skip cloning and building entirely. MCP
registration is built in for Hermes's real `~/.hermes/config.yaml` shape (via
`HERMES_CONFIG`). For any other agent, set
`HARNESS_MCP_REGISTER_CMD=<script>` to a program that takes
`<agent> <name> <url>` and writes that agent's real config — this installer
won't guess an unverified format, but it will call yours.

### Running without a checkout

`install.sh` is a thin bootstrap: if it finds `scripts/install.sh` next to it
(a normal checkout), it just runs that. If it's fetched standalone (e.g.
`curl -fsSL <url>/install.sh | bash`), it clones this installer's own repo at
a pinned ref into a temp dir first, then runs the payload from there:

```bash
export HARNESS_INSTALL_REPO=https://github.com/<you>/<your-fork>.git
export HARNESS_INSTALL_REF=v1.0.0   # optional — defaults to .version, then main
curl -fsSL https://raw.githubusercontent.com/<you>/<your-fork>/main/install.sh | bash
```

`HARNESS_INSTALL_REPO` has no default — this installer refuses to guess
which repo to clone. `HARNESS_INSTALL_REF` is also required in this mode —
there's no local `.version` file to fall back to, and this installer refuses
to silently run whatever `main` currently contains. If `HARNESS_INSTALL_REPO`
is a monorepo where this installer lives under a subdirectory (rather than
at the repo root), set `HARNESS_INSTALL_SUBDIR` to that path.

For this repo specifically, with no local clone:

```bash
curl -fsSL https://raw.githubusercontent.com/intel-sandbox/intel-agent-harness/main/install.sh \
  | HARNESS_INSTALL_REPO=https://github.com/intel-sandbox/intel-agent-harness.git bash
```

Installer flags/env after the piped script need `-s --` first, since stdin is
already consumed by the pipe:

```bash
curl -fsSL https://raw.githubusercontent.com/intel-sandbox/intel-agent-harness/main/install.sh \
  | HARNESS_INSTALL_REPO=https://github.com/intel-sandbox/intel-agent-harness.git \
    bash -s -- --agent openclaw --non-interactive --yes-i-accept-third-party-software
```

If the repo is private, anonymous `curl`/`git fetch` will fail here (401/404)
— clone it with your own git credentials first and run `./install.sh` from
that checkout instead (the normal source-checkout path above).

### Uninstall

```bash
./uninstall.sh                  # prompts, keeps exported models
./uninstall.sh --yes --delete-models --agent openclaw
./uninstall.sh --yes --keep-agent-data --agent hermes   # keep ~/.hermes (sessions, memories, skills)
```

Removes registered sandboxes, the OpenVINO Model Server container, the
installed agent (its actual package — e.g. `npm uninstall -g openclaw`, or
Hermes's own data directory `~/.hermes` — not just its CLI shim), and the
`~/.intel-agent` state directory. Docker, Node.js/nvm, and the Intel compute
runtime are left in place. Pass `--keep-agent-data` to preserve Hermes's
config/sessions/memories/skills instead of deleting them.

## Layout

```
install.sh                   thin bootstrap (delegates to scripts/install.sh, or self-clones)
uninstall.sh                  removes sandboxes, OVMS, the installed agent, and state dir
.version                      ref the bootstrap clones when fetched standalone
notice.json                  third-party software notice text/version
scripts/install.sh            payload: install flow + sandbox/onboard subcommands
scripts/lib/colors.sh         logging/spinner helpers
scripts/lib/state.sh          state dir, symlink-safe path assertions, atomic writes
scripts/lib/sudo.sh           non-interactive-safe sudo authorization
scripts/lib/shim.sh           CLI shim + PATH profile management
scripts/lib/gpu-intel.sh      Intel GPU detection + compute-runtime install
scripts/lib/docker-setup.sh   Docker install/group setup + GPU device args
scripts/lib/nodejs.sh         Node.js-via-nvm bootstrap
scripts/lib/openvino.sh       OpenVINO Model Server (OpenAI-compatible inference)
scripts/lib/agents.sh         Harness catalog: openclaw / deepagents-code / hermes
scripts/lib/notice.sh         third-party notice acceptance flow
scripts/lib/gateway.sh        optional shared reverse-proxy for sandbox traffic
scripts/lib/sandbox.sh        Docker-based sandbox/gateway manager
scripts/lib/edge.sh           generic Dockerized edge-microservice manager (clone/build/run)
scripts/lib/harness-mcp.sh    registers an edge microservice's endpoint as an MCP server (Hermes only)
scripts/lib/express.sh        Intel hardware profile detection (Core Ultra iGPU/Arc)
```

## Known limitations

- OpenClaw's own provider/config CLI surface isn't reproduced here. Its npm
  package is confirmed real and installable, but its runtime configuration
  commands aren't modeled, so onboarding reports the endpoint to configure
  (the OVMS endpoint) rather than fabricating flags.
- "Hermes" installs via its own official installer (curl | bash), not npm —
  this installer downloads and runs it unattended (`--skip-setup --non-interactive`).
  Nous Research doesn't publish a static checksum for it, so this installer
  refuses to run it unverified: set `HERMES_INSTALL_SHA256` (once you've
  reviewed a known-good copy) or `HERMES_ALLOW_UNVERIFIED_INSTALL=1` before
  installing the `hermes` agent, or it will fail with guidance.
- The Docker-based sandbox manager (`scripts/lib/sandbox.sh`) publishes
  ports directly by default. `HARNESS_GATEWAY_ENABLED=1` routes sandbox
  traffic through a single shared reverse-proxy container instead (see
  "Sandbox gateway" above) — still just one plain container, with no
  systemd-managed daemon or cross-process port-collision avoidance.
- Intel's Core Ultra iGPU/Arc lineup has no fixed appliance concept, so
  there's no dual-node pairing/reboot-resume receipt handling.
- Model export (`optimum-cli export openvino`) is CPU/host-bound and can be
  slow for large models.
- `edge`'s MCP registration has Hermes's config shape built in; other agents
  need `HARNESS_MCP_REGISTER_CMD` set to a real registration script, and no
  specific Dockerized microservice has been exercised end-to-end yet.

## Design notes

This installer is deliberately lightweight and single-purpose: a
bootstrap/payload split, nvm-based Node.js bootstrapping, and a real,
verified agent catalog (openclaw, hermes, deepagents-code), built
specifically for Intel Core Ultra iGPU / Arc (CRI) hardware (CPU fallback
otherwise). About 3,100 lines across 21 focused files — no fixed appliance
concept, no CDI (Intel render nodes pass through directly via `--device`),
no gateway daemon beyond the optional single proxy container. Downloaded
scripts/binaries are verified over HTTPS with SHA-256 pinning where a
vendor checksum is available (`scripts/lib/verify.sh`), and shape-checked
otherwise. Version resolution for the standalone-fetch bootstrap is env
var, then `.version` file, then `main`. Uninstall is a plain bash script.

## Edge microservices

See "Edge microservices" under Usage above for the generic `edge` mechanism.
It's deliberately project-agnostic: any repo with a Dockerfile (or any
prebuilt image) that exposes an HTTP/MCP endpoint fits the same
`EDGE_SERVICE_*` env vars.

## Extending

- `scripts/lib/gpu-intel.sh` currently supports apt-based distros for the
  compute-runtime install; add a branch there for other package managers.
- `scripts/lib/express.sh`'s PCI device-ID prefixes are a starting subset;
  extend the `case` statement as you validate more hardware.
- `scripts/lib/agents.sh`'s `install_deepagents_runner` is a minimal
  scaffold — replace `index.mjs` with your actual agent graph/tools.


