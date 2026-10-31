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
   MediaPipe graph OVMS's `/v3/chat/completions` endpoint needs. Pre-converted
   `OpenVINO/*` models are only downloaded, by the same OVMS image that serves
   them. For gated
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

## Metrics

`metrics` turns telemetry on or off for the Inference Router and the harness
and shows its state. Every verb takes arguments:

```bash
./install.sh metrics enable [--target all|harness|router] [--backend sqlite|jaeger|otlp] [--endpoint <url>] [--content off|preview|full]
./install.sh metrics disable [--target all|harness|router] [--clean | --keep-jaeger]
./install.sh metrics show [--target all|harness|router]
```

| Verb | Arguments | What it controls |
|---|---|---|
| `enable` | `--target`, `--backend`, `--endpoint`, `--content` | How telemetry is collected (`--content`), and where it is stored or visualized (`--backend`, `--endpoint`) |
| `disable` | `--target`, `--clean`, `--keep-jaeger` | Stops collection. `--clean` also deletes the collected data; `--keep-jaeger` leaves the managed Jaeger and its traces running |
| `show` | `--target` | A CLI summary of what was collected, and the Jaeger UI address when Jaeger is the backend (Jaeger is the full trace view) |

- `router`: switches the Inference Router telemetry backend to a JSONL file
  (`telemetry.jsonl` in the router workspace), restarts the router, and
  `show` reads `/v1/metrics`. `disable` reverts to the in-memory backend.
  The restart interrupts any request in flight, so run these between agent
  sessions, not during one.
  The setting persists across model changes. The file is group-writable
  (mode 664): the router container runs as another uid, so the installer starts
  it with `--group-add <your primary group id>` instead of making the file
  world-writable. It holds counters and latencies, not prompt text. Rootless
  Docker and user-namespace remapping do not map group ids that way (`metrics
  enable` warns when it detects them); set
  `HARNESS_IR_TELEMETRY_FILE_MODE=666` there. A router container created by an
  earlier installer version lacks that group: re-run `./install.sh` once to
  recreate it before enabling.
- `harness` (Hermes, host runtime): installs and enables the `hermes-otel`
  plugin and writes `$HERMES_HOME/hermes_otel.yaml`. `--backend sqlite` keeps
  records in the local store only; `jaeger` exports OTLP to a Jaeger
  all-in-one container managed by the installer (loopback only), or to
  `--endpoint` when given; `otlp` requires `--endpoint`. `--content` controls
  prompt/response capture and defaults to `off`. Restart running Hermes
  sessions afterwards. `disable` disables the plugin, removes the managed
  config and any managed Jaeger.
- `--target all` (default) applies both; an unsupported harness is skipped
  with a notice.
- Re-running `enable` keeps the saved harness `--backend`, `--endpoint` and
  `--content` unless you name them again, so `metrics enable --target all`
  later does not reset a Jaeger setup to `sqlite`.

### Cleaning collected data and keeping Jaeger

`disable` keeps what was collected unless you ask otherwise:

| Command | Router `telemetry.jsonl` | Hermes local store (`hermes_otel_live.db`) | Managed Jaeger and its traces |
|---|---|---|---|
| `metrics disable` | Kept | Kept | Removed |
| `metrics disable --clean` | Emptied | Emptied | Removed |
| `metrics disable --keep-jaeger` | Kept | Kept | Kept running |

- `--clean` and `--keep-jaeger` conflict, since cleaning removes Jaeger's traces.
  `--keep-jaeger` applies to the harness. A later `metrics disable --target
  harness` (or uninstall) removes the kept container; a later `metrics enable`
  that does not use Jaeger leaves it running.
- The Hermes store is emptied in place, not deleted, so a running Hermes
  gateway keeps working. A Hermes session that is still running keeps adding
  records until it is restarted. The plugin keeps at most 4000 rows per kind
  and, by default, drops rows older than 7 days by itself.
- If a clean cannot run (no `python3`, a locked store, or a symlinked file),
  the command says so and does not report the data as cleaned.
- Traces already exported to your own `--endpoint` collector are not removed;
  clear them in that backend.
- The Router restarts when it is disabled, which also resets its in-memory
  counters.

### Reading the data

`metrics show` is the CLI view:

- **Router:** whether file collection is on, the events file, and live totals
  from `/v1/metrics` (requests, tokens, latency), followed by a per
  provider/model breakdown.
- **Harness:** the plugin and config state, then a summary of the local store
  (record counts by kind, sessions, error spans, time window, and the busiest
  spans with count, average and maximum duration). The store is opened
  read-only. This needs `python3`; without it the summary is skipped.
- **Jaeger:** `show` prints the UI address (`http://127.0.0.1:16686` for the
  managed container). Use it for the full trace view, which the CLI summary
  does not replace.

