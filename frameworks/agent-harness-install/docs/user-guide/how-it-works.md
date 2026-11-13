# How it works

## Host-mode install flow

`./install.sh` is the only command you run. It prepares the host, brings up
the inference backend, installs the chosen agent, and wires the two together.
The diagram below describes host mode; OpenShell's automatic model selection,
sandbox lifecycle and onboarding are covered in the
[Agent Sandboxing guide](./agentic-ai-security/agent-sandboxing.md).

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "nodeSpacing": 40, "rankSpacing": 45, "curve": "basis"}}}%%
flowchart TD
    classDef step fill:#EAF3FB,stroke:#0068B5,color:#0A2A43
    classDef decision fill:#FFF6DD,stroke:#B38600,color:#4A3900
    classDef agent fill:#EAF7EE,stroke:#2E7D32,color:#123D17
    classDef done fill:#0068B5,stroke:#0068B5,color:#FFFFFF

    START(["./install.sh [--harness agent] --model id"]):::step
    CO{"Run from a<br/>source checkout?"}:::decision
    CLONE["Fetch the pinned<br/>HARNESS_INSTALL_REF<br/>into a temp dir"]:::step
    PAYLOAD["scripts/install.sh"]:::step

    START --> CO
    CO -- "yes" --> PAYLOAD
    CO -- "no, standalone" --> CLONE --> PAYLOAD

    subgraph PREP["Host preparation"]
        direction TB
        STARTUP["startup.sh<br/>curl and git, Docker, Node.js via nvm,<br/>Python venv and PyYAML"]:::step
        GPU["Intel GPU check<br/>driver, /dev/dri render nodes, compute runtime<br/>no GPU: continues CPU-only"]:::step
        STARTUP --> GPU
    end
    PAYLOAD --> STARTUP

    subgraph S1["Step 1 of 3: Inference routing"]
        direction TB
        EXT{"External router<br/>endpoint set?"}:::decision
        OVMS["Start OpenVINO Model Server<br/>Docker, GPU via --device"]:::step
        EXPORT["Fetch --model from its hub (default: Hugging Face,<br/>converted to OpenVINO IR) and register it<br/>with OVMS when it has a graph.pbtxt"]:::step
        IR["Pull and start the Inference Router<br/>intel/inference-router, in front of OVMS<br/>or of the external endpoint"]:::step
        EXT -- "yes (OVMS is not started)" --> IR
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
script) are fetched over HTTPS and verified against a SHA-256 before they run.
The Hermes and dcode installers come from pinned upstream commits with their
digests built in, so no flags are needed; the Docker convenience script still
needs a digest or an explicit opt-out.

## Runtime architecture

