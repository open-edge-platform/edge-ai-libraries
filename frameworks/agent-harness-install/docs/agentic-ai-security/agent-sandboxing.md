<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Agent Sandboxing

## Introduction

Sandboxing separates an agent's tool execution from the host environment and
limits the files and network endpoints available to it. Agent Harness Install
currently provides this capability through the experimental OpenShell runtime
for OpenClaw and Hermes. Host mode remains the default.

This is one layer of [Agentic AI Security](README.md), not prompt protection or
PII masking. A sandbox can still perform unwanted actions within its permitted
workspace and allowed services. Review tool effects, protect credentials and
grant only the access needed for a task.

## Architecture and security boundaries

```text
Interactive client
       |
       v
OpenShell sandbox: OpenClaw or Hermes (non-root)
       |
       | Attached inference provider
       | http://host.openshell.internal:8010/v1
       v
Shared Inference Router (host loopback publication)
       |
       | Private Docker backend network
       v
Managed OVMS -> selected model (GPU when available)
```

Each agent has an independently owned profile under
`~/.agent-harness-install/openshell/<agent>/`. Both use shared inference.
Existing host agent configuration is not imported or modified during sandbox
installation. External inference is configured on shared IR using
`HARNESS_LLM_ROUTER_ENDPOINT`, not directly in the sandbox; in that case IR
routes to the external backend instead of managed OVMS.

Sandbox images install the same pinned agent packages/installers as host mode,
run as a non-root user and do not mount host agent homes, model directories or
the Docker socket. Runtime egress is limited to the attached inference provider.
Web search, external browsing, MCP, package downloads, updates and messaging
need explicit additional policy and any required tool dependencies/credentials.
Working LLM inference does not establish external web-tool connectivity.
The host `mcp`/`skill` helpers reject OpenShell mode rather than modifying the
wrong agent.

Landlock uses OpenShell's `best_effort` compatibility setting; this is not a
claim that every host supports the same filesystem isolation guarantees.
This integration does not enable or validate desktop/computer-use workflows,
even if the pinned Hermes installer downloads an optional computer-use driver.

## Prerequisites

- Linux with Docker and sufficient memory/disk for the chosen model and images.
- OpenShell **0.1.5**. A different installed version is rejected rather than
  upgraded or downgraded automatically.
- Automatic OpenShell CLI/gateway provisioning requires Debian/Ubuntu and a
  working systemd user service. On other Linux distributions, install and
  configure OpenShell 0.1.5 manually before running the installer.
- Host Node.js is required for installer configuration/profile handling.
  The installer runs its normal host prerequisite setup.
- Network access for initial package/image/model downloads, or suitable caches.
  Runtime sandbox egress restrictions do not describe the image-build environment.

`HARNESS_OPENSHELL_GATEWAY` selects the gateway when creating a new profile
(default: `openshell`); lifecycle commands use the recorded gateway. On a fresh
machine the checksum-pinned upstream installer provisions the CLI and local
gateway. Existing gateways must already be configured and authenticated.

See [Get Started](../user-guide/get-started.md) for general installer
prerequisites. Run the commands below from the Agent Harness Install component
directory.

## Getting started

### Install a sandboxed agent

On a fresh host, one command provisions installer-owned OVMS and IR, downloads
**OpenVINO/Qwen3.5-9B-int8-ov**, and installs OpenClaw in its sandbox:

```bash
./install.sh --runtime openshell --harness openclaw --non-interactive
```

For Hermes, use:

```bash
./install.sh --runtime openshell --harness hermes --non-interactive
```

Run either command to install one agent, or both to create separate sandboxes
against the same shared model. The default is the **9B** model in the Qwen3.5
family, not a 3.5B model. Explicit `--model`, exporter and hub choices remain
supported; host-mode model selection is unchanged.

The default model's preconverted OpenVINO weights are downloaded using the
existing `hf-snapshot` exporter. Its repository has no OVMS graph, so the pinned
serving image generates `graph.pbtxt` using `--configure --task text_generation`
before registration. Once the serving image is available, this metadata-only
container step needs no network/GPU access and does not reconvert weights.
No external OVMS container or local model-directory import is used.

With managed local inference, IR/OVMS are validated for the exact model,
readiness, private network and loopback publication. With an external backend,
the local IR's loopback publication and advertised model are checked instead;
the installer does not manage that external backend.

