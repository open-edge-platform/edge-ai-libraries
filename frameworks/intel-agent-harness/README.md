# Intel Agentic Harness

A generic setup script for deploying your own Node.js-based CLI/agent
project onto Intel hardware (tested against Intel Core Ultra iGPU and Arc
(CRI) GPUs; degrades gracefully to CPU-only when no Intel GPU is present).

# Intel Agentic Harness

A generic setup script for deploying your own Node.js-based CLI/agent
project onto Intel hardware (tested against Intel Core Ultra iGPU and Arc
(CRI) GPUs; degrades gracefully to CPU-only when no Intel GPU is present).

## Vision: Agentic Harness

The standalone agent-plus-inference stack this repo installs (OpenClaw /
LangChain's Deep Agents Code / Hermes, wired to a local OpenVINO Model
Server). In the code/CLI this is still called the "agent" install step
(`HARNESS_AGENT`, `scripts/lib/agents.sh`) — "Agentic Harness" is the product
name for that same stack, per the OEP Agentic Blueprint's terminology (the
`HARNESS_` env var prefix predates this and is kept as-is for compatibility).

Uses a staged install flow (spinner/logging helpers, Node.js-via-nvm
bootstrap, Docker setup, CLI verification, express install) with a
**Docker-based sandbox manager** for running containerized workloads —
Intel GPUs don't need a CDI step, since render nodes under `/dev/dri` pass
straight through to containers via `--device`.

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
GPUs — but setting `HARNESS_LLM_ROUTER_ENDPOINT` routes the agent to any
existing OpenAI-compatible endpoint instead (e.g. Ollama, vLLM), and this
installer never starts, stops, or health-checks that endpoint (`status`
reports it as "Routed externally").

## Documentation

- [Get Started](docs/user-guide/get-started.md): install flow and basic usage.
- [Sandbox Management](docs/user-guide/sandbox-management.md): run your own
  containerized workloads, with an optional shared reverse-proxy gateway.
- [Running Without a Checkout](docs/user-guide/running-without-a-checkout.md):
  the standalone `curl | bash` bootstrap path.
- [Uninstall](docs/user-guide/uninstall.md).
- [Known Limitations](docs/user-guide/known-limitations.md).

## Layout

```
install.sh                   thin bootstrap (delegates to scripts/install.sh, or self-clones)
uninstall.sh                  removes sandboxes, OVMS, the installed agent, and state dir
scripts/install.sh            payload: install flow + sandbox/onboard subcommands
scripts/lib/colors.sh         logging/spinner helpers
scripts/lib/state.sh          state dir, symlink-safe path assertions, atomic writes
scripts/lib/sudo.sh           non-interactive-safe sudo authorization
scripts/lib/shim.sh           CLI shim + PATH profile management
scripts/lib/gpu-intel.sh      Intel GPU + compute-runtime readiness detection (no install)
scripts/lib/docker-setup.sh   Docker install/group setup + GPU device args
scripts/lib/nodejs.sh         Node.js-via-nvm bootstrap
scripts/lib/openvino.sh       OpenVINO Model Server (OpenAI-compatible inference)
scripts/lib/agents.sh         Agentic Harness's agent catalog: openclaw / deepagents-code (dcode) / hermes
scripts/lib/gateway.sh        optional shared reverse-proxy for sandbox traffic
scripts/lib/sandbox.sh        Docker-based sandbox/gateway manager
scripts/lib/harness-mcp.sh    registers an arbitrary MCP endpoint URL with an agent (Hermes only)
scripts/lib/express.sh        Intel hardware profile detection (Core Ultra iGPU/Arc)
docs/user-guide/              usage documentation (see Documentation above)
```

## Design notes

This installer is deliberately lightweight and single-purpose: a
bootstrap/payload split, nvm-based Node.js bootstrapping, and a real,
verified agent catalog (openclaw, hermes, dcode), built specifically for
Intel Core Ultra iGPU / Arc (CRI) hardware (CPU fallback otherwise). No
fixed appliance concept, no CDI (Intel render nodes pass through directly
via `--device`), no gateway daemon beyond the optional single proxy
container. Downloaded scripts/binaries are verified over HTTPS with
SHA-256 pinning where a vendor checksum is available
(`scripts/lib/verify.sh`), and shape-checked otherwise. The standalone-fetch
bootstrap requires an explicit `HARNESS_INSTALL_REF` (a tag or commit) —
see [Running Without a Checkout](docs/user-guide/running-without-a-checkout.md).
Uninstall is a plain bash script.

## Extending

- `scripts/lib/gpu-intel.sh` only detects GPU/compute-runtime readiness; it
  assumes drivers are already provisioned (e.g. via Edge Pack:
  github.com/open-edge-platform/edge-pack) rather than installing them.
- `scripts/lib/express.sh`'s PCI device-ID prefixes are a starting subset;
  extend the `case` statement as you validate more hardware.