Once installed, the agent talks to a single OpenAI-compatible endpoint. The
Inference Router sits in front of OVMS (or of an external endpoint), and the
local containers run on a dedicated Docker network. Published ports bind to
127.0.0.1 by default; set `HARNESS_ADVERTISED_HOST` (a specific address) or
`HARNESS_BIND_HOST=0.0.0.0` (all interfaces) to reach them from other machines.
These LAN-publication overrides apply only to host mode; OpenShell mode
reuses the existing loopback publication and private backend network, but
requires inference ports to remain bound to `127.0.0.1` and validates the
running deployment's bindings and, for managed OVMS, backend network.
The diagram below shows the host-mode agent, not an OpenShell sandbox.
Neither service authenticates inbound requests, and Docker-published ports
bypass `ufw`, so restrict access with the `DOCKER-USER` iptables chain or bind
to a specific interface address.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "nodeSpacing": 40, "rankSpacing": 60, "curve": "basis"}}}%%
flowchart TD
    classDef host fill:#EAF3FB,stroke:#0068B5,color:#0A2A43
    classDef box fill:#FFFFFF,stroke:#0068B5,color:#0A2A43
    classDef store fill:#FFF6DD,stroke:#B38600,color:#4A3900
    classDef hw fill:#EAF7EE,stroke:#2E7D32,color:#123D17
    classDef ext fill:#F3F3F3,stroke:#777777,color:#222222,stroke-dasharray: 4 3

    subgraph HOST["Intel host: Core Ultra iGPU or Arc, or CPU-only"]
        direction TB
        AGENT["Agent CLI<br/>OpenClaw, Deep Agents Code, or Hermes"]:::box
        subgraph NET["Docker network: agent-harness-install-backend"]
            direction TB
            IRC["Inference Router<br/>#lt;host-ip#gt;:8010/v1"]:::box
            OVMSC["OpenVINO Model Server<br/>#lt;host-ip#gt;:8000/v3"]:::box
        end
        MODELS[("OpenVINO models<br/>~/.agent-harness-install/models")]:::store
        GPUD["Intel GPU<br/>/dev/dri render nodes"]:::hw
    end
    EXTR["External OpenAI-compatible endpoint<br/>HARNESS_LLM_ROUTER_ENDPOINT"]:::ext
    REMOTE["Other machines on the network<br/>optional"]:::ext

    AGENT -- "OpenAI-compatible API<br/>host-ip is 127.0.0.1 by default" --> IRC
    IRC -- "container name" --> OVMSC
    OVMSC --- MODELS
    OVMSC -. "--device and --group-add" .-> GPUD
    IRC -. "or, when HARNESS_LLM_ROUTER_ENDPOINT is set" .-> EXTR
    REMOTE -. "only when HARNESS_ADVERTISED_HOST or HARNESS_BIND_HOST is set" .-> IRC
    class HOST host
```

## OpenShell sandbox runtime

For OpenShell, the agent runs in its own non-root sandbox. The attached
inference provider grants access to IR; managed IR-to-OVMS traffic stays on a
private Docker network. Agent UI access is forwarded privately on demand.
See the [Agent Sandboxing guide](./agentic-ai-security/agent-sandboxing.md)
for setup and security details.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "nodeSpacing": 40, "rankSpacing": 60, "curve": "basis"}}}%%
flowchart TD
    classDef host fill:#EAF3FB,stroke:#0068B5,color:#0A2A43
    classDef box fill:#FFFFFF,stroke:#0068B5,color:#0A2A43
    classDef agent fill:#EAF7EE,stroke:#2E7D32,color:#123D17
    classDef store fill:#FFF6DD,stroke:#B38600,color:#4A3900
    classDef ext fill:#F3F3F3,stroke:#777777,color:#222222,stroke-dasharray:4 3

    USER["User workstation<br/>OpenShell CLI or privately forwarded UI"]:::ext

    subgraph HOST["Linux host"]
        direction TB
        subgraph SANDBOX["OpenShell sandbox: non-root agent"]
            direction TB
            AGENT["OpenClaw or Hermes"]:::agent
            TOOLS["Agent tools and workspace<br/>sandbox filesystem policy"]:::box
            AGENT --> TOOLS
        end
        GATEWAY["OpenShell gateway<br/>lifecycle and policy control"]:::box

        subgraph INFERENCE["Shared inference: host loopback"]
            direction LR
            IR["Inference Router<br/>127.0.0.1:8010"]:::box
            subgraph BACKEND["Private Docker network"]
                direction LR
                OVMS["OpenVINO Model Server"]:::box
                MODEL[("Selected model<br/>GPU when available")]:::store
                OVMS --> MODEL
            end
            IR --> OVMS
        end
    end

    EXTERNAL["External inference endpoint<br/>optional route configured on IR"]:::ext
    EGRESS["Web search, browsing, MCP<br/>additional policy required"]:::ext

    USER -->|"OpenShell connect or UI tunnel"| AGENT
    GATEWAY -. "creates and controls" .-> SANDBOX
    AGENT -->|"Attached provider<br/>host.openshell.internal:8010/v1"| IR
    IR -. "when externally configured" .-> EXTERNAL
    AGENT -. "not allowed by default" .-> EGRESS
```