Limitations: harness telemetry is not available in OpenShell sandboxes (the
sandbox has no network egress beyond the router), and only Hermes is
supported. After an OpenShell install, pass `--runtime openshell` to `metrics`
(otherwise the runtime defaults to `host`). Router telemetry works in both
runtimes. The Router's `telemetry.jsonl` is append-only while the Router runs;
the installer rotates it once it exceeds `HARNESS_IR_TELEMETRY_MAX_BYTES` (see
[Router telemetry file](#router-telemetry-file)).
Overrides:
`HARNESS_HERMES_OTEL_PLUGIN`, `HARNESS_HERMES_OTEL_REF`,
`HARNESS_IR_TELEMETRY_MAX_BYTES`, `HARNESS_IR_TELEMETRY_FILE_MODE`,
`HARNESS_JAEGER_IMAGE`, `HARNESS_JAEGER_CONTAINER`,
`HARNESS_JAEGER_UI_PORT`, `HARNESS_JAEGER_OTLP_PORT`.

By default the plugin is installed from Hermes's reviewed plugin catalog
(`hermes plugins install hermes_otel`), which checks out the commit pinned
there and applies Hermes's removal kill-list. To pin another commit, set
`HARNESS_HERMES_OTEL_REF` to a full 40-character SHA; it is passed as `--ref`
and applies to a fresh plugin install only (an installed plugin is left as is).

### Harness backends

`--backend` applies to the harness only; the Router has its own `memory`/`file`
backend (see [Router telemetry file](#router-telemetry-file)). `jaeger` and
`otlp` both export OTLP/HTTP traces. The difference is that `jaeger` can start
and manage the collector for you.

| `--backend` | Where the data goes | `--endpoint` |
|---|---|---|
| `sqlite` (default) | The plugin's local store, `$HERMES_HOME/hermes_otel_live.db` (default `~/.hermes`). Nothing leaves the machine. | Not allowed |
| `jaeger` | Without `--endpoint`: a managed `jaegertracing/all-in-one` container (`agent-harness-install-jaeger`), published on `127.0.0.1` only (UI `16686`, OTLP `4318`). With `--endpoint`: your own Jaeger, which the installer does not manage. | Optional |
| `otlp` | Any OTLP/HTTP collector at `--endpoint` (for example an OpenTelemetry Collector or Grafana Tempo). Storage is whatever that collector uses. | Required |

- The `--endpoint` URL must be plain `http(s)://host[:port][/path]` (host: a
  name, IPv4 address or bracketed IPv6 such as `[::1]`; port 1 to 65535), with
  no credentials or query string. Repeating a flag is an error.
- The managed Jaeger container is removed by `metrics disable`, by switching
  to another backend, and by uninstall.
- `--content` is independent of `--backend`: with `preview` or `full`,
  prompt/response text is sent to whichever backend you chose, including an
  external `otlp` collector. `enable` warns when the endpoint is not on this
  machine (`127.0.0.1` or `localhost`).

### Router telemetry file

The Inference Router supports exactly two telemetry backends, `memory` and
`file`, and `metrics enable --target router` selects `file`. Nothing leaves
the machine: the Router appends to a local file and does not export telemetry.

| | `memory` (default) | `file` (after `metrics enable --target router`) |
|---|---|---|
| Storage | Router process memory | `telemetry.jsonl`, bind-mounted from the container's `/app/telemetry.jsonl` to `~/.agent-harness-install/inference-router/workspace/telemetry.jsonl` |
| `GET /v1/metrics` | Reads the in-process counters | Re-reads and re-parses the whole file |
| Router restart | Counters reset to zero | History is kept; a restart never truncates the file |

Each completed request adds one JSON line (`request_completed`) with the
provider, model, input/output token counts, total latency and TTFT/TPOT when
available. It holds no prompt or response text.

What clears the file:

- `./install.sh metrics disable --target router --clean` (or `--target all`)
  empties it after switching the Router back to `memory`.
- `POST /v1/metrics/reset` on the Router truncates it.
- Deleting it by hand is safe; the next `metrics enable --target router`
  recreates it with the right permissions.
- Rotation: when the installer next prepares the file (an install, or
  `metrics enable --target router`) and it is larger than
  `HARNESS_IR_TELEMETRY_MAX_BYTES` (default 20 MiB; `0` turns rotation off),
  it is moved to `telemetry.jsonl.1` (mode 600) and a fresh file is started.
  Only one previous generation is kept, and `/v1/metrics` counts only the new
  file. `metrics show` warns when the file is over the limit, and
  `--clean` removes the rotated file too.
- `./uninstall.sh` removes it with the rest of the state directory, including
  with `--keep-models`, which only retains the models.

`metrics disable --target router` switches back to `memory` and restarts the
Router, so the live counters read zero, but it leaves the file in place unless
you pass `--clean`. The kept file is restricted to owner-only (mode 600) since
nothing writes it any more; a later `enable` reopens it as configured. If you
enable again, the old events are counted with the
new ones; clean the file first for a clean session.

The file is a Router design choice, not an installer one: the Router has no
database backend. It needs no extra service and is easy to inspect, ship or
delete, and appends are serialised with an exclusive file lock. The cost is
that reads slow down as the file grows, the installer rotates it only when it
runs (not while the Router is serving), and you
only get the totals and time-window filtering the Router exposes. A database
backend would need a new `Telemetry` implementation and a new `backend:`
value in `microservices/inference-router`.

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
