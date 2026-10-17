# agent-harness-install

An installer that deploys an AI coding agent onto Intel hardware and wires it
to a local, OpenAI-compatible inference endpoint (tested against Intel Core
Ultra iGPU and Arc (CRI) GPUs; degrades gracefully to CPU-only when no Intel
GPU is present).

This installer installs **real, independently-published open-source agent
projects** rather than something invented for Intel:

| Agent | Verified package | License |
|---|---|---|
| `openclaw` | npm `openclaw` — github.com/openclaw/openclaw | MIT |
| `deepagents-code` | `dcode` (Deep Agents Code) — github.com/langchain-ai/deepagents | MIT |
| `hermes` | Nous Research's official installer — github.com/NousResearch/hermes-agent (curl \| bash from hermes-agent.nousresearch.com, not npm) | MIT |

The inference backend is **configurable**. By default it's a local
**OpenVINO Model Server** (OVMS) serving an OpenAI-compatible
`/v3/chat/completions` endpoint on Intel Core Ultra iGPU and Arc (CRI)
GPUs, always fronted by a locally-built **Inference Router** (IR) — agents
are wired to the Router's endpoint, never directly to OVMS's. Setting
`HARNESS_LLM_ROUTER_ENDPOINT` instead routes the agent to any existing
OpenAI-compatible endpoint you already operate (e.g. Ollama, vLLM, an
internal gateway), bypassing both OVMS and the Router entirely — this
installer never starts, stops, or health-checks that endpoint (`status`
reports it as "Routed externally").

## How it works

### Install flow

`./install.sh` is the only command you run. It prepares the host, brings up
the inference backend, installs the chosen agent, and wires the two together.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "nodeSpacing": 40, "rankSpacing": 45, "curve": "basis"}}}%%
flowchart TD
    classDef step fill:#EAF3FB,stroke:#0068B5,color:#0A2A43
    classDef decision fill:#FFF6DD,stroke:#B38600,color:#4A3900
    classDef agent fill:#EAF7EE,stroke:#2E7D32,color:#123D17
    classDef done fill:#0068B5,stroke:#0068B5,color:#FFFFFF

    START(["./install.sh [--harness agent] [--model id]"]):::step
    CO{"Run from a<br/>source checkout?"}:::decision
    CLONE["Fetch the pinned<br/>HARNESS_INSTALL_REF<br/>into a temp dir"]:::step
    PAYLOAD["scripts/install.sh"]:::step

    START --> CO
    CO -- "yes" --> PAYLOAD
    CO -- "no, standalone" --> CLONE --> PAYLOAD

    subgraph PREP["Host preparation"]
        direction TB
        STARTUP["startup.sh<br/>curl and git, Docker, Node.js via nvm,<br/>Python venv and PyYAML"]:::step
        GPU["Express profile and Intel GPU check<br/>driver, /dev/dri render nodes, compute runtime<br/>no GPU: continues CPU-only"]:::step
        STARTUP --> GPU
    end
    PAYLOAD --> STARTUP

    subgraph S1["Step 1 of 3: Inference routing"]
        direction TB
        EXT{"External router<br/>endpoint set?"}:::decision
        USEEXT["Use that OpenAI-compatible endpoint<br/>(HARNESS_LLM_ROUTER_ENDPOINT)<br/>OVMS and the Router are not started"]:::step
        OVMS["Start OpenVINO Model Server<br/>Docker, GPU via --device"]:::step
        EXPORT["Fetch --model from its hub (default: Hugging Face,<br/>converted to OpenVINO IR) and register it<br/>with OVMS when it has a graph.pbtxt"]:::step
        IR["Build and start the Inference Router<br/>pinned upstream commit, in front of OVMS"]:::step
        EXT -- "yes" --> USEEXT
        EXT -- "no" --> OVMS --> EXPORT --> IR
    end
    GPU --> EXT

    subgraph S2["Step 2 of 3: Agent install"]
        direction TB
        PICK{"HARNESS_AGENT"}:::decision
        OC["OpenClaw<br/>npm install -g"]:::agent
        DC["Deep Agents Code<br/>dcode installer"]:::agent
        HM["Hermes<br/>official installer"]:::agent
        PICK --> OC
        PICK --> DC
        PICK --> HM
    end
    IR --> PICK
    USEEXT --> PICK

    subgraph S3["Step 3 of 3: Onboarding"]
        direction TB
        ONB["Point the agent at the endpoint<br/>OpenClaw and dcode: configure and smoke-test<br/>Hermes: print the endpoint to configure"]:::step
    end
    OC --> ONB
    DC --> ONB
    HM --> ONB

    FINISH(["Installation complete"]):::done
    ONB --> FINISH