To prepare or explicitly reconfigure shared inference separately:

```bash
./install.sh inference --runtime openshell --non-interactive
# Or choose another model explicitly:
./install.sh inference --runtime openshell --model <model-id> --non-interactive
```

Separate inference provisioning is optional, not a prerequisite for a fresh
managed sandbox install.

### Inspect and connect

```bash
./install.sh status --runtime openshell --harness openclaw
./install.sh connect --runtime openshell --harness openclaw
```

For Hermes:

```bash
./install.sh status --runtime openshell --harness hermes
./install.sh connect --runtime openshell --harness hermes
```

The OpenShell gateway owns sandbox lifecycle and policy delivery. The OpenClaw
gateway runs **inside** its sandbox, binds to sandbox loopback and uses a
generated authentication token. Hermes runs as an interactive CLI; messaging
integrations are not enabled. `connect` uses OpenShell's authenticated execution
path and does not publish an agent UI on the LAN.

### Browser access

Agent UIs must remain private: use OpenShell forwarding bound to host loopback
and an SSH tunnel to your laptop rather than LAN publication.

Hermes browser chat is available on demand through its built-in dashboard:
run `hermes dashboard --host 127.0.0.1 --port 9119 --skip-build --no-open`
inside the owned sandbox using `openshell sandbox exec`. Forward sandbox port
9119 with `openshell forward service`, then SSH-tunnel the host loopback port
to your laptop. The dashboard is not started by the installer and stops with
its process/sandbox; keep its launcher running during testing. No messaging
gateway is required for browser chat. Do not expose the loopback-only dashboard
on a LAN without configuring Hermes authentication.
This browser UI is separate from external web-search/browser tools: those tools
still need explicit egress policy and any required service configuration.

For example, read the sandbox `name` and `gateway` from
`~/.agent-harness-install/openshell/hermes/profile.json`. Substitute them below.
Run the dashboard on the installation host in one terminal:

```bash
openshell sandbox exec --name <sandbox-name> --no-tty --no-login-shell \
  -g <gateway-name> -- /home/node/.local/bin/hermes dashboard \
  --host 127.0.0.1 --port 9119 --skip-build --no-open
```

In a second terminal on that host, keep the forward running:

```bash
openshell forward service <sandbox-name> --target-port 9119 \
  --local 127.0.0.1:19119 -g <gateway-name>
```

On your laptop, substitute your SSH account/host and add your SSH identity
option if needed:

```text
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:19119:127.0.0.1:19119 <user>@<installation-host>
```

Open `http://127.0.0.1:19119/chat?profile=default` on the laptop. The example
uses loopback/tunnel access and does not require an OpenClaw token. A Hermes
"Gateway Status: Off" indication refers to its messaging gateway, not a failed
browser dashboard. Stop all three commands when finished.

Hermes uses [a dedicated policy](../../openshell/hermes-policy.yaml) matching the
[base agent policy](../../openshell/policy.yaml) except for writable `/dev/ptmx`
and `/dev/pts`. These sandbox-local pseudo-terminal devices are needed by its
browser chat terminal; OpenClaw's policy is unchanged. This does not grant host
filesystem, Docker socket or additional network access. Existing Hermes
sandboxes must be recreated with the new policy after backing up needed data.

## Model lifecycle and repeated installs

Repeated installs without `--model` reuse the saved shared model and preserve
sandbox data. The full source ID, hub, exporter, revision and conversion options
are saved in `~/.agent-harness-install/openshell-model-source.json`; the served ID
is also recorded in `openshell-model`. Older installations fall back to their
shared selection, agent profile or OVMS registry before the fresh-install default.

An explicit new `--model` checks the normal exporter cache, downloads/converts
when needed, reconfigures OVMS/IR, and synchronizes **both installed agents**.
Changing shared inference can interrupt active turns: finish those turns first.
The installer preserves sandbox identities, gateway tokens, history and workspace.
It writes a durable selection inside each sandbox, restarts it without deletion,
and updates its host profile only after the restart/model check succeeds.
The durable selection takes precedence over the original sandbox creation
environment, so OpenClaw and Hermes keep the new model on later stop/start.