```

Third-party downloads (the Hermes and dcode installers, Docker's convenience
script) are fetched over HTTPS and verified against a SHA-256 before they run;
the installer stops if no digest is available unless you opt out explicitly.

### Runtime architecture

Once installed, the agent talks to a single OpenAI-compatible endpoint. The
Inference Router sits in front of OVMS, and both run as containers on a
dedicated Docker network. Published ports bind to loopback by default.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "nodeSpacing": 40, "rankSpacing": 60, "curve": "basis"}}}%%
flowchart LR
    classDef host fill:#EAF3FB,stroke:#0068B5,color:#0A2A43
    classDef box fill:#FFFFFF,stroke:#0068B5,color:#0A2A43
    classDef store fill:#FFF6DD,stroke:#B38600,color:#4A3900
    classDef hw fill:#EAF7EE,stroke:#2E7D32,color:#123D17
    classDef ext fill:#F3F3F3,stroke:#777777,color:#222222,stroke-dasharray: 4 3

    subgraph HOST["Intel host: Core Ultra iGPU or Arc, or CPU-only"]
        direction LR
        AGENT["Agent CLI<br/>OpenClaw, Deep Agents Code, or Hermes"]:::box
        subgraph NET["Docker network: agent-harness-install-backend"]
            direction TB
            IRC["Inference Router<br/>127.0.0.1:8010/v1"]:::box
            OVMSC["OpenVINO Model Server<br/>127.0.0.1:8000/v3"]:::box
        end
        MODELS[("OpenVINO models<br/>~/.agent-harness-install/models")]:::store
        GPUD["Intel GPU<br/>/dev/dri render nodes"]:::hw
    end
    EXTR["External OpenAI-compatible endpoint<br/>HARNESS_LLM_ROUTER_ENDPOINT"]:::ext

    AGENT -- "OpenAI-compatible API" --> IRC
    IRC -- "container name" --> OVMSC
    OVMSC --- MODELS
    OVMSC -. "--device and --group-add" .-> GPUD
    AGENT -. "optional: bypasses OVMS and the Router" .-> EXTR
    class HOST host
```

## Documentation

- [Get Started](docs/user-guide/get-started.md): install flow, usage and
  [model sources](docs/user-guide/get-started.md#model-sources) (Hugging Face,
  Ollama, remote URL and the other Model Download hubs).
- [Running Without a Checkout](docs/user-guide/running-without-a-checkout.md):
  the standalone `curl | bash` bootstrap path.
- [Uninstall](docs/user-guide/uninstall.md).
- [Known Limitations](docs/user-guide/known-limitations.md).

## Layout

```
startup.sh                    prerequisite setup: installs/verifies curl/git, Docker, Node.js/npm, Python -- run automatically by install.sh, or standalone
install.sh                   thin bootstrap (delegates to scripts/install.sh, or self-clones)
uninstall.sh                  removes the Inference Router, OVMS, the installed agent, and state dir
scripts/install.sh            payload: install flow + status/onboard/models/mcp/skill subcommands
scripts/lib/colors.sh         logging/spinner helpers
scripts/lib/state.sh          state dir, symlink-safe path assertions, atomic writes
scripts/lib/sudo.sh           non-interactive-safe sudo authorization
scripts/lib/verify.sh         HTTPS-only, checksum-verified downloads of third-party scripts
scripts/lib/shim.sh           CLI shim + PATH profile management
scripts/lib/gpu-intel.sh      Intel GPU + compute-runtime readiness detection (no install)
scripts/lib/docker-setup.sh   Docker install/group setup, Docker daemon proxy config + GPU device args
scripts/lib/nodejs.sh         Node.js-via-nvm bootstrap
scripts/lib/python-setup.sh   Python (venv + PyYAML) bootstrap
scripts/lib/openvino.sh       OpenVINO Model Server (OpenAI-compatible inference)
scripts/lib/inference-router.sh  Inference Router (always built/run in front of OVMS; agents are wired to it, not OVMS directly)
scripts/lib/agents.sh         agent-harness-install's agent catalog: openclaw / deepagents-code (dcode) / hermes
scripts/lib/harness-mcp.sh    registers an arbitrary MCP endpoint URL with an agent (Hermes and OpenClaw built in; others via HARNESS_MCP_REGISTER_CMD)
scripts/lib/express.sh        Intel hardware profile detection (Core Ultra iGPU/Arc)
docs/user-guide/              usage documentation (see Documentation above)
test/smoke-test.sh            end-to-end smoke test suite (phased; see --list)
test/full-flow-test.sh        full install -> real chat completion -> uninstall run, per agent
```

## Design notes

This installer is deliberately lightweight and single-purpose: a
bootstrap/payload split, nvm-based Node.js bootstrapping, and a real,
verified agent catalog (openclaw, hermes, dcode), built specifically for
Intel Core Ultra iGPU / Arc (CRI) hardware (CPU fallback otherwise). No
fixed appliance concept, no CDI (Intel render nodes pass through directly
via `--device`). Downloaded third-party scripts are fetched over HTTPS only and
verified against a SHA-256 (`scripts/lib/verify.sh`); where the vendor
publishes none (Hermes, dcode, Docker's convenience script) the installer
refuses to run the download unless you pin a digest or explicitly opt out.
Source builds (the Inference Router) and the Model Download script are pinned
to full commit SHAs. The standalone-fetch
bootstrap requires an explicit `HARNESS_INSTALL_REF` (a tag or commit) —
see [Running Without a Checkout](docs/user-guide/running-without-a-checkout.md).
Uninstall is a plain bash script.

## Extending

- `scripts/lib/gpu-intel.sh` only detects GPU/compute-runtime readiness; it
  assumes drivers are already provisioned (e.g. via Edge Pack:
  github.com/open-edge-platform/edge-pack) rather than installing them.
- `scripts/lib/express.sh`'s PCI device-ID prefixes are a starting subset;
  extend the `case` statement as you validate more hardware.