An interrupted switch leaves `openshell-model-pending.json`; rerun the install
without `--model` to resume that exact target before requesting another model.
This is recoverable sequencing, not an atomic all-service transaction: a failed
switch may temporarily leave inference or an agent unavailable. Old downloaded
models remain cached until full uninstall.
Only the selected model remains registered for serving in managed OpenShell
mode, avoiding simultaneous loading of previous large models into GPU memory.
A no-model rerun does not silently replace an existing route; incomplete
deployments require an explicit model selection to repair.

Existing images predating restart-safe startup fail preflight before inference
is modified. They require a separately planned image migration after backing
up needed data; the installer does not automate image upgrades, agent replacement
or backup/restore and never deletes/recreates a legacy sandbox to change its model.

### Qwen local-model defaults

New OpenShell images generate a responsiveness-oriented baseline for the exact
served model `Qwen3.5-9B-int8-ov`:

| Setting | OpenClaw | Hermes |
|---|---|---|
| Context budget | `contextWindow: 65536` | `model.context_length: 65536` |
| Reply cap | Catalog and model params `maxTokens: 512` | Custom-provider `extra_body.max_tokens: 512` |
| Sampling | Model params `temperature: 0.2` | Custom-provider `extra_body.temperature: 0.2` |
| Thinking | `thinkingDefault: off` and `chat_template_kwargs.enable_thinking: false` | Model reasoning override `none` and custom-provider `chat_template_kwargs.enable_thinking: false` |
| Prompt/tool size | `localModelLean: true`, bootstrap limits 4000/12000 characters, `tools.profile: coding` | No unsupported OpenClaw prompt/tool settings are copied |

These are operational budgets, not model maximum capabilities or latency
guarantees. The 512-token cap can truncate long answers or tool calls; increase
the model-specific request cap (and OpenClaw catalog cap) when needed. Existing
explicit settings, including catalog values in older configurations, take
precedence; absent keys receive defaults. Startup preserves gateway tokens,
history and workspace data. Hermes uses its bundled Python/YAML runtime and a
dedicated `custom:harness-ovms-qwen` provider through the same IR endpoint.

The sandbox's `.harness-local-defaults.json` tracks only installer-added values.
Restarts preserve user edits. Switching models removes unchanged installer-added
Qwen values before configuring the next model; user overrides remain. Other
models keep existing settings, or the previous generic OpenClaw catalog defaults
(32768 context / 4096 output) when none exist. Host mode is unchanged. Existing
images need rebuilding/migration to include this startup behavior; this is not
a live deployment migration or a chat acceptance gate.

## Validation and troubleshooting

Onboarding checks inference connectivity, **not** agentic correctness. A Ready
sandbox or successful chat smoke test does not validate multi-step tool use.
Tool-use acceptance requires independently verifying generated files/content.
The 0.5B quickstart model is not a validated multi-step tool-use baseline.

| Symptom | Check |
|---|---|
| LLM responds but web search or browsing fails | External tools need explicit egress policy and service configuration; IR only supplies inference routing |
| Hermes dashboard opens but its terminal cannot allocate a PTY | Use the Hermes-specific policy; older sandboxes need backed-up recreation |
| OpenClaw SQLite temporary-storage errors | Current startup exports a private mode-700 `SQLITE_TMPDIR` before any Node process; older images need the updated startup |
| Installation reports a pending model transition | Rerun without `--model` to resume before selecting a different model |

Offline regression tests: `bash test/openshell-test.sh`. Agent-image build and
real sandbox tests require Docker, the pinned gateway and a running shared IR.
See [OpenShell quality gates](../../test/README.md) for automated test cases,
TAP reports, opt-in lifecycle tests and CI runner setup. PTY allocation tests
are not automated browser chat acceptance tests.

## Uninstall

Back up needed chat/workspace data before uninstalling. Full uninstall deletes
both owned sandboxes, shared IR, managed OVMS, downloaded models and installer
state by default. An installer-owned OpenShell CLI/gateway is removed; a
pre-existing installation is preserved. An external inference backend is never
removed. If the same state directory records a host-installed agent, full
uninstall removes that agent too.

Use the [uninstall guide](../user-guide/uninstall.md#openshell-profiles) for
full/scoped commands, ownership safeguards, retained prerequisites and the
`--keep-models` option. Stop separately launched forwarding and SSH processes
after uninstall.

See [Known Limitations](../user-guide/known-limitations.md) for remaining
runtime, model, network and migration restrictions.
